"""
Arkon MCP Tools — LLM Wiki + raw source drill-down for Claude.

The wiki layer is the primary surface: Claude searches and reads markdown
pages compiled from sources. Raw-source tools (PageIndex-style) act as a
fallback for precise citations or text the wiki has paraphrased away.

All tools verify the employee's MCP token and enforce knowledge_type scope:
  - search_wiki / read_wiki_page / list_wiki_pages: filter by
    `knowledge_type_slugs && allowed_knowledge_types` (Postgres ARRAY overlap).
  - get_source / get_source_outline / get_source_pages / list_sources /
    get_knowledge_type_docs: enforce per-source scope via apply_scope_filter.
"""

from typing import Optional

from fastmcp import FastMCP
from loguru import logger
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.logging import current_identity, logged_tool
from app.mcp.permissions import (
    ANY_AUTHENTICATED,
    CAN_CONTRIBUTE_WIKI,
    kb_tool,
)

# Cosine-similarity floor for search_wiki. Vector-only hits below this are
# dropped as noise; hits the full-text arm matched bypass the floor (an exact
# keyword match matters even at low cosine).
MIN_SIM_FLOOR = 0.30

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def _get_identity():
    """Resolve the bearer token to a ResolvedIdentity, or return an error string."""
    from fastmcp.server.dependencies import get_http_request

    from app.database import async_session_factory
    from app.services.mcp_auth_service import MCPAuthService

    try:
        request = get_http_request()
        auth_header = request.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
    except RuntimeError:
        return None, "No HTTP request context available."

    if not token:
        return None, (
            "Authentication required. Configure your MCP token in Claude Desktop:\n"
            '{"mcpServers": {"arkon": {"url": "...", '
            '"headers": {"Authorization": "Bearer <your-token>"}}}}'
        )

    async with async_session_factory() as session:
        auth_svc = MCPAuthService(session)
        identity = await auth_svc.verify_token(token)
        if identity is None:
            return None, "Invalid or inactive MCP token. Contact your administrator."
        # Only commit when verify_token actually bumped last_connected;
        # otherwise this is a pure read and an empty COMMIT round-trips Redis
        # latency for nothing on every MCP tool call.
        if auth_svc.bumped_last_connected:
            await session.commit()

        user_role = (request.headers.get("x-user-role") or "").strip().lower()
        dept_code = (request.headers.get("x-department-code") or "").strip()
        dept_name = (request.headers.get("x-department-name") or "").strip()

        # Dynamic scope enforcement based on forwarded department and role from Chatbot
        if user_role:
            if user_role == "admin":
                identity.is_admin = True
            else:
                identity.is_admin = False
                matched_depts = []
                if dept_code or dept_name:
                    from sqlalchemy import or_, select
                    from app.database.models import Department

                    conds = []
                    if dept_code:
                        conds.append(Department.name.ilike(f"%{dept_code}%"))
                    if dept_name:
                        conds.append(Department.name.ilike(f"%{dept_name}%"))
                    stmt = select(Department).where(or_(*conds))
                    res = await session.execute(stmt)
                    matched_depts = res.scalars().all()

                    # If not found in Arkon DB but valid dept_code supplied, auto-register it
                    if not matched_depts and dept_code:
                        new_dept = Department(name=dept_code, description=dept_name or dept_code)
                        session.add(new_dept)
                        await session.commit()
                        await session.refresh(new_dept)
                        matched_depts = [new_dept]

                if matched_depts:
                    identity.department_ids = [d.id for d in matched_depts]
                    identity.department_names = [d.name for d in matched_depts]
                    identity.allowed_source_ids = await auth_svc._get_department_source_ids(identity.department_ids)
                else:
                    identity.department_ids = []
                    identity.department_names = []
                    identity.allowed_source_ids = await auth_svc._get_department_source_ids([])

    current_identity.set(identity)
    return identity, None


async def _get_allowed_source_ids(identity, session: Optional[AsyncSession] = None) -> Optional[set[str]]:
    """Allowed source UUID strings, or None when access is unrestricted.

    Pass an existing session to avoid opening a second DB connection.
    """
    if identity.is_admin:
        return None
    if identity.allowed_source_ids is None and identity.allowed_knowledge_types is None:
        return None

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.database.models import Source
    from app.services.mcp_auth_service import apply_scope_filter

    async def _query(s: AsyncSession) -> set[str]:
        stmt = select(Source.id).where(Source.status == "ready")
        stmt = apply_scope_filter(stmt, identity)
        result = await s.execute(stmt)
        return {str(r[0]) for r in result.all()}

    if session is not None:
        return await _query(session)

    async with async_session_factory() as session:
        return await _query(session)


# ---------------------------------------------------------------------------
# Permission helpers (shared across review/contribute tools)
# ---------------------------------------------------------------------------

async def _can_review_page(session: AsyncSession, employee, page) -> bool:
    """wiki:write:all globally, or admin.

    Mirrors REST `_can_review`.
    """
    from app.services.permission_engine import _get_user_permissions
    if employee.role == "admin":
        return True
    perms = _get_user_permissions(employee)
    return "wiki:write:all" in perms


async def _can_contribute_to_page(session: AsyncSession, employee, page) -> bool:
    """Permission to propose an edit on `page` via MCP.

    Mirrors REST `_can_propose`:
    - Department pages: wiki:write:all, or wiki:write:own_dept restricted to
      the employee's own department.
    - Global pages: any wiki:write permission.
    """
    from app.services.permission_engine import (
        _get_user_permissions,
        has_any_permission,
    )
    if employee.role == "admin":
        return True
    perms = _get_user_permissions(employee)
    if page.scope_type == "department" and page.scope_id:
        if "wiki:write:all" in perms:
            return True
        return (
            "wiki:write:own_dept" in perms
            and page.scope_id in employee.department_ids
        )
    return has_any_permission(list(perms), "wiki", "write")


# ---------------------------------------------------------------------------
# Out-of-scope hint (Tier 1 — count + scope name, no titles/content leaked)
# ---------------------------------------------------------------------------

async def _format_oos_hint(session: AsyncSession, oos_hits: list) -> str:
    """Aggregate out-of-scope search hits into a short "ask for access" hint.

    Intentionally leaks ONLY (count, scope_type, scope_name) — never titles
    or summaries — to avoid information disclosure across department
    boundaries. A page title can itself be sensitive
    (e.g. "Q1 layoffs — Engineering").
    """
    if not oos_hits:
        return ""

    from collections import Counter

    from app.database.models import Department

    # Group by (scope_type, scope_id) → count.
    buckets: Counter[tuple[str, str | None]] = Counter()
    for page, _sim in oos_hits:
        scope_type = page.scope_type or "global"
        if scope_type == "global":
            continue  # global pages should already be visible; defensive skip
        scope_id = str(page.scope_id) if page.scope_id else None
        buckets[(scope_type, scope_id)] += 1

    if not buckets:
        return ""

    # Resolve human-readable scope labels.
    labels: dict[tuple[str, str | None], str] = {}
    for (scope_type, scope_id) in buckets.keys():
        label: str | None = None
        if scope_id:
            import uuid as _uuid
            try:
                sid = _uuid.UUID(scope_id)
            except (ValueError, TypeError):
                sid = None
            if sid is not None:
                if scope_type == "department":
                    d = await session.get(Department, sid)
                    label = d.name if d else None
        labels[(scope_type, scope_id)] = label or "(unknown)"

    lines = ["**Out-of-scope matches** — matching page(s) exist outside your access:"]
    for (scope_type, scope_id), count in buckets.most_common():
        label = labels[(scope_type, scope_id)]
        if scope_type == "department":
            lines.append(
                f"- {count} page(s) in department **{label}** — "
                f"contact the {label} department admin to request access."
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_tools(mcp: FastMCP):
    """Register all KB tools on the MCP server."""

    # =========================================================================
    # Wiki layer — synthesized markdown pages compiled from sources
    # =========================================================================

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("search_wiki", query_arg="query")
    async def search_wiki(query: str, top_k: int = 10) -> str:
        """
        Semantic search across the knowledge base — synthesized wiki pages AND
        verbatim source documents — in one ranked list.

        Use this FIRST when answering a question about the organization. Results
        are of two kinds:
          - 📘 Wiki pages: persistent, interlinked summaries compiled from many
            sources. Read the full page with `read_wiki_page(slug)`.
          - 📄 Source matches: passages from high-fidelity documents kept verbatim
            (decrees, gazettes, contracts) that are NOT rewritten. Read the exact
            original text with `get_source_pages(source_id, "<page>")` and cite the
            portal link shown so the user can open or download the original.

        If the response includes an "Out-of-scope matches" section, pages matching
        the query exist but live in a department the caller is not a
        member of — tell the user to request access instead of assuming it's missing.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return (default: 10, max: 50).

        Returns:
            A ranked list of wiki pages and source matches with similarity scores.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        top_k = min(max(1, top_k), 50)

        from app.config import settings
        from app.ai.registry import ProviderRegistry
        from app.database import async_session_factory
        from app.services import wiki_service


        from app.services.retrieval_service import (
            format_graph_neighbors_section,
            unified_search,
        )

        exact_match = None
        graph_neighbors = []
        oos_hint = ""

        async with async_session_factory() as session:
            registry = ProviderRegistry(session)
            embedding_provider = await registry.get_embedding(task="search_query")
            query_embedding = await embedding_provider.embed(query)

            allowed_source_ids = await _get_allowed_source_ids(identity, session)

            search_out = await unified_search(
                session=session,
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
                allowed_kt_slugs=identity.allowed_knowledge_types,
                department_ids=identity.department_ids,
                all_scopes=identity.is_admin,
                allowed_source_ids=allowed_source_ids,
                apply_reranker=True,
                apply_mmr=True,
                check_out_of_scope=not identity.is_admin,
            )

            exact_match = search_out.get("exact_match")
            ranked = search_out.get("ranked_results", [])
            graph_neighbors = search_out.get("graph_neighbors", [])
            oos_hits = search_out.get("out_of_scope_hits", [])
            failed_arms = search_out.get("failed_arms", [])
            total_candidates = search_out.get("total_candidates", len(ranked))
            if oos_hits:
                oos_hint = await _format_oos_hint(session, oos_hits)

        arm_labels = {"wiki": "trang wiki", "source": "văn bản gốc", "exact": "tra cứu theo số hiệu"}
        failed_main = [a for a in ("wiki", "source") if a in failed_arms]
        if len(failed_main) == 2 and not exact_match:
            return (
                "Tìm kiếm thất bại: cả trang wiki và văn bản gốc đều bị lỗi. "
                "Thử lại sau hoặc báo quản trị viên."
            )
        failure_note = ""
        failed_shown = [arm_labels[a] for a in ("wiki", "source", "exact") if a in failed_arms]
        if failed_shown:
            failure_note = (
                f"⚠️ Tìm kiếm trên {', '.join(failed_shown)} bị lỗi; "
                "kết quả có thể chưa đầy đủ.\n"
            )

        exact_block = ""
        if exact_match and exact_match.get("found"):
            exact_block = (
                "🎯 **KẾT QUẢ TRA CỨU CHÍNH XÁC THEO SỐ HIỆU VĂN BẢN**:\n"
                f"- **Văn bản**: {exact_match.get('doc_number', '')} — {exact_match.get('full_path', '')}\n"
                f"- **Tiêu đề**: {exact_match.get('title') or ''}\n"
                f"- **Nội dung**:\n{exact_match.get('content', '')}\n"
            )
            if exact_match.get("warning_callout"):
                exact_block += f"\n{exact_match['warning_callout']}\n"
            exact_block += "\n---\n"

        if not ranked:
            if exact_block:
                return failure_note + exact_block
            base = failure_note + f"No knowledge base matches found for: \"{query}\""
            if oos_hint:
                return f"{base}\n\n{oos_hint}"
            return base

        def _portal_link(source_id) -> str:
            base = (settings.portal_base_url or "").rstrip("/")
            return f"{base}/wiki/source/{source_id}" if base else f"/wiki/source/{source_id}"

        def _score_label(hit: dict) -> str:
            if "rerank_score" in hit:
                return f"⚡ rerank {hit['rerank_score']:.2f}"
            cos = hit.get("cosine")
            if cos is not None:
                return f"{cos:.0%}"
            return "🔑 từ khóa"  # FTS-only match, no cosine

        lines = []
        if failure_note:
            lines.append(failure_note)
        if exact_block:
            lines.append(exact_block)
        lines.append(f"**KB search — {len(ranked)} result(s) for: \"{query}\"**\n")
        for kind, _score, hit in ranked:
            score_label = _score_label(hit)
            if hit.get("exact_match"):
                score_label = "🎯 khớp chính xác · " + score_label
            if kind == "wiki":
                page = hit["page"]
                kt_label = (
                    f" [{', '.join(page.knowledge_type_slugs)}]"
                    if page.knowledge_type_slugs else ""
                )
                entry = (
                    f"- 📘 `{page.slug}` ({page.page_type}){kt_label} — {score_label}\n"
                    f"  **{page.title}**"
                )
                if hit.get("heading_path"):
                    entry += f" · _{hit['heading_path']}_"
                if page.summary:
                    entry += f" — {page.summary}"
                entry += "\n  _Read: `read_wiki_page(\"%s\")`_" % page.slug
            else:
                source = hit["source"]
                chunk = hit.get("chunk")
                title = source.title or source.file_name or source.url or "Untitled"
                page_num = getattr(chunk, "page_number", 1) if chunk else 1
                preview = ((getattr(chunk, "text", "") or "").strip().replace("\n", " ")) if chunk else ""
                if len(preview) > 200:
                    preview = preview[:200] + "…"
                entry = (
                    f"- 📄 **{title}** (nguyên văn) — {score_label} — trang {page_num}\n"
                    f"  “{preview}”\n"
                    f"  _Đọc bản gốc: `get_source_pages(\"{source.id}\", \"{page_num}\")` · "
                    f"Link: {_portal_link(source.id)}_"
                )
            lines.append(entry)

        if total_candidates > len(ranked):
            lines.append(
                f"\n_Hiển thị {len(ranked)}/{total_candidates} ứng viên phù hợp — "
                f"tăng `top_k` (tối đa 50) hoặc thu hẹp truy vấn để xem thêm._"
            )

        if graph_neighbors:
            lines.append("")
            lines.append(format_graph_neighbors_section(graph_neighbors))

        if oos_hint:
            lines.append("")
            lines.append(oos_hint)
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("read_wiki_index")
    async def read_wiki_index() -> str:
        """
        Read the wiki catalog.

        Lists the wiki pages you can access, grouped by type, with one-line
        summaries. Use this to discover the shape of the wiki before drilling
        into specific pages.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        from app.database import async_session_factory
        from app.services import wiki_service

        async with async_session_factory() as session:
            return await wiki_service.render_scoped_index(
                session,
                allowed_kt_slugs=identity.allowed_knowledge_types,
                department_ids=identity.department_ids,
                all_scopes=identity.is_admin,
            )

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("read_wiki_page", query_arg="slug")
    async def read_wiki_page(slug: str) -> str:
        """
        Read a specific wiki page by slug, plus its backlinks.

        Args:
            slug: The page slug, e.g. "entity/jane-doe", "concept/onboarding".
                  Use `search_wiki` or `list_wiki_pages` to find slugs.

        Returns:
            Markdown content of the page, plus an "Outlinks" section listing
            pages this one links out to, and a "Backlinks" section listing pages
            that link back to it. Both lists (and any inline `[[slug]]` wikilinks)
            can be followed with another `read_wiki_page` call to traverse the
            knowledge graph.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        from app.database import async_session_factory
        from app.services import wiki_service

        import uuid as uuid_mod
        from sqlalchemy import select as sa_select

        from app.database.models import Department, WikiPage

        async with async_session_factory() as session:
            # Try global → department.
            page = await wiki_service.get_page_by_slug(
                session, slug, allowed_kt_slugs=identity.allowed_knowledge_types,
            )
            if not page and identity.department_ids:
                # Walk the user's departments until we hit a matching slug.
                for did in identity.department_ids:
                    page = await wiki_service.get_page_by_slug(
                        session, slug,
                        allowed_kt_slugs=identity.allowed_knowledge_types,
                        scope_type="department",
                        scope_id=did,
                    )
                    if page:
                        break

            if not page:
                # Out-of-scope hint: does the slug exist in a scope the caller
                # CAN'T access? If so, leak only the scope label (no content).
                if not identity.is_admin:
                    stmt = sa_select(WikiPage).where(WikiPage.slug == slug)
                    others = (await session.execute(stmt)).scalars().all()
                    inaccessible = [
                        p for p in others
                        if p.scope_type == "department" and p.scope_id not in identity.department_ids
                    ]
                    if inaccessible:
                        labels: list[str] = []
                        for p in inaccessible:
                            if p.scope_type == "department" and p.scope_id:
                                d = await session.get(Department, p.scope_id)
                                labels.append(
                                    f"department **{d.name if d else '(unknown)'}**"
                                )
                        # Dedup while preserving order.
                        seen: set[str] = set()
                        unique_labels = [
                            x for x in labels if not (x in seen or seen.add(x))
                        ]
                        joined = ", ".join(unique_labels)
                        return (
                            f"Wiki page `{slug}` exists in {joined} but you don't "
                            f"have access. Contact the scope's admin to request access."
                        )
                return f"Wiki page not found or out of scope: `{slug}`"

            backlinks = await wiki_service.get_backlinks(
                session, slug, page.scope_type, page.scope_id,
            )
            outlinks = await wiki_service.get_outlinks(
                session, slug, page.scope_type, page.scope_id,
            )

            # Check legal validity warnings if this is a legal article page
            validity_callout = ""
            try:
                from app.database.models import LegalUnit
                from app.services.legal_service import (
                    get_legal_unit_validity_warnings,
                    format_legal_validity_warning_callout,
                )
                unit_res = await session.execute(sa_select(LegalUnit).where(LegalUnit.wiki_page_id == page.id))
                legal_unit = unit_res.scalar_one_or_none()
                if legal_unit:
                    warnings = await get_legal_unit_validity_warnings(session, legal_unit.id)
                    if warnings:
                        validity_callout = format_legal_validity_warning_callout(warnings) + "\n\n"
            except Exception:
                pass

        body = validity_callout + (page.content_md or "")
        outlinks = sorted({s for s in outlinks if s != slug})
        if outlinks:
            body = body.rstrip() + "\n\n## Outlinks\n" + "\n".join(
                f"- `{s}`" for s in outlinks
            )
        if backlinks:
            body = body.rstrip() + "\n\n## Backlinks\n" + "\n".join(
                f"- `{s}`" for s in sorted(backlinks)
            )
        return body

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("get_document_relations")
    async def get_document_relations(
        doc_number: Optional[str] = None,
        article_number: Optional[str] = None,
        slug: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """
        Relations between documents/articles: amendments, supplements,
        replacements, repeals, guidance, legal basis and cross-references —
        in both directions (what this document changes / what changes it).

        Works for any document that carries an official number (decrees,
        circulars, decisions, official letters, internal regulations…).

        Args:
            doc_number: Official document number, e.g. "136/2020/NĐ-CP",
                "123/QĐ-UBND". Partial numbers ("136/2020") are accepted.
            article_number: Article number ("5", "5a"). With `doc_number`,
                narrows to one article; without it, the whole document is used.
            slug: Wiki page slug of an article page (alternative to the above).
            limit: Max relations per direction (default 50, max 200).

        Returns:
            Validity warnings plus outgoing ("Văn bản này tác động đến") and
            incoming ("Bị tác động bởi") relations.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        import uuid as _uuid

        from sqlalchemy import case, func, or_
        from sqlalchemy.orm import aliased, configure_mappers, selectinload

        from app.database import async_session_factory
        from app.database.models import LegalRelation, LegalUnit, LegalUnitType, WikiPage
        from app.services.legal_route_service import (
            _like_escape,
            _norm_doc_sql,
            normalize_doc_number,
        )
        from app.services.legal_service import (
            format_legal_validity_warning_callout,
            get_legal_unit_validity_warnings,
        )

        limit = min(max(1, limit), 200)
        configure_mappers()
        label_map = {
            "sua_doi": "Sửa đổi", "bo_sung": "Bổ sung", "thay_the": "Thay thế",
            "bai_bo": "Bãi bỏ", "huong_dan": "Hướng dẫn", "can_cu": "Căn cứ",
            "dan_chieu": "Dẫn chiếu",
        }

        def _rtype(r) -> str:
            v = r.relation_type.value if hasattr(r.relation_type, "value") else str(r.relation_type)
            return label_map.get(v, v)

        def _unit_ref(u, doc=None, art=None) -> str:
            d = (u.doc_number if u else None) or doc or "?"
            a = (u.unit_number if u else None) or art
            return f"{d} Điều {a}" if a else d

        async with async_session_factory() as session:
            allowed = await _get_allowed_source_ids(identity, session)
            if allowed is not None and not allowed:
                return "Bạn chưa được cấp quyền truy cập văn bản nào."
            allowed_uuids = [_uuid.UUID(s) for s in allowed] if allowed is not None else None

            def _scoped(stmt, unit_cls=LegalUnit):
                if allowed_uuids is None:
                    return stmt
                return stmt.where(unit_cls.source_id.in_(allowed_uuids))

            unit = None
            if slug:
                stmt = (
                    sa_select(LegalUnit)
                    .join(WikiPage, WikiPage.id == LegalUnit.wiki_page_id)
                    .where(WikiPage.slug == slug)
                    .order_by((LegalUnit.unit_type != LegalUnitType.ARTICLE))
                    .limit(1)
                )
                unit = (await session.execute(_scoped(stmt))).scalars().first()
                if not unit and not (doc_number and article_number):
                    return f"Không tìm thấy điều khoản gắn với trang `{slug}` (hoặc bạn không có quyền)."

            doc_norm = normalize_doc_number(doc_number) if doc_number else ""
            doc_pat = _like_escape(doc_norm)
            norm_col = _norm_doc_sql(LegalUnit.doc_number)
            doc_rank = case(
                (norm_col == doc_norm, 0),
                (norm_col.like(f"{doc_pat}%", escape="\\"), 1),
                else_=2,
            )

            if not unit and doc_norm and article_number:
                stmt = (
                    sa_select(LegalUnit)
                    .where(
                        norm_col.like(f"%{doc_pat}%", escape="\\"),
                        LegalUnit.unit_type == LegalUnitType.ARTICLE,
                        func.lower(LegalUnit.unit_number) == article_number.strip().lower(),
                    )
                    .order_by(doc_rank, LegalUnit.doc_number)
                    .limit(1)
                )
                unit = (await session.execute(_scoped(stmt))).scalars().first()

            if unit:
                header = f"## Quan hệ văn bản: {unit.full_path or ''} ({unit.doc_number or 'chưa rõ số hiệu'})"
                warnings = await get_legal_unit_validity_warnings(session, unit.id)
                callout = format_legal_validity_warning_callout(warnings)
                unit_doc_norm = normalize_doc_number(unit.doc_number) if unit.doc_number else None
                out_where = [LegalRelation.source_unit_id == unit.id]
                in_conds = [LegalRelation.target_unit_id == unit.id]
                if unit_doc_norm:
                    in_conds.append(
                        (_norm_doc_sql(LegalRelation.target_doc_number) == unit_doc_norm)
                        & (func.lower(LegalRelation.target_article_number) == (unit.unit_number or "").lower())
                    )
            elif doc_norm:
                # Whole document: relations from any of its units, and relations
                # that target it by number.
                header = f"## Quan hệ văn bản: {doc_number}"
                callout = ""
                doc_unit_ids = _scoped(
                    sa_select(LegalUnit.id).where(norm_col.like(f"%{doc_pat}%", escape="\\"))
                )
                out_where = [LegalRelation.source_unit_id.in_(doc_unit_ids)]
                in_conds = [
                    _norm_doc_sql(LegalRelation.target_doc_number).like(f"%{doc_pat}%", escape="\\"),
                    LegalRelation.target_unit_id.in_(doc_unit_ids),
                ]
            else:
                return "Vui lòng cung cấp `doc_number` (kèm `article_number` nếu cần) hoặc `slug` hợp lệ."

            SrcUnit = aliased(LegalUnit)
            out_stmt = (
                sa_select(LegalRelation)
                .options(selectinload(LegalRelation.target_unit))
                .where(*out_where)
                .limit(limit + 1)
            )
            in_stmt = (
                sa_select(LegalRelation)
                .join(SrcUnit, SrcUnit.id == LegalRelation.source_unit_id)
                .options(selectinload(LegalRelation.source_unit))
                .where(or_(*in_conds))
                .limit(limit + 1)
            )
            if unit is None:
                in_stmt = in_stmt.where(~LegalRelation.source_unit_id.in_(doc_unit_ids))
            out_rels = list((await session.execute(out_stmt)).scalars().all())
            in_rels = list((await session.execute(_scoped(in_stmt, SrcUnit))).scalars().all())

        def _visible_target(r) -> bool:
            t = r.target_unit
            return t is None or allowed is None or str(t.source_id) in allowed

        lines = [header]
        if callout:
            lines.append("\n" + callout)

        more_out = len(out_rels) > limit
        out_rels = out_rels[:limit]
        if out_rels:
            lines.append("\n### Văn bản này tác động đến:")
            for r in out_rels:
                if _visible_target(r):
                    ref = _unit_ref(r.target_unit, r.target_doc_number, r.target_article_number)
                else:  # target exists but is outside the caller's scope
                    ref = _unit_ref(None, r.target_doc_number, r.target_article_number)
                src = f" (từ Điều {r.source_unit.unit_number})" if unit is None and r.source_unit and r.source_unit.unit_number else ""
                quote = f": {r.quote_context}" if r.quote_context else ""
                lines.append(f"- **{_rtype(r)}** {ref}{src}{quote}")
            if more_out:
                lines.append(f"- _… còn thêm — tăng `limit` (hiện {limit}) để xem tiếp._")

        more_in = len(in_rels) > limit
        in_rels = in_rels[:limit]
        if in_rels:
            lines.append("\n### Bị tác động bởi:")
            for r in in_rels:
                ref = _unit_ref(r.source_unit)
                eff = "" if r.is_effective else " _(không còn hiệu lực)_"
                quote = f": {r.quote_context}" if r.quote_context else ""
                lines.append(f"- **{_rtype(r)}** bởi {ref}{eff}{quote}")
            if more_in:
                lines.append(f"- _… còn thêm — tăng `limit` (hiện {limit}) để xem tiếp._")

        if not out_rels and not in_rels and not callout:
            lines.append("\n_Không ghi nhận quan hệ sửa đổi, thay thế hay dẫn chiếu nào._")
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("list_wiki_pages")
    async def list_wiki_pages(
        page_type: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """
        Browse wiki pages with filters and text search. Reserved pages (`_index`, `_log`) are excluded.

        Args:
            page_type: Filter by type — "entity", "concept", "topic", "source".
            knowledge_type: Filter by KnowledgeType slug.
            query: Optional substring search query (case-insensitive) matched against title, slug, and content.
            limit: Max pages to return (default: 50, max: 50).
            offset: Number of pages to skip for pagination (default: 0).

        Returns:
            Slug, title, summary, type, and KnowledgeType slugs for each page.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        from app.database import async_session_factory
        from app.services import wiki_service

        limit = min(max(1, limit), 50)
        offset = max(0, offset)

        async with async_session_factory() as session:
            pages = await wiki_service.list_pages(
                session,
                page_type=page_type,
                knowledge_type_slug=knowledge_type,
                allowed_kt_slugs=identity.allowed_knowledge_types,
                query=query,
                limit=limit + 1,
                offset=offset,
                department_ids=identity.department_ids,
                all_scopes=identity.is_admin,
            )

        if not pages:
            return "No wiki pages match the filters."

        has_more = len(pages) > limit
        pages = pages[:limit]
        lines = [f"**Wiki pages — {len(pages)} result(s)**\n"]
        for p in pages:
            kt_label = f" [{', '.join(p.knowledge_type_slugs)}]" if p.knowledge_type_slugs else ""
            line = f"- `{p.slug}` ({p.page_type}){kt_label} — **{p.title}**"
            if p.summary:
                line += f" — {p.summary}"
            lines.append(line)
        if has_more:
            lines.append(f"\n_Còn trang khác — gọi lại với `offset={offset + limit}`._")
        return "\n".join(lines)

    # =========================================================================
    # Raw source drill-down (PageIndex-inspired)
    # =========================================================================

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("get_source", query_arg="source_id")
    async def get_source(source_id: str) -> str:
        """
        Metadata for a raw source document — title, knowledge type, page count,
        contributor, status. Use this before reading source pages.

        Args:
            source_id: The source UUID.
        """
        import uuid as uuid_mod

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.database import async_session_factory
        from app.database.models import Source

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None
        try:
            sid = uuid_mod.UUID(source_id)
        except ValueError:
            return f"Invalid source ID: {source_id}"

        async with async_session_factory() as session:
            stmt = (
                select(Source).where(Source.id == sid)
                .options(selectinload(Source.knowledge_type), selectinload(Source.contributor))
            )
            source = (await session.execute(stmt)).scalar_one_or_none()
            if not source:
                return f"Source not found: {source_id}"

            allowed_ids = await _get_allowed_source_ids(identity, session)
            if allowed_ids is not None and str(sid) not in allowed_ids:
                return "Access denied: this source is outside your knowledge scope."

        page_count = len(source.page_offsets or [])
        kt_label = source.knowledge_type.name if source.knowledge_type else "Uncategorized"
        contributor_label = source.contributor.name if source.contributor else "(admin upload)"

        lines = [
            f"# {source.title or source.file_name or 'Untitled Source'}",
            f"- **ID:** `{source.id}`",
            f"- **Type:** {source.source_type or 'file'}",
            f"- **Knowledge type:** {kt_label}",
            f"- **Status:** {source.status}",
            f"- **Pages:** {page_count}" if page_count else "- **Pages:** (single block)",
            f"- **Contributed by:** {contributor_label}",
        ]
        if source.file_name:
            lines.append(f"- **File:** {source.file_name}")
        if source.url:
            lines.append(f"- **URL:** {source.url}")
        if source.created_at:
            lines.append(f"- **Added:** {source.created_at.strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("get_source_outline", query_arg="source_id")
    async def get_source_outline(source_id: str) -> str:
        """
        Heading-based outline (table of contents) of a raw source.

        Use this to navigate long documents by structure instead of guessing
        page numbers. Each entry shows title, level, page, and char range.
        Pass char_start/char_end downstream is not needed — use the page
        number with `get_source_pages` for the actual text.

        Args:
            source_id: The source UUID.
        """
        import uuid as uuid_mod

        from app.database import async_session_factory
        from app.database.models import Source

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None
        try:
            sid = uuid_mod.UUID(source_id)
        except ValueError:
            return f"Invalid source ID: {source_id}"

        async with async_session_factory() as session:
            source = await session.get(Source, sid)
            if not source:
                return f"Source not found: {source_id}"
            allowed_ids = await _get_allowed_source_ids(identity, session)
            if allowed_ids is not None and str(sid) not in allowed_ids:
                return "Access denied: this source is outside your knowledge scope."

        outline = source.outline_json or []
        if not outline:
            return "_(no outline — this document has no detectable headings)_"

        lines = ["# Outline\n"]
        def _walk(nodes: list[dict]):
            for n in nodes:
                indent = "  " * (max(0, n.get("level", 1) - 1))
                page = n.get("page")
                page_label = f" (page {page})" if page else ""
                lines.append(f"{indent}- {n.get('title', '')}{page_label}")
                if n.get("children"):
                    _walk(n["children"])
        _walk(outline)
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("get_source_pages", query_arg="source_id")
    async def get_source_pages(source_id: str, pages: str) -> str:
        """
        Read raw text of specific pages from a source.

        Args:
            source_id: The source UUID.
            pages: Page range — examples: "5-7", "3,8", "12", "1-3,9".

        Returns:
            Concatenated page text with `--- page N ---` separators. Use this
            for precise citations when the wiki summary has paraphrased away
            details you need.
        """
        import uuid as uuid_mod

        from app.database import async_session_factory
        from app.database.models import Source
        from app.services.source_outline import parse_page_range, slice_pages_by_range

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None
        try:
            sid = uuid_mod.UUID(source_id)
        except ValueError:
            return f"Invalid source ID: {source_id}"

        page_nums = parse_page_range(pages)
        if not page_nums:
            return f"Invalid page range: {pages!r}. Use formats like '5-7', '3,8', '12'."

        async with async_session_factory() as session:
            source = await session.get(Source, sid)
            if not source:
                return f"Source not found: {source_id}"
            allowed_ids = await _get_allowed_source_ids(identity, session)
            if allowed_ids is not None and str(sid) not in allowed_ids:
                return "Access denied: this source is outside your knowledge scope."

        full_text = source.full_text or ""
        offsets = source.page_offsets or []
        if not full_text or not offsets:
            return "_(no extractable text or page offsets for this source)_"

        slices = slice_pages_by_range(full_text, offsets, page_nums)
        if not slices:
            return f"No content for pages: {page_nums}"

        parts = []
        for s in slices:
            parts.append(f"--- page {s['page']} ---\n{s['content']}")
        return "\n\n".join(parts)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("search_source_content", query_arg="query")
    async def search_source_content(
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """
        Search inside the full text of raw source documents.

        Use this tool when the wiki summarizes or paraphases too much and you
        need to search across all raw text documents to locate specific terms,
        clauses, product codes, or quotes.

        Args:
            query: Exact keyword or phrase to search for in document contents.
            limit: Max sources to return matches for (default: 10).
            offset: Number of sources to skip for pagination (default: 0).

        Returns:
            Matched source documents, their matching page numbers, and highlighted context snippets.
        """
        import re
        from sqlalchemy import func, literal_column, select

        from app.database import async_session_factory
        from app.database.models import Source
        from app.services.mcp_auth_service import apply_scope_filter

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        query = query.strip()
        if not query:
            return "Error: query parameter must not be empty."

        STOPWORDS = {
            "của", "có", "chưa", "ở", "tại", "là", "gì", "nào", "bao", "nhiêu", "ai", "không",
            "về", "cho", "với", "trong", "tìm", "kiểm", "tra", "xem", "hãy", "thì", "được", "ra",
            "sao", "và", "các", "những", "một", "the", "a", "an", "is", "are", "what", "where",
            "who", "when", "why", "how", "does", "do", "did", "exist", "already", "for", "in",
            "on", "of", "to", "and", "or"
        }

        # Extract tokens
        raw_words = re.findall(r"[\w\-]+", query)
        clean_terms = [w for w in raw_words if w.lower() not in STOPWORDS and len(w) > 1]

        async with async_session_factory() as session:
            tsv = literal_column("to_tsvector('simple', f_unaccent(sources.full_text))")

            # 1. Try strict websearch_to_tsquery first
            tsq = func.websearch_to_tsquery("simple", func.f_unaccent(query))
            stmt = select(Source).where(
                Source.status == "ready",
                tsv.op("@@")(tsq),
            ).order_by(func.ts_rank(tsv, tsq).desc())
            stmt = apply_scope_filter(stmt, identity).offset(offset).limit(limit)
            sources = (await session.execute(stmt)).scalars().all()

            # 2. Fallback: try keyword OR/AND tsquery if natural language query failed
            if not sources and clean_terms:
                kw_query_str = " | ".join(clean_terms)
                try:
                    tsq_kw = func.to_tsquery("simple", func.f_unaccent(kw_query_str))
                    stmt2 = select(Source).where(
                        Source.status == "ready",
                        tsv.op("@@")(tsq_kw),
                    ).order_by(func.ts_rank(tsv, tsq_kw).desc())
                    stmt2 = apply_scope_filter(stmt2, identity).offset(offset).limit(limit)
                    sources = (await session.execute(stmt2)).scalars().all()
                except Exception:
                    pass

            # 3. Fallback: ILIKE substring scan for primary keywords
            if not sources and clean_terms:
                primary_terms = [t for t in clean_terms if len(t) > 2]
                if primary_terms:
                    ilike_clauses = [
                        func.f_unaccent(Source.full_text).ilike(f"%{t.lower()}%")
                        for t in primary_terms[:3]
                    ]
                    from sqlalchemy import or_
                    stmt3 = select(Source).where(
                        Source.status == "ready",
                        or_(*ilike_clauses),
                    )
                    stmt3 = apply_scope_filter(stmt3, identity).offset(offset).limit(limit)
                    sources = (await session.execute(stmt3)).scalars().all()

        if not sources:
            return f"No document content matches found for: \"{query}\""

        # Build search tokens for highlighting
        search_tokens = [t for t in clean_terms if len(t) > 1] or [query]

        lines = [f"**Content search results for: \"{query}\"**\n"]
        for s in sources:
            text = s.full_text or ""
            offsets = s.page_offsets or []
            title = s.title or s.file_name or s.url or "Untitled Source"

            # Score and extract best snippets
            scored_snippets = []
            text_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            for ln in text_lines:
                hits = [t for t in search_tokens if t.lower() in ln.lower()]
                if hits:
                    score = sum(len(h) for h in hits)
                    # Find char offset to determine page
                    start_char = text.find(ln)
                    page_num = 1
                    if offsets and start_char >= 0:
                        for idx, off in enumerate(offsets):
                            if start_char < off:
                                page_num = idx
                                break
                            page_num = len(offsets)

                    # Highlight all matched tokens
                    hl_line = ln
                    for h in sorted(hits, key=len, reverse=True):
                        hl_line = re.sub(
                            re.escape(h),
                            lambda m: f"**{m.group(0)}**",
                            hl_line,
                            flags=re.IGNORECASE,
                        )
                    scored_snippets.append((score, page_num, hl_line))

            scored_snippets.sort(key=lambda x: x[0], reverse=True)

            lines.append(f"### {title} (ID: `{s.id}`)")
            if scored_snippets:
                for score, p_num, snip in scored_snippets[:5]:
                    lines.append(f"- **Page {p_num}**: {snip}")
            else:
                lines.append("- Keyword matches found in full text.")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Source/Type browsing
    # =========================================================================

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("list_sources")
    async def list_sources(
        status: str = "ready",
        knowledge_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """
        List raw source documents with optional filters and text search.

        Args:
            status: "ready", "processing", "error", or "all".
            knowledge_type: Filter by KnowledgeType slug.
            query: Optional text query (case-insensitive) to search in title, filename, or URL.
            limit: Max sources to return (default: 20).
            offset: Number of sources to skip for pagination (default: 0).
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.database import async_session_factory
        from app.database.models import KnowledgeType, Source
        from app.services.mcp_auth_service import apply_scope_filter

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        async with async_session_factory() as session:
            stmt = (
                select(Source)
                .options(selectinload(Source.knowledge_type))
                .order_by(Source.created_at.desc())
            )
            if status != "all":
                stmt = stmt.where(Source.status == status)
            if knowledge_type:
                kt_id = (await session.execute(
                    select(KnowledgeType.id).where(KnowledgeType.slug == knowledge_type)
                )).scalar()
                if kt_id:
                    stmt = stmt.where(Source.knowledge_type_id == kt_id)
            if query:
                stmt = stmt.where(
                    Source.title.ilike(f"%{query}%") |
                    Source.file_name.ilike(f"%{query}%") |
                    Source.url.ilike(f"%{query}%")
                )
            stmt = apply_scope_filter(stmt, identity).offset(offset).limit(limit)
            sources = (await session.execute(stmt)).scalars().all()

        if not sources:
            msg = "No documents found"
            if knowledge_type:
                msg += f" of type '{knowledge_type}'"
            if query:
                msg += f" matching '{query}'"
            return msg + "."

        from collections import defaultdict
        by_type = defaultdict(list)
        for s in sources:
            kt_name = s.knowledge_type.name if s.knowledge_type else "Uncategorized"
            by_type[kt_name].append(s)

        lines = [f"**Knowledge Base — {len(sources)} document(s)**\n"]
        for kt_name, type_sources in by_type.items():
            lines.append(f"\n### {kt_name} ({len(type_sources)})")
            for s in type_sources:
                title = s.title or s.file_name or s.url or "Untitled"
                lines.append(f"- **{title}** (ID: `{s.id}`)")
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("list_knowledge_types")
    async def list_knowledge_types() -> str:
        """
        List knowledge types (admin-defined classifications) accessible to the caller.
        """
        from sqlalchemy import func, select

        from app.database import async_session_factory
        from app.database.models import KnowledgeType, Source

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        async with async_session_factory() as session:
            stmt = (
                select(KnowledgeType, func.count(Source.id).label("doc_count"))
                .outerjoin(
                    Source,
                    (Source.knowledge_type_id == KnowledgeType.id) & (Source.status == "ready"),
                )
                .group_by(KnowledgeType.id)
                .order_by(KnowledgeType.sort_order, KnowledgeType.name)
            )
            rows = (await session.execute(stmt)).all()

        if not rows:
            return "No knowledge types have been defined yet."

        allowed_types = identity.allowed_knowledge_types

        lines = ["**Knowledge Types**\n"]
        for kt, doc_count in rows:
            if allowed_types is not None and kt.slug not in allowed_types:
                continue
            line = f"- **{kt.name}** (slug: `{kt.slug}`, {doc_count} doc(s))"
            if kt.description:
                line += f" — {kt.description}"
            lines.append(line)

        if len(lines) == 1:
            return "No accessible knowledge types found for your scope."
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("get_knowledge_type_docs", query_arg="knowledge_type_slug")
    async def get_knowledge_type_docs(knowledge_type_slug: str, limit: int = 10) -> str:
        """
        List documents belonging to a specific knowledge type.

        Args:
            knowledge_type_slug: Type slug (use `list_knowledge_types` to find).
            limit: Max documents to return (default: 10).
        """
        from sqlalchemy import select

        from app.database import async_session_factory
        from app.database.models import KnowledgeType, Source
        from app.services.mcp_auth_service import apply_scope_filter

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        if (identity.allowed_knowledge_types is not None
                and knowledge_type_slug not in identity.allowed_knowledge_types):
            return (
                f"Access denied: knowledge type '{knowledge_type_slug}' is outside your scope. "
                f"Use `list_knowledge_types` to see what types you can access."
            )

        async with async_session_factory() as session:
            kt = (await session.execute(
                select(KnowledgeType).where(KnowledgeType.slug == knowledge_type_slug)
            )).scalar_one_or_none()
            if not kt:
                return f"Knowledge type '{knowledge_type_slug}' not found."

            stmt = (
                select(Source)
                .where(Source.knowledge_type_id == kt.id, Source.status == "ready")
                .order_by(Source.created_at.desc())
            )
            stmt = apply_scope_filter(stmt, identity).limit(limit)
            sources = (await session.execute(stmt)).scalars().all()

        if not sources:
            return f"No documents found for knowledge type: **{kt.name}**"

        lines = [f"**{kt.name}** — {len(sources)} document(s)\n"]
        for s in sources:
            title = s.title or s.file_name or s.url or "Untitled"
            lines.append(f"- **{title}** (ID: `{s.id}`)")
        return "\n".join(lines)

    # =========================================================================
    # Write — edit / create wiki pages (published immediately, no review)
    # =========================================================================

    @kb_tool(mcp, requires=CAN_CONTRIBUTE_WIKI)
    @logged_tool("edit_wiki_page", query_arg="slug")
    async def edit_wiki_page(
        slug: str,
        content_md: str,
        note: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        base_version: Optional[int] = None,
        allow_row_removal: bool = False,
    ) -> str:
        """
        Edit an existing wiki page. Published immediately as a new page version.

        Read the page with read_wiki_page() first and send the FULL new content
        (not a diff). Always confirm the change with the user before calling.

        Args:
            slug: Target page slug (e.g. "concept/fire-safety").
            content_md: Full new content in Markdown (max 50,000 chars).
            note: One-line explanation of what changed and why.
            scope_type: "global" or "department". Required only when the same
                slug exists in several scopes.
            scope_id: Department UUID when scope_type is "department".
            base_version: Page version your edit is based on (from
                read_wiki_page). If the page changed since, the edit is refused
                so you can re-read and re-apply.
            allow_row_removal: The edit is refused when it drops table rows of
                the current page. Set True only when the user explicitly asked
                to delete those rows.
        """
        import uuid as _uuid

        from app.database import async_session_factory
        from app.database.models import Employee, WikiPage
        from app.services import wiki_service
        from app.services.wiki_draft_publish import publish_draft
        from app.services.wiki_write_guard import check_agent_write

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        if not slug or not content_md.strip():
            return "Error: slug and content_md are required."
        if slug in (wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG, wiki_service.HOT_SLUG):
            return "Error: reserved pages cannot be edited."
        if len(content_md) > 50_000:
            return "Error: content_md exceeds 50,000 character limit."
        if scope_type and scope_type not in ("global", "department"):
            return "Error: scope_type must be global or department."

        sid: Optional[_uuid.UUID] = None
        if scope_id:
            try:
                sid = _uuid.UUID(scope_id)
            except ValueError:
                return "Error: scope_id must be a valid UUID."

        async with async_session_factory() as session:
            if scope_type:
                page = await wiki_service.get_page_by_slug(
                    session, slug, scope_type=scope_type, scope_id=sid,
                )
            else:
                # No explicit scope: require the slug to be unambiguous.
                matches = (await session.execute(
                    sa_select(WikiPage).where(WikiPage.slug == slug)
                )).scalars().all()
                if len(matches) > 1:
                    scopes = ", ".join(
                        f"{m.scope_type}:{m.scope_id or 'global'}" for m in matches
                    )
                    return (
                        f"Error: slug '{slug}' exists in multiple scopes ({scopes}). "
                        "Re-call with scope_type and scope_id."
                    )
                page = matches[0] if matches else None
            if not page:
                return f"Page '{slug}' not found. Use search_wiki() or list_wiki_pages() to find the slug."

            employee = await session.get(Employee, identity.employee_id)
            if not employee:
                return "Error: employee not found."

            if not (
                await _can_review_page(session, employee, page)
                or await _can_contribute_to_page(session, employee, page)
            ):
                return f"Error: insufficient permission to edit '{slug}'."

            if not allow_row_removal:
                refusal = check_agent_write(page.content_md, content_md)
                if refusal:
                    return f"Error: {refusal}"

            effective_base = base_version if base_version is not None else page.version
            if (
                effective_base is not None
                and page.version is not None
                and effective_base > page.version
            ):
                return f"Error: base_version {effective_base} is ahead of current page v{page.version}."

            draft = await wiki_service.create_draft(
                session,
                page_id=page.id,
                author_id=employee.id,
                content_md=content_md.strip(),
                note=note,
                source="mcp_claude_desktop",
                base_version=effective_base,
            )
            draft.page = page
            try:
                published = await publish_draft(session, draft, employee)
            except wiki_service.DraftConflictError as e:
                await session.rollback()
                return (
                    f"Error: page '{slug}' is now v{e.current_version} (your edit was based on "
                    f"v{e.base_version}). Re-read the page and re-apply your change."
                )
            await session.commit()

        return f"Page `{slug}` updated to v{published.version}. Note: {note or '(none)'}"

    @kb_tool(mcp, requires=CAN_CONTRIBUTE_WIKI)
    @logged_tool("create_wiki_page", query_arg="slug")
    async def create_wiki_page(
        slug: str,
        title: str,
        content_md: str,
        page_type: str = "concept",
        knowledge_type_slugs: Optional[list[str]] = None,
        scope_type: str = "global",
        scope_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> str:
        """
        Create a new wiki page. Published immediately.

        Use search_wiki() first to make sure a similar page does not already
        exist. Always confirm with the user before calling.

        Args:
            slug: Unique URL slug, no whitespace, not a reserved slug (_index, _log).
            title: Display title.
            content_md: Full Markdown content (max 50,000 chars).
            page_type: One of entity | concept | source | topic.
            knowledge_type_slugs: KB taxonomy tags (controls RBAC visibility).
            scope_type: "global" or "department".
            scope_id: Department UUID when scope_type is "department".
            note: One-line description of why this page should exist.
        """
        import uuid as _uuid

        from app.database import async_session_factory
        from app.database.models import Employee
        from app.services import wiki_service
        from app.services.wiki_draft_publish import publish_draft

        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        if not slug or not title or not content_md.strip():
            return "Error: slug, title, and content_md are required."
        slug = slug.strip()
        if slug in (wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG, wiki_service.HOT_SLUG):
            return "Error: this slug is reserved."
        if len(content_md) > 50_000:
            return "Error: content_md exceeds 50,000 character limit."
        if any(c.isspace() for c in slug):
            return "Error: slug must not contain whitespace."
        if page_type not in wiki_service.PAGE_TYPES:
            return f"Error: page_type must be one of {sorted(wiki_service.PAGE_TYPES)}."
        if scope_type not in ("global", "department"):
            return "Error: scope_type must be global or department."

        sid: Optional[_uuid.UUID] = None
        if scope_id:
            try:
                sid = _uuid.UUID(scope_id)
            except ValueError:
                return "Error: scope_id must be a valid UUID."
        if scope_type == "department" and sid is None:
            return "Error: scope_id is required when scope_type is department."
        if scope_type == "global":
            sid = None

        async with async_session_factory() as session:
            employee = await session.get(Employee, identity.employee_id)
            if not employee:
                return "Error: employee not found."

            if employee.role != "admin":
                from app.services.permission_engine import (
                    _get_user_permissions,
                    has_any_permission,
                )
                perms = _get_user_permissions(employee)
                if scope_type == "department":
                    if "wiki:write:all" not in perms and not (
                        "wiki:write:own_dept" in perms and sid in employee.department_ids
                    ):
                        return "Error: insufficient permission to create pages in this department."
                elif not has_any_permission(list(perms), "wiki", "write"):
                    return "Error: insufficient permission to create wiki pages."

            existing = await wiki_service.get_page_by_slug(
                session, slug, scope_type=scope_type, scope_id=sid,
            )
            if existing is not None:
                return (
                    f"Error: page '{slug}' already exists in {scope_type}. "
                    "Use edit_wiki_page() to change it instead."
                )

            suggested_metadata = {
                "slug": slug, "title": title, "page_type": page_type,
                "knowledge_type_slugs": list(knowledge_type_slugs or []),
                "scope_type": scope_type,
                "scope_id": str(sid) if sid else None,
            }
            draft = await wiki_service.create_draft(
                session,
                page_id=None,
                author_id=employee.id,
                content_md=content_md.strip(),
                note=note,
                source="mcp_claude_desktop",
                base_version=None,
                draft_kind="create",
                suggested_metadata=suggested_metadata,
            )
            try:
                page = await publish_draft(session, draft, employee)
            except (wiki_service.CreateDraftSlugConflict, ValueError) as e:
                await session.rollback()
                return f"Error: could not create page '{slug}': {e}"
            await session.commit()

        return f"Page `{slug}` created at v{page.version}. Note: {note or '(none)'}"

    # =========================================================================
    # Spreadsheet / Tabular Analytics via DuckDB
    # =========================================================================

    @kb_tool(mcp, requires=ANY_AUTHENTICATED)
    @logged_tool("query_table", query_arg="sql_query")
    async def query_table(
        source_id: str,
        sql_query: str,
        max_rows: int = 50,
    ) -> str:
        """
        Execute a safe, read-only SQL query against an uploaded spreadsheet (Excel or CSV).

        Args:
            source_id: UUID of the source spreadsheet document.
            sql_query: SQL SELECT query (e.g. `SELECT name, rank FROM can_bo WHERE unit = 'Đội 1'`).
                       Sheet names are registered as tables (unaccented, lowercase, underscores).
            max_rows: Maximum rows to return (default: 50, max: 100).

        Returns:
            Markdown table of query results or an informative error message.
        """
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        import uuid
        from app.database import async_session_factory
        from app.database.models import Source
        from app.services.storage_service import storage_service
        from app.services.table_query_service import TableQueryService

        try:
            source_uuid = uuid.UUID(source_id)
        except ValueError:
            return f"Invalid source_id format: '{source_id}'."

        max_rows = min(max(1, max_rows), 100)

        async with async_session_factory() as session:
            source = await session.get(Source, source_uuid)
            if not source:
                return f"Source '{source_id}' not found."

            if not source.minio_key:
                return f"Source '{source_id}' has no stored file."

            # Verify permissions/scope
            allowed_ids = await _get_allowed_source_ids(identity, session)
            if allowed_ids is not None and str(source.id) not in allowed_ids:
                return f"Access denied to source '{source_id}'."

            file_bytes = storage_service.download_file(source.minio_key)
            if not file_bytes:
                return f"Failed to retrieve file content for source '{source_id}'."

            file_name = source.file_name or "table.xlsx"

        query_service = TableQueryService(default_max_rows=max_rows)
        res = query_service.query_excel_bytes(
            file_bytes=file_bytes,
            file_name=file_name,
            sql_query=sql_query,
            max_rows=max_rows,
        )

        if not res["success"]:
            return f"❌ Lỗi truy vấn bảng: {res['error']}"

        cols = res["columns"]
        rows = res["rows"]
        if not rows:
            return f"Truy vấn thành công nhưng không có dòng nào thỏa mãn: `{sql_query}`"

        lines = [
            f"**Kết quả truy vấn bảng tính ({len(rows)} dòng) từ `{file_name}`**:\n",
            "| " + " | ".join(cols) + " |",
            "| " + " | ".join(["---"] * len(cols)) + " |",
        ]
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")

        return "\n".join(lines)
