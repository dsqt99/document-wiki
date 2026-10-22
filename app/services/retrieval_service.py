"""
Retrieval Service — Advanced Hybrid, Graph-Expanded & Reranked Retrieval Orchestrator.

Combines:
1. Exact Routing: resolves "Điều X <số hiệu văn bản>" queries against the structured-unit table.
2. Dual-Arm Hybrid Search: Cosine vector kNN + Vietnamese-tokenized BM25/FTS via RRF.
3. 1-Hop Graph Neighbor Expansion: Traverses LegalRelation edges (amendments, guidances, repeals)
   to pull in cross-document context from the legal knowledge graph.
4. Configured Wiki Reranking: Shares the portal's model and strict threshold;
   provider failures preserve retrieval order without fabricated relevance scores.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Optional

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import configure_mappers, selectinload

from app.database.models import LegalRelation, LegalRelationType, LegalUnit, WikiPage
from app.services.legal_route_service import route_exact_legal_query
from app.services.wiki_reranker import configured_rank_candidates, search_metadata
from app.utils.text import clip_text


async def expand_graph_neighbors(
    session: AsyncSession,
    page_ids: list[uuid.UUID],
    max_neighbors_per_node: int = 5,
    allowed_source_ids: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """
    Expand 1-hop relations on the legal knowledge graph for the given wiki page IDs.

    Finds the underlying LegalUnits, then queries incoming & outgoing LegalRelations
    (e.g., sua_doi, bo_sung, thay_the, bai_bo, huong_dan, quy_dinh, can_cu).
    Returns deduplicated list of related legal nodes.

    `allowed_source_ids` (None = không giới hạn) là tập nguồn người dùng được đọc:
    điều khoản liên quan thuộc nguồn ngoài tập này bị bỏ, kể cả tiêu đề, nội dung
    và trích dẫn, để phần văn bản liên quan không lộ tài liệu ngoài phạm vi.
    """
    if not page_ids:
        return []

    # 1. Fetch LegalUnits associated with the given wiki_page_ids
    unit_stmt = select(LegalUnit).where(LegalUnit.wiki_page_id.in_(page_ids))
    res = await session.execute(unit_stmt)
    units = res.scalars().all()
    if not units:
        return []

    unit_ids = [u.id for u in units]
    unit_map = {u.id: u for u in units}
    unit_doc_art_map = {(u.doc_number, u.unit_number): u for u in units if u.doc_number}

    # 2. Query both outgoing and incoming relations
    conditions = [
        LegalRelation.source_unit_id.in_(unit_ids),
        LegalRelation.target_unit_id.in_(unit_ids),
    ]

    for (d_num, a_num) in unit_doc_art_map.keys():
        conditions.append(
            (LegalRelation.target_doc_number == d_num) & (LegalRelation.target_article_number == a_num)
        )

    configure_mappers()  # backref attributes (LegalRelation.source_unit) exist only after configure
    rel_stmt = (
        select(LegalRelation)
        .options(
            selectinload(LegalRelation.source_unit),
            selectinload(LegalRelation.target_unit),
        )
        .where(
            or_(*conditions),
            LegalRelation.is_effective.is_(True),
        )
        .limit(max_neighbors_per_node * len(units) * 2)
    )
    rel_res = await session.execute(rel_stmt)
    relations = rel_res.scalars().all()

    allowed_set = None if allowed_source_ids is None else {str(x) for x in allowed_source_ids}

    def _readable(u) -> bool:
        if allowed_set is None:
            return True
        return u is not None and str(u.source_id) in allowed_set

    neighbors: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for rel in relations:
        rel_type_str = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)
        
        # Determine direction and neighbor details
        if rel.target_unit_id in unit_map or (rel.target_doc_number, rel.target_article_number) in unit_doc_art_map:
            # Incoming: another document modified/guided this unit
            source_u = rel.source_unit
            if not _readable(source_u):
                # Trích dẫn và nội dung đến từ văn bản nguồn của quan hệ.
                continue
            doc_num = (source_u.doc_number if source_u else None) or "Văn bản liên quan"
            art_num = (source_u.unit_number if source_u else None) or ""
            title = (source_u.title if source_u else None) or ""
            content = (source_u.content if source_u else None) or ""
            direction = "incoming"
            target_unit_ref = source_u
        else:
            # Outgoing: this unit references/guides another unit
            target_u = rel.target_unit
            if target_u is not None and not _readable(target_u):
                continue
            doc_num = (target_u.doc_number if target_u else None) or rel.target_doc_number or ""
            art_num = (target_u.unit_number if target_u else None) or rel.target_article_number or ""
            title = (target_u.title if target_u else None) or ""
            content = (target_u.content if target_u else None) or ""
            direction = "outgoing"
            target_unit_ref = target_u

        dedup_key = (doc_num, art_num, rel_type_str, direction)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        neighbors.append({
            "unit_id": str(target_unit_ref.id) if target_unit_ref else None,
            "doc_number": doc_num,
            "article_number": art_num,
            "relation_type": rel_type_str,
            "direction": direction,
            "title": title,
            "content": content,
            "quote_context": rel.quote_context,
            "wiki_page_id": str(target_unit_ref.wiki_page_id) if target_unit_ref and getattr(target_unit_ref, "wiki_page_id", None) else None,
        })

    return neighbors


def format_graph_neighbors_section(neighbors: list[dict[str, Any]]) -> str:
    """Format 1-hop graph neighbors into clear markdown section."""
    if not neighbors:
        return ""

    lines = [
        "🔗 **VĂN BẢN & ĐIỀU KHOẢN LIÊN QUAN**:\n"
    ]
    
    label_map = {
        "sua_doi": "Sửa đổi, bổ sung",
        "bo_sung": "Bổ sung",
        "thay_the": "Thay thế",
        "bai_bo": "Bãi bỏ",
        "huong_dan": "Hướng dẫn thi hành",
        "can_cu": "Căn cứ ban hành",
        "dan_chieu": "Dẫn chiếu",
        "quy_dinh": "Quy định liên quan",
    }

    for n in neighbors:
        rel_label = label_map.get(n["relation_type"], n["relation_type"])
        doc = n.get("doc_number", "")
        art = n.get("article_number")
        art_ref = f" - Điều {art}" if art else ""
        title = f": {n['title']}" if n.get("title") else ""
        if n.get("direction") == "incoming":
            lines.append(f"- Bị tác động bởi **{doc}{art_ref}** ({rel_label}){title}")
        else:
            lines.append(f"- Văn bản này tác động đến **{doc}{art_ref}** ({rel_label}){title}")
        if n.get("quote_context"):
            lines.append(f"  *Trích yếu*: \"{clip_text(n['quote_context'], 300)}\"")

    return "\n".join(lines)


MIN_SIM_FLOOR = 0.35


def merge_sequential_chunks(hits: list[dict], max_gap_chars: int = 200) -> list[dict]:
    """Merge consecutive chunks from the same source or page into continuous passages."""
    if not hits or len(hits) <= 1:
        return hits

    merged: list[dict] = []
    # Group by parent id
    by_parent: dict[Any, list[dict]] = {}
    for h in hits:
        parent_id = None
        if "page" in h and h["page"]:
            parent_id = ("page", getattr(h["page"], "id", None))
        elif "source" in h and h["source"]:
            parent_id = ("source", getattr(h["source"], "id", None))
        by_parent.setdefault(parent_id, []).append(h)

    for parent_id, group in by_parent.items():
        if len(group) == 1 or parent_id is None:
            merged.extend(group)
            continue

        # Sort by chunk_index
        def _get_idx(item):
            c = item.get("chunk")
            if c and hasattr(c, "chunk_index"):
                return c.chunk_index
            return item.get("chunk_index", 0)

        group.sort(key=_get_idx)
        cur = dict(group[0])
        for nxt in group[1:]:
            cur_idx = cur.get("chunk_index_end", _get_idx(cur))
            nxt_idx = _get_idx(nxt)
            if nxt_idx == cur_idx + 1:
                # Sequential chunk: merge text
                c_cur = cur.get("chunk")
                c_nxt = nxt.get("chunk")
                if c_cur and c_nxt and hasattr(c_cur, "text") and hasattr(c_nxt, "text"):
                    # A search passage is not a persisted chunk. Mutating the ORM
                    # row would autoflush an UPDATE during the next graph/metadata read.
                    chunk = SimpleNamespace(**{
                        key: getattr(c_cur, key, None) for key in
                        ("source_id", "chunk_index", "model_spec_id", "page_number", "start_char", "content_hash")
                    })
                    chunk.text = f"{c_cur.text}\n\n{c_nxt.text}"
                    chunk.end_char = getattr(c_nxt, "end_char", None)
                    chunk.page_end = getattr(c_nxt, "page_end", None) or getattr(c_nxt, "page_number", None)
                    cur["chunk"] = chunk
                    cur["chunk_index_end"] = nxt_idx
                    cur["rrf"] = max(cur.get("rrf", 0.0), nxt.get("rrf", 0.0))
                elif "chunk_text" in cur and "chunk_text" in nxt:
                    cur["chunk_text"] = f"{cur['chunk_text']}\n\n{nxt['chunk_text']}"
                    cur["chunk_index_end"] = nxt_idx
                    cur["rrf"] = max(cur.get("rrf", 0.0), nxt.get("rrf", 0.0))
                else:
                    merged.append(cur)
                    cur = dict(nxt)
            else:
                merged.append(cur)
                cur = dict(nxt)
        merged.append(cur)

    # Sort merged results by rrf descending
    merged.sort(key=lambda x: x.get("rrf", 0.0), reverse=True)
    return merged


async def unified_search(
    session: AsyncSession,
    query: str,
    query_embedding: Optional[list[float]],
    top_k: int = 10,
    allowed_kt_slugs: Optional[list[str]] = None,
    department_ids: Optional[list[uuid.UUID]] = None,
    project_ids: Optional[list[uuid.UUID]] = None,
    all_scopes: bool = False,
    allowed_source_ids: Optional[Any] = None,
    apply_reranker: bool = True,
    apply_mmr: bool = True,
    check_out_of_scope: bool = False,
    clearance: Optional[str] = None,
    page_filter=None,
    personal_owner_id=None,
) -> dict[str, Any]:
    """Unified multi-stage search orchestrator:

    1. Exact legal routing: checks for article & doc number match.
    2. Fault-tolerant hybrid search (vector + vi-tokenized FTS) over wiki pages & source chunks.
    3. Winning-chunk text extraction & threshold filtering.
    4. 1-hop graph expansion over legal knowledge graph.
    5. Configured reranking with the portal's threshold and honest hybrid fallback.
    """
    from app.services import wiki_service

    failed_arms: list[str] = []

    async def _arm(name: str, coro_fn):
        """Run one arm inside a savepoint so a failing statement does not poison
        the shared session for later arms. Arms run one after another: an
        AsyncSession is not safe for concurrent use."""
        try:
            async with session.begin_nested():
                return await coro_fn()
        except Exception as e:
            logger.warning(f"unified_search: {name} arm failed: {e}")
            failed_arms.append(name)
            return None

    # 1. Exact document-number routing ("Điều X [khoản Y] <số hiệu>")
    exact_route_res = await _arm(
        "exact",
        lambda: route_exact_legal_query(session, query, allowed_source_ids=allowed_source_ids),
    )

    # 2. Hybrid search arms
    fetch_k = top_k * 2 if apply_reranker else top_k
    wiki_hits = await _arm("wiki", lambda: wiki_service.search_pages_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=fetch_k,
        allowed_kt_slugs=allowed_kt_slugs,
        department_ids=department_ids,
        project_ids=project_ids,
        all_scopes=all_scopes,
        clearance=clearance,
        page_filter=page_filter,
        personal_owner_id=personal_owner_id,
    )) or []
    source_hits = await _arm("source", lambda: wiki_service.search_source_chunks_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=fetch_k,
        allowed_source_ids=allowed_source_ids,
        clearance=clearance,
    )) or []

    oos_hits: list = []
    if check_out_of_scope and not all_scopes:
        oos_hits = await _arm("out_of_scope", lambda: wiki_service.search_pages_semantic(
            session,
            query_embedding=query_embedding,
            top_k=5,
            department_ids=department_ids,
            project_ids=project_ids,
            inverse_scope=True,
            clearance=clearance,
        )) or []

    # 3. Confidence Threshold Floor (drop weak vector-only noise, retain lexical matches)
    def _passes(hit: dict) -> bool:
        if hit.get("fts_matched"):
            return True
        cos = hit.get("cosine")
        return cos is not None and cos >= MIN_SIM_FLOOR

    wiki_hits = [h for h in wiki_hits if _passes(h)]
    source_hits = [h for h in source_hits if _passes(h)]

    # 4. Adjacent Sequential Chunk Merging
    source_hits = merge_sequential_chunks(source_hits)

    total_candidates = len(wiki_hits) + len(source_hits)

    # 5. 1-Hop Graph Neighbor Expansion from Top Wiki Pages
    top_page_ids = [h["page"].id for h in wiki_hits[:5] if "page" in h]
    graph_neighbors = []
    if top_page_ids:
        graph_neighbors = await _arm(
            "graph", lambda: expand_graph_neighbors(
                session, top_page_ids, allowed_source_ids=allowed_source_ids,
            )
        ) or []

    # 6. Prepare candidate texts for reranking (using WINNING CHUNKS instead of whole 50KB page)
    candidates: list[dict[str, Any]] = []

    for h in wiki_hits:
        p = h["page"]
        chunk_text = h.get("chunk_text")
        if not chunk_text:
            body = getattr(p, "content_md", "") or getattr(p, "content", "")
            chunk_text = body[:1500]
        heading = h.get("heading_path") or ""
        header = f"{p.title} — {heading}" if heading else p.title
        text = f"[{header}]\n\n{chunk_text}"
        candidates.append({
            "kind": "wiki", "hit": h, "text": text,
            "rrf": h.get("rrf", 0.0), "exact": bool(h.get("exact_match")),
        })

    for h in source_hits:
        c = h.get("chunk")
        text = (getattr(c, "text", "") or getattr(c, "content", "") or "") if c else ""
        s = h.get("source")
        doc_title = (getattr(s, "title", "") or getattr(s, "file_name", "") or "") if s else ""
        if doc_title:
            text = f"[{doc_title}]\n\n{text}"
        candidates.append({
            "kind": "source", "hit": h, "text": text,
            "rrf": h.get("rrf", 0.0), "exact": bool(h.get("exact_match")),
        })

    # Retrieval order (best RRF first) — the reranker's prior and its fallback.
    candidates.sort(key=lambda c: c["rrf"], reverse=True)

    # Exact legal routing stays separate. For search candidates use the same
    # configured model/strict threshold as the portal, retaining the lexical
    # prior if scoring fails. ``apply_mmr`` remains accepted for compatibility.
    candidates.sort(key=lambda c: c["exact"], reverse=True)
    result = await configured_rank_candidates(session, query, candidates, enabled=apply_reranker)
    final_ranked = []
    for cand in result.items[:top_k]:
        hit = dict(cand["hit"])
        if result.mode == 'rerank':
            score = cand['rerank_score']
            hit['rerank_score'] = score
        else:
            hit.pop('rerank_score', None)
            score = cand['rrf']
        final_ranked.append((cand['kind'], score, hit))

    return {
        "exact_match": exact_route_res,
        "ranked_results": final_ranked,
        "graph_neighbors": graph_neighbors,
        "out_of_scope_hits": oos_hits,
        "failed_arms": failed_arms,
        "rerank_mode": result.mode,
        "search": search_metadata(result, lexical_fallback=query_embedding is None,
                                  candidate_count=total_candidates),
        "total_candidates": total_candidates,
    }
