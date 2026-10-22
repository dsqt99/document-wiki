"""MCP tools of the Document Wiki knowledge base (06 §1.3, §1.4, §1.7).

Every tool resolves the caller first (``_get_identity``) and returns Markdown.
``_get_identity`` / ``_get_allowed_source_ids`` are looked up on this module at
call time, the DB session factory and the wiki service are imported lazily, so
tests can patch them.
"""

from __future__ import annotations

import asyncio
import bisect
import logging
import os
import posixpath
import re
import sys
import unicodedata
import uuid
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from sqlalchemy import and_, any_, case, exists, func, literal, not_, or_, select
from sqlalchemy.orm import aliased, contains_eager, selectinload

from app.mcp import permissions_compat
from app.mcp import knowledge_payloads as payloads
from app.mcp.logging import current_identity, logged_tool
from app.services import security_label
from app.utils.text import clip_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Messages and constants
# ---------------------------------------------------------------------------

AUTH_REQUIRED_MSG = (
    "Authentication required. Configure your MCP client (for example Claude Desktop) to send the "
    "header `Authorization: Bearer ark_…` with the personal MCP token issued from the Document Wiki portal."
)
INVALID_TOKEN_MSG = "Invalid or inactive MCP token. Contact your administrator."

_SSO_ERRORS = {
    "sso_disabled": "SSO tokens are not accepted by this server. Use an Document Wiki MCP token (ark_…).",
    "sso_token_expired": "SSO token expired. Sign in again.",
    "sso_token_invalid": "Invalid SSO token.",
    "sso_client_not_allowed": "This SSO client may not call Document Wiki MCP (see SSO_MCP_CLIENTS).",
    "sso_email_conflict": "The SSO account's email belongs to another linked Document Wiki account.",
    "sso_email_unverified": (
        "The SSO account's email is not verified, so it cannot be linked to the existing Document Wiki account."
    ),
    "sso_inactive": "Document Wiki account is inactive. Contact your administrator.",
}

_TRUTHY = {"true", "1", "yes"}
_TOP_LEVEL = security_label.LEVELS[-1]

MIN_SIM_FLOOR = 0.30
WIKI_CONTENT_MAX_CHARS = 50_000
SKILL_FILE_MAX_CHARS = 60000
SKILL_TEXT_EXTENSIONS = (
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".xml", ".html",
    ".py", ".js", ".ts", ".sh", ".sql", ".ini", ".cfg",
)
_FENCE_LANG = {
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".csv": "csv", ".xml": "xml",
    ".html": "html", ".py": "python", ".sql": "sql",
}
_BUNDLE_CACHE_MAX = 256
_bundle_cache: dict[tuple, dict] = {}

ACCESS_DENIED_SOURCE = "Access denied: this source is outside your knowledge scope."
NO_SCOPE_MSG = "Bạn chưa được cấp quyền truy cập văn bản nào."

RELATION_LABELS = {
    "sua_doi": "Sửa đổi",
    "bo_sung": "Bổ sung",
    "thay_the": "Thay thế",
    "bai_bo": "Bãi bỏ",
    "huong_dan": "Hướng dẫn",
    "can_cu": "Căn cứ",
    "dan_chieu": "Dẫn chiếu",
}

_VI_STOPWORDS = {
    "và", "của", "là", "có", "các", "những", "được", "cho", "trong", "với", "theo", "về", "này",
    "đó", "khi", "thì", "mà", "để", "từ", "tại", "trên", "dưới", "một", "hay", "hoặc", "nào",
    "gì", "ai", "bao", "nhiêu", "như", "thế", "nếu", "đã", "sẽ", "đang", "không", "bị", "do",
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "what", "how",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _this():
    return sys.modules[__name__]


def _db():
    from app import database

    return database


def _wiki():
    from app.services import wiki_service

    return wiki_service


def _clamp(value, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def _as_uuid(value) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value.strip())
        except ValueError:
            return None
    return None


def _id_list(value) -> Optional[list]:
    """Tolerant read of an ``allowed_*`` attribute: None stays None, odd values mean "nothing"."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return []


def _bool_attr(identity, name: str) -> bool:
    return getattr(identity, name, False) is True


def _uuid_attr_list(identity, name: str) -> list[uuid.UUID]:
    raw = getattr(identity, name, None)
    if not isinstance(raw, (list, tuple, set)):
        return []
    out = []
    for v in raw:
        u = _as_uuid(v) if not isinstance(v, uuid.UUID) else v
        if u is not None:
            out.append(u)
    return out


def _str_list_attr(identity, name: str) -> Optional[list[str]]:
    raw = getattr(identity, name, None)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple, set)):
        return [str(v) for v in raw]
    return []


def _clearance(identity) -> str:
    raw = getattr(identity, "clearance_level", None)
    if isinstance(raw, str):
        return security_label.normalize(raw)
    return _TOP_LEVEL if _bool_attr(identity, "is_admin") else security_label.DEFAULT_LEVEL


def _perms(identity) -> set[str]:
    raw = getattr(identity, "permissions", None)
    if isinstance(raw, (list, tuple, set, frozenset)):
        return {str(p) for p in raw}
    return set()


def _scope_view(identity) -> SimpleNamespace:
    """Normalised, attribute-safe copy of an identity for SQL helpers."""
    is_admin = _bool_attr(identity, "is_admin")
    return SimpleNamespace(
        is_admin=is_admin,
        employee_id=_as_uuid(getattr(identity, "employee_id", None)),
        allowed_source_ids=None if is_admin else _id_list(getattr(identity, "allowed_source_ids", None)),
        allowed_knowledge_types=None if is_admin else _str_list_attr(identity, "allowed_knowledge_types"),
        clearance_level=_clearance(identity),
        department_ids=_uuid_attr_list(identity, "department_ids"),
    )


def _page_filter(identity):
    from app.services import mcp_auth_service

    view = _scope_view(identity)
    return and_(mcp_auth_service.page_source_clause(view), payloads.personal_page_clause(view))


def _strip_accents(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _fold(text: str) -> str:
    return _strip_accents(text).casefold()


def _portal_url() -> str:
    from app.config import settings

    return (getattr(settings, "portal_base_url", "") or "").rstrip("/")


def _md_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# Identity (06 §1.3)
# ---------------------------------------------------------------------------


def forwarded_role(headers: Optional[Mapping[str, str]], trust: bool) -> str:
    """Role forwarded by a trusted caller (chatbot); ignored unless ``trust`` is on."""
    if not trust or not headers:
        return ""
    value = None
    try:
        value = headers.get("x-user-role")
    except Exception:
        value = None
    if value is None:
        try:
            for k, v in headers.items():
                if str(k).lower() == "x-user-role":
                    value = v
                    break
        except Exception:
            value = None
    return (value or "").strip().lower()


def _stdio_admin_identity():
    from app.services.mcp_auth_service import ResolvedIdentity

    return ResolvedIdentity(
        employee_id=None,  # type: ignore[arg-type]  # not a real employee row
        employee_name="stdio admin",
        is_admin=True,
        clearance_level=_TOP_LEVEL,
    )


def _current_http_request():
    try:
        from fastmcp.server.dependencies import get_http_request

        return get_http_request()
    except Exception:
        return None


async def _get_identity():
    """Resolve the caller of the current MCP request. Returns ``(identity, None)`` or ``(None, error)``."""
    from app.config import settings
    from app.services.mcp_auth_service import MCPAuthService

    request = _current_http_request()
    headers: Mapping[str, str] = {}
    if request is None:
        token = (os.environ.get("MCP_TOKEN") or "").strip()
        if not token and (os.environ.get("MCP_STDIO_ADMIN") or "").strip().lower() in _TRUTHY:
            identity = _stdio_admin_identity()
            current_identity.set(identity)
            return identity, None
    else:
        headers = request.headers
        auth = (headers.get("authorization") or "").strip()
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""

    if not token:
        return None, AUTH_REQUIRED_MSG

    async with _db().async_session_factory() as session:
        service = MCPAuthService(session)
        if not token.startswith("ark_") and token.count(".") == 2:
            identity, err = await service.verify_sso_token(session, token)
            if err or identity is None:
                return None, _SSO_ERRORS.get(err or "", _SSO_ERRORS["sso_token_invalid"])
            await session.commit()
            current_identity.set(identity)
            return identity, None

        identity = await service.verify_token(session, token)
        if identity is None:
            return None, INVALID_TOKEN_MSG
        if getattr(identity, "bumped_last_connected", False) is True:
            await session.commit()

        role = forwarded_role(headers, settings.mcp_trust_forwarded_identity) if request is not None else ""
        if role:
            identity = await service.apply_forwarded_identity(identity, role, headers, session=session)
            # Department matching may have created a department row.
            await session.commit()

    current_identity.set(identity)
    return identity, None


# ---------------------------------------------------------------------------
# Source scope (06 §1.4)
# ---------------------------------------------------------------------------


async def _allowed_with_session(identity, session) -> Optional[set[str]]:
    from app.database.models import Source
    from app.services import mcp_auth_service, permission_engine

    view = _scope_view(identity)
    label_restricted = view.clearance_level != _TOP_LEVEL
    open_scope = view.is_admin or (view.allowed_source_ids is None and view.allowed_knowledge_types is None)

    if not label_restricted and open_scope:
        personal = func.coalesce(Source.scope_type, permission_engine._GLOBAL_SCOPE) == permission_engine.PERSONAL_SCOPE
        if view.employee_id is not None:
            others = and_(personal, or_(Source.scope_id.is_(None), Source.scope_id != view.employee_id))
        else:
            others = personal
        res = await session.execute(select(exists().where(others)))
        try:
            has_others = res.scalar() is True
        except Exception:
            has_others = False
        if not has_others:
            return None

    query = mcp_auth_service.apply_scope_filter(select(Source.id), view)
    res = await session.execute(query)
    return {str(v) for v in res.scalars().all()}


async def _get_allowed_source_ids(identity, session=None) -> Optional[set[str]]:
    """Ids (as strings) of sources the identity may read; None means unrestricted."""
    if session is not None:
        return await _allowed_with_session(identity, session)
    async with _db().async_session_factory() as own:
        return await _allowed_with_session(identity, own)


# ---------------------------------------------------------------------------
# Wiki write permission helpers
# ---------------------------------------------------------------------------


def _can_review(identity) -> bool:
    return _bool_attr(identity, "is_admin") or "wiki:write:all" in _perms(identity)


def _can_contribute_page(identity, scope_type: Optional[str], scope_id) -> bool:
    if _can_review(identity):
        return True
    perms = _perms(identity)
    if (scope_type or "global") == "department":
        sid = _as_uuid(scope_id) if not isinstance(scope_id, uuid.UUID) else scope_id
        return "wiki:write:own_dept" in perms and sid is not None and sid in _uuid_attr_list(identity, "department_ids")
    return any(p.startswith("wiki:write:") for p in perms)


async def _department_names(session, ids) -> dict:
    from app.database.models import Department

    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    res = await session.execute(select(Department).where(Department.id.in_(ids)))
    return {d.id: d.name for d in res.scalars().all()}


async def _out_of_scope_hint(session, pages: list) -> str:
    """Count matching pages the caller cannot see, per department, without exposing titles."""
    counts: dict = {}
    for page in pages:
        if getattr(page, "scope_type", None) != "department":
            continue
        sid = getattr(page, "scope_id", None)
        if sid is None:
            continue
        counts[sid] = counts.get(sid, 0) + 1
    if not counts:
        return ""
    try:
        names = await _department_names(session, list(counts))
    except Exception:
        names = {}
    lines = ["", "**Ngoài phạm vi truy cập của bạn:**"]
    for sid, n in counts.items():
        name = names.get(sid) or str(sid)
        lines.append(
            f"- {n} trang khớp thuộc phòng ban **{name}**. "
            "Liên hệ quản trị viên phòng ban đó nếu bạn cần được cấp quyền."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Search formatting
# ---------------------------------------------------------------------------


def _score_label(hit: dict) -> str:
    rr = hit.get("rerank_score")
    if rr is not None:
        label = f"rerank {float(rr):.2f}"
    elif hit.get("cosine") is not None:
        label = f"{float(hit['cosine']) * 100:.0f}%"
    else:
        label = "từ khóa"
    if hit.get("exact_match"):
        label = "★ khớp chính xác · " + label
    return label


def _summary_of(page, hit: dict) -> str:
    text = getattr(page, "summary", None) or hit.get("chunk_text") or ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:300] + ("…" if len(text) > 300 else "")


def _format_wiki_hit(idx: int, hit: dict) -> list[str]:
    page = hit.get("page")
    slug = getattr(page, "slug", "?")
    title = getattr(page, "title", None) or slug
    ptype = getattr(page, "page_type", None) or "concept"
    kts = getattr(page, "knowledge_type_slugs", None) or []
    kt_txt = ", ".join(kts) if isinstance(kts, (list, tuple)) and kts else "—"
    lines = [f"{idx}. **{title}** — `{slug}` [{ptype}; loại tri thức: {kt_txt}; {_score_label(hit)}]"]
    if hit.get("heading_path"):
        lines.append(f"   Mục: {hit['heading_path']}")
    summary = _summary_of(page, hit)
    if summary:
        lines.append(f"   {summary}")
    pid = getattr(page,"id",None)
    origin = getattr(page,"origin_tag",None) or "unclassified"
    lines.append(f"   Tag: {origin} · ID: {pid} · scope: {getattr(page,'scope_type',None) or 'global'}:{getattr(page,'scope_id',None)}")
    lines.append(f"   → `read_wiki_page(page_id=\"{pid}\")` · {payloads.page_url(page)}")
    return lines


def _format_source_hit(idx: int, hit: dict) -> list[str]:
    src = hit.get("source")
    chunk = hit.get("chunk")
    sid = str(getattr(src, "id", "?"))
    title = getattr(src, "title", None) or getattr(src, "file_name", None) or sid
    page_no = getattr(chunk, "page_number", None)
    page_end = getattr(chunk, "page_end", None) or page_no
    page_range = f"{page_no}-{page_end}" if page_end and page_no and page_end != page_no else str(page_no)
    text = re.sub(r"\s+", " ", str(getattr(chunk, "text", "") or "")).strip()
    preview = text[:200] + ("…" if len(text) > 200 else "")
    page_txt = f"trang {page_no}" if page_no else "không rõ trang"
    lines = [f"{idx}. **{title}** (nguyên văn) — ID `{sid}` [{_score_label(hit)}; {page_txt}]"]
    if preview:
        lines.append(f"   > {preview}")
    if page_no:
        lines.append(f"   → `get_source_pages(source_id=\"{sid}\", pages=\"{page_range}\")`")
    else:
        lines.append(f"   → `get_source_outline(source_id=\"{sid}\")`")
    base = _portal_url()
    if base:
        lines.append(f"   {base}/wiki/source/{sid}")
    return lines


_ARM_LABELS = {"wiki": "trang wiki", "source": "văn bản gốc", "exact": "tra cứu theo số hiệu"}


# ---------------------------------------------------------------------------
# Legal relations helpers
# ---------------------------------------------------------------------------


def _norm_doc_number(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def _norm_article(value: str) -> str:
    v = (value or "").strip().lower()
    v = re.sub(r"^(điều|dieu|article)\s*", "", v)
    return v.strip(" .")


def _doc_col(col):
    return func.upper(func.replace(col, " ", ""))


def _rel_type(rel) -> str:
    rt = getattr(rel, "relation_type", "")
    return getattr(rt, "value", rt) or ""


def _unit_ref(unit) -> str:
    if unit is None:
        return "?"
    path = getattr(unit, "full_path", None) or getattr(unit, "title", None) or "?"
    doc = getattr(unit, "doc_number", None)
    return f"{path} ({doc})" if doc else path


def _target_ref(rel, allowed: Optional[set[str]]) -> str:
    target = getattr(rel, "target_unit", None)
    if target is not None and (allowed is None or str(target.source_id) in allowed):
        return _unit_ref(target)
    doc = getattr(rel, "target_doc_number", None) or (getattr(target, "doc_number", None) if target else None)
    return doc or "văn bản chưa rõ số hiệu"


def _relation_line(rel, other: str, arrow: str) -> str:
    rt = _rel_type(rel)
    label = RELATION_LABELS.get(rt, rt or "Quan hệ")
    line = f"- **{label}** {arrow} {other}"
    if getattr(rel, "is_effective", True) is False:
        line += " (không còn hiệu lực)"
    quote = (getattr(rel, "quote_context", None) or "").strip()
    if quote:
        line += f" — “{clip_text(quote, 500)}”"
    return line


def _relations_block(outgoing: list, incoming: list, limit: int, allowed) -> str:
    if not outgoing and not incoming:
        return "Không ghi nhận quan hệ sửa đổi, thay thế hay dẫn chiếu nào."
    lines = ["### Văn bản này tác động đến:"]
    if outgoing:
        for rel in outgoing[:limit]:
            lines.append(_relation_line(rel, _target_ref(rel, allowed), "→"))
        if len(outgoing) > limit:
            lines.append("… còn thêm")
    else:
        lines.append("_(không có)_")
    lines.append("")
    lines.append("### Bị tác động bởi:")
    if incoming:
        for rel in incoming[:limit]:
            lines.append(_relation_line(rel, _unit_ref(getattr(rel, "source_unit", None)), "←"))
        if len(incoming) > limit:
            lines.append("… còn thêm")
    else:
        lines.append("_(không có)_")
    return "\n".join(lines)


async def _validity_callout(session, unit_id) -> str:
    try:
        from app.services import legal_service

        warnings = await legal_service.get_legal_unit_validity_warnings(session, unit_id)
        return legal_service.format_legal_validity_warning_callout(warnings) if warnings else ""
    except Exception as e:
        logger.debug("validity warnings failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


async def _load_scoped_source(session, identity, source_id):
    from app.database.models import Source

    sid = _as_uuid(str(source_id or ""))
    if sid is None:
        return None, f"Invalid source ID: {source_id}"
    src = await session.get(Source, sid)
    if src is None:
        return None, f"Source not found: {source_id}"
    allowed = await _this()._get_allowed_source_ids(identity, session)
    if allowed is not None and str(src.id) not in allowed:
        return None, ACCESS_DENIED_SOURCE
    return src, None


def _page_of_offset(page_offsets, offset: int) -> Optional[int]:
    if not isinstance(page_offsets, list) or not page_offsets:
        return None
    try:
        offs = [int(o) for o in page_offsets]
    except (TypeError, ValueError):
        return None
    return max(1, bisect.bisect_right(offs, offset))


def _search_terms(query: str) -> list[str]:
    words = re.findall(r"\w+", (query or "").lower())
    return [w for w in words if len(w) > 1 and w not in _VI_STOPWORDS]


def _matching_lines(full_text: str, page_offsets, terms: list[str], max_lines: int = 5) -> list[str]:
    folded_terms = [_fold(t) for t in terms if t]
    out = []
    pos = 0
    for raw in (full_text or "").split("\n"):
        line_start = pos
        pos += len(raw) + 1
        line = raw.strip()
        if not line:
            continue
        folded = _fold(line)
        if not any(t and t in folded for t in folded_terms):
            continue
        shown = line[:300]
        for t in sorted({t for t in terms if t}, key=len, reverse=True):
            shown = re.sub(f"({re.escape(t)})", r"**\1**", shown, flags=re.IGNORECASE)
        page = _page_of_offset(page_offsets, line_start)
        out.append(f"- {'(trang ' + str(page) + ') ' if page else ''}{shown}")
        if len(out) >= max_lines:
            break
    return out


# ---------------------------------------------------------------------------
# Skill bundle helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    text = text or ""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    meta: dict = {}
    try:
        import yaml

        loaded = yaml.safe_load(raw)
        if isinstance(loaded, dict):
            meta = {str(k): v for k, v in loaded.items()}
    except Exception:
        meta = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def _bundle_cache_put(key, bundle) -> None:
    if len(_bundle_cache) >= _BUNDLE_CACHE_MAX:
        _bundle_cache.clear()
    _bundle_cache[key] = bundle


def _load_bundle_sync(storage_path: str) -> dict:
    from app.services import storage_service

    store = storage_service.storage_service
    prefix = storage_path.rstrip("/") + "/"
    objects = [o for o in store.list_objects(prefix, recursive=True) if not str(o.object_name).endswith("/")]
    rels = [(str(o.object_name)[len(prefix):], o) for o in objects]
    skill_md = [
        (r.count("/"), r, o) for r, o in rels if posixpath.basename(r).lower() == "skill.md"
    ]
    root = ""
    skill_obj = None
    if skill_md:
        skill_md.sort(key=lambda t: (t[0], t[1]))
        _, rel, skill_obj = skill_md[0]
        root = posixpath.dirname(rel)
    files: dict[str, tuple[str, int]] = {}
    for rel, o in rels:
        if root and not rel.startswith(root + "/"):
            continue
        local = rel[len(root) + 1:] if root else rel
        files[local] = (str(o.object_name), int(getattr(o, "size", 0) or 0))
    skill_text = None
    meta: dict = {}
    if skill_obj is not None:
        skill_text = store.download_file(str(skill_obj.object_name)).decode("utf-8", errors="replace")
        meta, _ = _parse_frontmatter(skill_text)
    return {"root": root, "files": files, "skill_md": skill_text, "meta": meta}


async def _load_bundle(skill) -> dict:
    key = (skill.storage_path, skill.version_hash)
    cached = _bundle_cache.get(key)
    if cached is not None:
        return cached
    bundle = await asyncio.to_thread(_load_bundle_sync, skill.storage_path)
    _bundle_cache_put(key, bundle)
    return bundle


async def _skill_department_map(session, skill_ids) -> dict:
    from app.database.models import SkillDepartment

    if not skill_ids:
        return {}
    res = await session.execute(
        select(SkillDepartment.skill_id, SkillDepartment.department_id).where(SkillDepartment.skill_id.in_(skill_ids))
    )
    out: dict = {}
    for sid, did in res.all():
        out.setdefault(sid, set()).add(did)
    return out


def _can_read_skill(identity, skill_depts: set) -> bool:
    if _bool_attr(identity, "is_admin"):
        return True
    if "skill:read:all" in _perms(identity) and getattr(identity, "delegated_role", None) is None:
        return True
    if not skill_depts:
        return True
    return bool(set(_uuid_attr_list(identity, "department_ids")) & set(skill_depts))


async def _resolve_skill(session, identity, slug: str):
    from app.database.models import Skill

    res = await session.execute(select(Skill).where(Skill.slug == (slug or "").strip()))
    skill = res.scalars().first()
    status = getattr(getattr(skill, "status", None), "value", getattr(skill, "status", None))
    if skill is None or status != "active":
        return None, f"Skill '{slug}' not found. Use `list_skills` to see available skills."
    depts = (await _skill_department_map(session, [skill.id])).get(skill.id, set())
    if not _can_read_skill(identity, depts):
        return None, f"Access denied: skill '{slug}' is outside your scope."
    if not skill.storage_path:
        return None, f"Skill '{slug}' has no stored content."
    return skill, None


def _fmt_size(n: int) -> str:
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB"


def _truncate(text: str, limit: int = SKILL_FILE_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n(truncated: {len(text) - limit} more characters)"


def _normalize_skill_path(path: str) -> str:
    p = (path or "").replace("\\", "/").lstrip("/")
    p = posixpath.normpath(p) if p else ""
    return "" if p == "." else p


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp) -> None:  # noqa: C901 - one registry for all tools
    kb_tool = permissions_compat.kb_tool
    ANY = permissions_compat.any_authenticated()
    CONTRIB = permissions_compat.can_contribute_wiki()

    # -- search_wiki --------------------------------------------------------

    @kb_tool(
        mcp,
        requires=ANY,
        name="search_wiki",
        description=(
            "Search the Document Wiki knowledge base (wiki pages and original documents) with hybrid semantic + "
            "keyword search. Always call this first before answering. Returns ranked hits with slugs and "
            "source IDs to cite."
        ),
    )
    @logged_tool("search_wiki", query_arg="query")
    async def search_wiki(query: str, top_k: int = 10) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        top_k = _clamp(top_k, 1, 50, 10)
        from app.ai.registry import ProviderRegistry
        from app.services import retrieval_service

        is_admin = _bool_attr(identity, "is_admin")
        view = _scope_view(identity)
        async with _db().async_session_factory() as session:
            allowed = await _this()._get_allowed_source_ids(identity, session)
            try:
                embedder = await ProviderRegistry(session).get_embedding(task="search_query")
                embedding = await embedder.embed(query)
                if not embedding:
                    raise ValueError("Empty query embedding")
            except Exception as exc:
                logger.warning("MCP query embedding unavailable: %s", type(exc).__name__)
                embedding = None
            result = await retrieval_service.unified_search(
                session,
                query,
                embedding,
                top_k=top_k,
                allowed_kt_slugs=view.allowed_knowledge_types,
                department_ids=view.department_ids,
                all_scopes=is_admin,
                allowed_source_ids=allowed,
                apply_reranker=True,
                apply_mmr=True,
                check_out_of_scope=not is_admin,
                clearance=view.clearance_level,
                page_filter=_page_filter(identity),
                personal_owner_id=view.employee_id,
            )
            exact = result.get("exact_match")
            ranked = list(result.get("ranked_results") or [])
            failed = list(result.get("failed_arms") or [])
            oos_pages = [
                (t[0] if isinstance(t, (list, tuple)) else t)
                for t in (result.get("out_of_scope_hits") or [])
                if (t[1] if isinstance(t, (list, tuple)) and len(t) > 1 else 1.0) >= MIN_SIM_FLOOR
            ]
            hint = await _out_of_scope_hint(session, oos_pages) if oos_pages else ""
            structured_hits,citations = await payloads.search_metadata(session,view,ranked)
            exact_meta = None
            if exact and exact.get("wiki_page_id"):
                exact_pages = await payloads.find_pages(session,view,page_id=_as_uuid(exact["wiki_page_id"]))
                if exact_pages:
                    exact_meta = (await payloads.page_metadata_batch(session,view,exact_pages[:1]))[0]
                    citations.insert(0,payloads.page_citation(exact_meta,exact.get("content") or ""))

        if "wiki" in failed and "source" in failed and not exact:
            return payloads.knowledge_result(
                "Tìm kiếm thất bại: cả trang wiki và văn bản gốc đều bị lỗi. "
                "Thử lại sau hoặc báo quản trị viên.", status='error', query=query,
                results=[], failed_arms=failed, search=result.get('search') or {},
            )

        parts: list[str] = []
        shown_failed = [_ARM_LABELS[a] for a in failed if a in _ARM_LABELS]
        if shown_failed:
            parts.append(f"> ⚠ Một phần tìm kiếm bị lỗi ({', '.join(shown_failed)}); kết quả có thể chưa đầy đủ.")
        if (result.get("search") or {}).get("warning"):
            parts.append("> ⚠ " + result["search"]["warning"])

        if exact:
            block = ["## KẾT QUẢ TRA CỨU CHÍNH XÁC THEO SỐ HIỆU VĂN BẢN"]
            if exact.get("doc_number"):
                block.append(f"- **Số hiệu:** {exact['doc_number']}")
            if exact.get("full_path"):
                block.append(f"- **Điều khoản:** {exact['full_path']}")
            if exact.get("title"):
                block.append(f"- **Tiêu đề:** {exact['title']}")
            if exact.get("warning_callout"):
                block.append("")
                block.append(str(exact["warning_callout"]))
            if exact.get("content"):
                block.append("")
                block.append(str(exact["content"]))
            parts.append("\n".join(block))

        if not ranked:
            if not exact:
                msg = f'No knowledge base matches found for: "{query}"'
                parts.append(msg + (("\n" + hint) if hint else ""))
            elif hint:
                parts.append(hint)
            return payloads.knowledge_result("\n\n".join(parts), query=query, results=structured_hits,
                exact_match={**exact,"page":exact_meta} if exact else None, sources=citations,
                failed_arms=failed, total_candidates=result.get("total_candidates") or 0,
                search=result.get("search") or {})

        lines = [f'**KB search — {len(ranked)} result(s) for: "{query}"**']
        lines.append(f"_Phạm vi: {security_label.describe(view.clearance_level)}"
                     f"{'; toàn bộ phòng ban' if is_admin else ''}_")
        lines.append("")
        for i, item in enumerate(ranked, 1):
            kind, _score, hit = item[0], item[1], item[2]
            lines.extend(_format_wiki_hit(i, hit) if kind == "wiki" else _format_source_hit(i, hit))
        total = result.get("total_candidates") or 0
        if isinstance(total, int) and total > len(ranked) and top_k < 50:
            lines.append("")
            lines.append(f"_Có {total} ứng viên; tăng `top_k` (tối đa 50) để xem thêm._")
        neighbors = result.get("graph_neighbors") or []
        if neighbors:
            section = retrieval_service.format_graph_neighbors_section(neighbors)
            if section:
                lines.append("")
                lines.append(section)
        if hint:
            lines.append(hint)
        parts.append("\n".join(lines))
        return payloads.knowledge_result("\n\n".join(parts), query=query, results=structured_hits,
                exact_match={**exact,"page":exact_meta} if exact else None, sources=citations,
                failed_arms=failed, total_candidates=result.get("total_candidates") or 0,
                search=result.get("search") or {})

    # -- read_wiki_index -----------------------------------------------------

    @kb_tool(
        mcp,
        requires=ANY,
        name="read_wiki_index",
        description="List the wiki pages you can access, grouped by page type (your personal catalog).",
    )
    async def read_wiki_index() -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        async with _db().async_session_factory() as session:
            return await _wiki().render_scoped_index(
                session,
                allowed_kt_slugs=getattr(identity, "allowed_knowledge_types", None),
                department_ids=getattr(identity, "department_ids", None),
                all_scopes=_bool_attr(identity, "is_admin"),
                clearance=_clearance(identity),
                page_filter=_page_filter(identity),
                personal_owner_id=_scope_view(identity).employee_id,
            )

    # -- read_wiki_page ------------------------------------------------------

    @kb_tool(
        mcp,
        requires=ANY,
        name="read_wiki_page",
        description="Read Wiki content, AI summary and source metadata. Content is bounded; use offset/max_chars and returned next_offset to continue. Prefer page_id from search; otherwise supply slug and scope_type/scope_id. Ambiguous slugs return accessible choices.",
    )
    @logged_tool("read_wiki_page", query_arg="slug")
    async def read_wiki_page(
        slug: Optional[str] = None, page_id: Optional[str] = None,
        scope_type: Optional[str] = None, scope_id: Optional[str] = None,
        offset: int = 0, max_chars: int = payloads.READ_DEFAULT_CHARS,
    ) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import LegalUnit, WikiPage

        view = _scope_view(identity)
        pid = _as_uuid(page_id) if page_id else None
        sid = _as_uuid(scope_id) if scope_id else None
        slug = (slug or "").strip() or None
        if page_id and pid is None:
            return "Error: page_id must be a valid UUID."
        if not slug and pid is None:
            return "Error: supply page_id or slug."
        if scope_type not in (None, "global", "department", "personal", "project"):
            return "Error: invalid scope_type."
        if scope_id and (sid is None or not scope_type or scope_type == "global"):
            return "Error: scope_id requires a non-global scope_type and a valid UUID."
        if scope_type == "personal" and sid is None:
            sid = view.employee_id
        if scope_type in ("department", "personal", "project") and sid is None:
            return "Error: scope_id is required for this scope."
        async with _db().async_session_factory() as session:
            matches = await payloads.find_pages(session, view, slug=slug, page_id=pid,
                                               scope_type=scope_type, scope_id=sid)
            if not matches:
                return "Wiki page not found or out of scope."
            if len(matches) > 1:
                choices = [{k: payloads.page_metadata(p, [])[k] for k in
                            ("id", "slug", "title", "origin_tag", "scope_type", "scope_id", "url")} for p in matches[:50]]
                text = "Multiple accessible pages match this slug. Re-call read_wiki_page(page_id=...) or specify scope_type and scope_id.\n\n"
                text += "\n".join(f"- `{c['id']}` · {c['scope_type']}:{c['scope_id']} · {c['title']}" for c in choices)
                return payloads.knowledge_result(text, status="ambiguous", choices=choices, has_more=len(matches)>50)
            page = matches[0]
            meta = (await payloads.page_metadata_batch(session, view, [page], full_summary=True))[0]
            parts = [f"# {meta['title']}", payloads.metadata_markdown({k:v for k,v in meta.items() if k != "summary"})]
            if meta["summary"]:
                parts.append("## Tóm tắt\n" + meta["summary"])
            unit = (await session.execute(select(LegalUnit).where(LegalUnit.wiki_page_id == page.id)
                    .order_by(case((LegalUnit.unit_type == "article", 0), else_=1)).limit(1))).scalars().first()
            if unit is not None:
                callout = await _validity_callout(session, unit.id)
                if callout:
                    parts.append(callout)
            window = payloads.text_window(page.content_md, offset=offset, max_chars=max_chars)
            parts.append("## Nội dung\n" + window['content'])
            if window['has_more']:
                parts.append(f'_Nội dung chưa đầy đủ. Tiếp tục: read_wiki_page(page_id="{page.id}", offset={window["next_offset"]}, max_chars={window["max_chars"]})._')
            wiki = _wiki()
            outs = await wiki.get_outlinks(session, page.slug, scope_type=page.scope_type or "global", scope_id=page.scope_id)
            backs = await wiki.get_backlinks(session, page.slug, scope_type=page.scope_type or "global", scope_id=page.scope_id)
            def slugs(items):
                return {it if isinstance(it,str) else getattr(it,"slug",None) or getattr(it,"to_slug",None) for it in items or []} - {None, page.slug}
            out_slugs, back_slugs = slugs(outs), slugs(backs)
            linked = out_slugs | back_slugs
            if linked:
                readable = (await session.execute(payloads.readable_pages(view).where(
                    WikiPage.slug.in_(linked), WikiPage.scope_type == page.scope_type,
                    WikiPage.scope_id == page.scope_id if page.scope_id else WikiPage.scope_id.is_(None)
                ))).scalars().all()
                allowed_links = {p.slug for p in readable}
                out_slugs &= allowed_links; back_slugs &= allowed_links
            out_slugs, back_slugs = sorted(out_slugs), sorted(back_slugs)
            parts.append("## Outlinks\n" + ("\n".join(f"- [[{x}]]" for x in out_slugs) or "_(none)_"))
            parts.append("## Backlinks\n" + ("\n".join(f"- [[{x}]]" for x in back_slugs) or "_(none)_"))
        return payloads.knowledge_result("\n\n".join(parts), page=meta, content_md=window['content'],
            content_truncated=window['truncated'], pagination={k:v for k,v in window.items() if k not in ('content','truncated')},
            **{key:window[key] for key in ('content_offset','content_length','total_chars','content_version','content_empty')},
            outlinks=out_slugs, backlinks=back_slugs, sources=[payloads.page_citation(meta,window['content'])])

    # -- get_document_relations ---------------------------------------------

    @kb_tool(
        mcp,
        requires=ANY,
        name="get_document_relations",
        description=(
            "Show legal relations (amends, replaces, repeals, guides, cites) of a document or article. "
            "Give doc_number (+ article_number) or a wiki page slug."
        ),
    )
    async def get_document_relations(
        doc_number: Optional[str] = None,
        article_number: Optional[str] = None,
        slug: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import LegalRelation, LegalUnit, WikiPage

        limit = _clamp(limit, 1, 200, 50)
        doc_number = (doc_number or "").strip() or None
        art = _norm_article(article_number) if article_number else ""
        slug = (slug or "").strip() or None

        async with _db().async_session_factory() as session:
            allowed = await _this()._get_allowed_source_ids(identity, session)
            if allowed is not None and not allowed:
                return NO_SCOPE_MSG
            allowed_uuids = [u for u in (_as_uuid(a) for a in allowed) if u] if allowed is not None else None

            def scoped(q, col=LegalUnit.source_id):
                return q.where(col.in_(allowed_uuids)) if allowed_uuids is not None else q

            unit = None
            if doc_number and art:
                norm = _norm_doc_number(doc_number)
                dcol = _doc_col(LegalUnit.doc_number)
                q = scoped(
                    select(LegalUnit).where(
                        dcol.like(f"%{norm}%"),
                        LegalUnit.unit_type == "article",
                        func.lower(LegalUnit.unit_number) == art,
                    )
                ).order_by(case((dcol == norm, 0), (dcol.like(f"{norm}%"), 1), else_=2)).limit(1)
                unit = (await session.execute(q)).scalars().first()

            if unit is None and slug:
                q = scoped(
                    select(LegalUnit)
                    .join(WikiPage, LegalUnit.wiki_page_id == WikiPage.id)
                    .where(WikiPage.slug == slug)
                ).order_by(case((LegalUnit.unit_type == "article", 0), else_=1)).limit(1)
                unit = (await session.execute(q)).scalars().first()
                if unit is None and not (doc_number and art):
                    if not doc_number:
                        return f"Không tìm thấy điều khoản gắn với trang `{slug}` (hoặc bạn không có quyền)."

            if unit is not None:
                header = f"## Quan hệ văn bản: {unit.full_path or unit.title or ''} ({unit.doc_number or 'chưa rõ số hiệu'})"
                callout = await _validity_callout(session, unit.id)
                out_q = (
                    select(LegalRelation)
                    .where(LegalRelation.source_unit_id == unit.id)
                    .options(selectinload(LegalRelation.target_unit))
                    .limit(limit + 1)
                )
                outgoing = list((await session.execute(out_q)).scalars().all())
                incoming_cond = [LegalRelation.target_unit_id == unit.id]
                if unit.doc_number and unit.unit_number:
                    incoming_cond.append(
                        and_(
                            _doc_col(LegalRelation.target_doc_number) == _norm_doc_number(unit.doc_number),
                            func.lower(LegalRelation.target_article_number) == str(unit.unit_number).lower(),
                        )
                    )
                in_q = scoped(
                    select(LegalRelation)
                    .join(LegalUnit, LegalRelation.source_unit_id == LegalUnit.id)
                    .where(or_(*incoming_cond))
                    .options(contains_eager(LegalRelation.source_unit))
                ).limit(limit + 1)
                incoming = list((await session.execute(in_q)).scalars().all())
                body = _relations_block(outgoing, incoming, limit, allowed)
                return "\n\n".join(p for p in (header, callout, body) if p)

            if doc_number:
                norm = _norm_doc_number(doc_number)
                SrcU = aliased(LegalUnit)
                TgtU = aliased(LegalUnit)
                out_q = scoped(
                    select(LegalRelation)
                    .join(SrcU, LegalRelation.source_unit_id == SrcU.id)
                    .where(_doc_col(SrcU.doc_number).like(f"%{norm}%"))
                    .options(contains_eager(LegalRelation.source_unit.of_type(SrcU)), selectinload(LegalRelation.target_unit)),
                    SrcU.source_id,
                ).limit(limit + 1)
                outgoing = list((await session.execute(out_q)).scalars().all())
                in_q = scoped(
                    select(LegalRelation)
                    .join(SrcU, LegalRelation.source_unit_id == SrcU.id)
                    .outerjoin(TgtU, LegalRelation.target_unit_id == TgtU.id)
                    .where(
                        or_(
                            _doc_col(LegalRelation.target_doc_number).like(f"%{norm}%"),
                            _doc_col(TgtU.doc_number).like(f"%{norm}%"),
                        ),
                        not_(func.coalesce(_doc_col(SrcU.doc_number), literal("")).like(f"%{norm}%")),
                    )
                    .options(contains_eager(LegalRelation.source_unit.of_type(SrcU))),
                    SrcU.source_id,
                ).limit(limit + 1)
                incoming = list((await session.execute(in_q)).scalars().all())
                header = f"## Quan hệ văn bản: {doc_number}"
                return header + "\n\n" + _relations_block(outgoing, incoming, limit, allowed)

        return "Vui lòng cung cấp `doc_number` (kèm `article_number` nếu cần) hoặc `slug` hợp lệ."

    # -- list_wiki_pages -----------------------------------------------------

    @kb_tool(
        mcp,
        requires=ANY,
        name="list_wiki_pages",
        description="Browse accessible pages with metadata and IDs. Filter by page_type, knowledge_type, origin_tag (extracted/generated), source_id, query; limit/offset paginate.",
    )
    @logged_tool("list_wiki_pages", query_arg="query")
    async def list_wiki_pages(
        page_type: Optional[str] = None, knowledge_type: Optional[str] = None,
        query: Optional[str] = None, limit: int = 50, offset: int = 0,
        origin_tag: Optional[str] = None, source_id: Optional[str] = None,
    ) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        if origin_tag not in (None, "extracted", "generated"):
            return "Error: origin_tag must be extracted or generated."
        source_uuid = _as_uuid(source_id) if source_id else None
        if source_id and source_uuid is None:
            return "Error: source_id must be a valid UUID."
        limit = _clamp(limit, 1, 50, 50)
        offset = max(0, _clamp(offset, 0, 10**9, 0))
        view = _scope_view(identity)
        async with _db().async_session_factory() as session:
            pages = list(await _wiki().list_pages(
                session, page_type=page_type, knowledge_type_slug=knowledge_type,
                allowed_kt_slugs=view.allowed_knowledge_types, query=query, limit=limit+1, offset=offset,
                department_ids=view.department_ids, all_scopes=view.is_admin, clearance=view.clearance_level,
                page_filter=and_(_page_filter(identity),payloads.personal_page_clause(view)),
                personal_owner_id=view.employee_id, origin_tag=origin_tag, source_id=source_uuid,
            ))
            more = len(pages) > limit
            meta = await payloads.page_metadata_batch(session,view,pages[:limit])
        lines = [f"**Wiki pages — {len(meta)} result(s)**", ""]
        for page in meta:
            lines.append(f"- `{page['slug']}` — {page['title']} ({page['page_type']}; {page['origin_tag'] or 'unclassified'}; "
                         f"ID {page['id']}; scope {page['scope_type']}:{page['scope_id']}): {page['summary']}")
            lines.append(f"  → read_wiki_page(page_id=\"{page['id']}\") · {page['url']}")
        if more:
            lines.append(f"_Còn trang sau: gọi lại với offset={offset+limit}._")
        if not meta:
            lines.append("No wiki pages match the filters.")
        return payloads.knowledge_result("\n".join(lines), pages=meta,
            pagination={"offset":offset,"limit":limit,"has_more":more,"next_offset":offset+limit if more else None},
            sources=[payloads.page_citation(p,p['summary']) for p in meta])

    # -- get_source ----------------------------------------------------------

    @kb_tool(mcp, requires=ANY, name="get_source", description="Read document attributes, scope, management department, processing status and linked Wiki page IDs. Linked pages support wiki_offset/wiki_limit paging.")
    async def get_source(source_id: str, wiki_offset: int = 0, wiki_limit: int = 50) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import WikiPage

        view = _scope_view(identity)
        wiki_offset = max(0, _clamp(wiki_offset, 0, 10**9, 0))
        wiki_limit = _clamp(wiki_limit, 1, 100, 50)
        async with _db().async_session_factory() as session:
            src, err = await _load_scoped_source(session, identity, source_id)
            if err:
                return err
            loaded = await payloads.load_sources(session, view, [src.id])
            if not loaded:
                return ACCESS_DENIED_SOURCE
            meta = payloads.source_metadata(loaded[0])
            pages = list((await session.execute(payloads.readable_pages(view).where(
                src.id == any_(WikiPage.source_ids)).order_by(WikiPage.created_at,WikiPage.id)
                .offset(wiki_offset).limit(wiki_limit+1))).scalars().all())
            more = len(pages) > wiki_limit
            refs = [payloads.page_metadata(p,[],full_summary=False) for p in pages[:wiki_limit]]
        lines = [f"# {meta['title']}", payloads.metadata_markdown(meta), "## Trang Wiki liên quan"]
        lines.extend(f"- {p['title']} · {p['origin_tag'] or 'unclassified'} · ID `{p['id']}` · {p['url']}" for p in refs)
        if more:
            lines.append(f"Còn trang sau: get_source(source_id=\"{source_id}\", wiki_offset={wiki_offset+wiki_limit}).")
        return payloads.knowledge_result("\n\n".join(lines), source=meta, wiki_pages=refs,
            pagination={"offset":wiki_offset,"limit":wiki_limit,"has_more":more,
                        "next_offset":wiki_offset+wiki_limit if more else None},
            sources=[payloads.source_citation(meta)])

    # -- get_source_outline --------------------------------------------------

    @kb_tool(
        mcp, requires=ANY, name="get_source_outline",
        description="Show the heading outline (with page numbers) of an original document.",
    )
    async def get_source_outline(source_id: str) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.services.source_outline import flatten_outline_with_depth

        async with _db().async_session_factory() as session:
            src, err = await _load_scoped_source(session, identity, source_id)
            if err:
                return err
            loaded = await payloads.load_sources(session,_scope_view(identity),[src.id])
            if not loaded:
                return ACCESS_DENIED_SOURCE
            src = loaded[0]
            meta = payloads.source_metadata(src)
        nodes = src.outline_json if isinstance(src.outline_json, list) else []
        flat = flatten_outline_with_depth(nodes)
        if not flat:
            return payloads.knowledge_result("_(no outline — this document has no detectable headings)_",source=meta,outline=[],sources=[payloads.source_citation(meta)])
        lines = ["# Outline", ""]
        for e in flat:
            page = f" (page {e['page']})" if e.get("page") else ""
            lines.append(f"{'  ' * int(e.get('_depth') or 0)}- {e.get('title') or ''}{page}")
        return payloads.knowledge_result("\n".join(lines),source=meta,outline=flat,sources=[payloads.source_citation(meta)])

    # -- get_source_pages ----------------------------------------------------

    @kb_tool(
        mcp, requires=ANY, name="get_source_pages",
        description="Read bounded verbatim text of original pages, e.g. pages='5-7' or '3,8'. Replay pages with returned offset/char_offset to continue; max_chars <= 50000 and limit <= 20 pages.",
    )
    async def get_source_pages(source_id: str, pages: str, offset: int = 0, char_offset: int = 0,
                               max_chars: int = payloads.READ_DEFAULT_CHARS, limit: int = payloads.READ_MAX_PAGES) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        async with _db().async_session_factory() as session:
            src, err = await _load_scoped_source(session, identity, source_id)
            if err:
                return err
            loaded = await payloads.load_sources(session,_scope_view(identity),[src.id])
            if not loaded:
                return ACCESS_DENIED_SOURCE
            src = loaded[0]
            meta = payloads.source_metadata(src)
        offsets = src.page_offsets or ([0] if src.full_text else [])
        window = payloads.source_page_window(src.full_text, offsets, pages, offset=offset,
                    char_offset=char_offset, max_chars=max_chars, limit=limit)
        if not window['valid_range']:
            return f"Invalid page range: '{pages}'. Use formats like '5-7', '3,8', '12'."
        sliced = window['pages']
        body = "\n\n".join(f"--- page {s['page']} ---\n{s['content']}" for s in sliced)
        text = f"# {meta['title']}\nSource ID: {source_id} · scope: {meta['scope_type']}:{meta['scope_id']}\n\n" + (body or f"No content for pages: {pages}")
        if window['pagination']['has_more']:
            more = window['pagination']
            text += f'\n\n_Content truncated. Continue get_source_pages(source_id="{src.id}", pages="{pages}", offset={more["next_offset"]}, char_offset={more["next_char_offset"]}, max_chars={more["max_chars"]}, limit={more["limit"]})._'
        return payloads.knowledge_result(text,source=meta,pages=sliced,
            content_truncated=window['truncated'], pagination=window['pagination'],
            sources=[payloads.source_citation(meta,p["content"],p["page"]) for p in sliced])

    # -- search_source_content -----------------------------------------------

    @kb_tool(
        mcp, requires=ANY, name="search_source_content",
        description="Keyword search inside the full text of original documents (accent-insensitive).",
    )
    @logged_tool("search_source_content", query_arg="query")
    async def search_source_content(query: str, limit: int = 10, offset: int = 0) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        if not (query or "").strip():
            return "Error: query parameter must not be empty."
        from app.database.models import Source
        from app.services import mcp_auth_service

        limit = _clamp(limit, 1, 50, 10)
        offset = max(0, _clamp(offset, 0, 10**9, 0))
        view = _scope_view(identity)
        plain_q = _strip_accents(query).lower()
        terms = _search_terms(query)
        plain_terms = [_strip_accents(t).lower() for t in terms]
        unaccented = func.lower(func.unaccent(func.coalesce(Source.full_text, "")))

        def base():
            return mcp_auth_service.apply_scope_filter(
                # Raw text remains usable after either downstream branch fails.
                select(Source).where(Source.full_text.isnot(None),
                    func.length(func.btrim(Source.full_text, " \t\r\n")) > 0), view
            )

        tiers = []
        tiers.append(func.to_tsvector("simple", unaccented).op("@@")(func.websearch_to_tsquery("simple", plain_q)))
        if plain_terms:
            tiers.append(
                func.to_tsvector("simple", unaccented).op("@@")(func.to_tsquery("simple", " | ".join(
                    re.sub(r"[^\w]", "", t) for t in plain_terms if re.sub(r"[^\w]", "", t)
                ) or "''"))
            )
        long_words = [w for w in plain_terms if len(w) > 2][:3]
        if long_words:
            tiers.append(and_(*[unaccented.like(f"%{w}%") for w in long_words]))

        rows: list = []
        async with _db().async_session_factory() as session:
            for cond in tiers:
                try:
                    res = await session.execute(
                        base().where(cond).order_by(Source.created_at.desc()).offset(offset).limit(limit)
                    )
                    rows = list(res.scalars().all())
                    loaded = await payloads.load_sources(session,view,[src.id for src in rows])
                    metadata = {str(src.id):payloads.source_metadata(src) for src in loaded}
                except Exception as e:
                    logger.debug("search_source_content tier failed: %s", e)
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    rows = []
                if rows:
                    break

        if not rows:
            return payloads.knowledge_result(f'No document content matches found for: "{query}"',results=[],sources=[])
        hl_terms = terms or [query.strip()]
        lines = [f'**Document content — {len(rows)} result(s) for: "{query}"**', ""]
        for src in rows:
            lines.append(f"### {src.title or src.file_name or src.id} (ID: {src.id})")
            lines.extend(_matching_lines(src.full_text or "", src.page_offsets, hl_terms) or ["- _(khớp trong văn bản)_"])
            lines.append("")
        hits = [{"source":metadata[str(src.id)],"matches":_matching_lines(src.full_text or "",src.page_offsets,hl_terms)} for src in rows if str(src.id) in metadata]
        return payloads.knowledge_result("\n".join(lines),results=hits,offset=offset,limit=limit,
            sources=[payloads.source_citation(hit["source"],"\n".join(hit["matches"])) for hit in hits])

    # -- list_sources --------------------------------------------------------

    @kb_tool(mcp, requires=ANY, name="list_sources", description="List original documents in your scope, grouped by knowledge type.")
    @logged_tool("list_sources", query_arg="query")
    async def list_sources(
        status: str = "ready",
        knowledge_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import KnowledgeType, Source
        from app.services import mcp_auth_service

        limit = _clamp(limit, 1, 100, 20)
        offset = max(0, _clamp(offset, 0, 10**9, 0))
        q = select(Source, KnowledgeType.name).outerjoin(KnowledgeType, Source.knowledge_type_id == KnowledgeType.id)
        if status and status != "all":
            q = q.where(Source.status == status)
        if knowledge_type:
            q = q.where(KnowledgeType.slug == knowledge_type)
        if query:
            like = f"%{query}%"
            q = q.where(or_(Source.title.ilike(like), Source.file_name.ilike(like), Source.url.ilike(like)))
        q = mcp_auth_service.apply_scope_filter(q, _scope_view(identity))
        q = q.order_by(Source.created_at.desc()).offset(offset).limit(limit+1)
        async with _db().async_session_factory() as session:
            rows = list((await session.execute(q.options(*payloads.source_options()))).all())
            more = len(rows)>limit
            rows = rows[:limit]
            metadata = [payloads.source_metadata(src) for src,_ in rows]
        if not rows:
            msg = "No documents found"
            if knowledge_type:
                msg += f" of type '{knowledge_type}'"
            if query:
                msg += f" matching '{query}'"
            return payloads.knowledge_result(msg + ".", documents=[], sources=[],
                pagination={"offset":offset,"limit":limit,"has_more":False,"next_offset":None})
        groups: dict[str, list] = {}
        for src, kt_name in rows:
            groups.setdefault(kt_name or "Uncategorized", []).append(src)
        lines = [f"**Knowledge Base — {len(rows)} document(s)**"]
        for name in sorted(groups):
            lines.append("")
            lines.append(f"### {name}")
            for src in groups[name]:
                meta = next(m for m in metadata if m["id"] == str(src.id))
                doc = meta["doc_meta"]
                lines.append(f"- {meta['title']} (ID: `{src.id}`, status: {src.status}; scope: {meta['scope_type']}; quản lý: {meta['managing_department_name'] or '—'})")
                lines.append(f"  Số hiệu: {doc.get('doc_number') or '—'} · Cơ quan: {doc.get('issuing_authority') or '—'} · {meta['url']}")
        if more:
            lines.append(f"_Còn trang sau: gọi lại với offset={offset+limit}._")
        return payloads.knowledge_result("\n".join(lines), documents=metadata,
            pagination={"offset":offset,"limit":limit,"has_more":more,"next_offset":offset+limit if more else None},
            sources=[payloads.source_citation(m) for m in metadata])

    # -- list_knowledge_types ------------------------------------------------

    @kb_tool(mcp, requires=ANY, name="list_knowledge_types", description="List knowledge types (document categories) you can access.")
    async def list_knowledge_types() -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import KnowledgeType, Source

        from app.services import mcp_auth_service
        visible_sources = mcp_auth_service.apply_scope_filter(select(Source.id),_scope_view(identity))
        q = (
            select(KnowledgeType, func.count(Source.id))
            .outerjoin(Source, and_(Source.knowledge_type_id == KnowledgeType.id, Source.status == "ready", Source.id.in_(visible_sources)))
            .group_by(KnowledgeType.id)
            .order_by(KnowledgeType.sort_order, KnowledgeType.name)
        )
        async with _db().async_session_factory() as session:
            rows = list((await session.execute(q)).all())
        if not rows:
            return "No knowledge types have been defined yet."
        allowed = _scope_view(identity).allowed_knowledge_types
        if allowed is not None:
            rows = [r for r in rows if r[0].slug in allowed]
        if not rows:
            return "No accessible knowledge types found for your scope."
        lines = [f"**Knowledge types — {len(rows)} result(s)**", ""]
        for kt, count in rows:
            desc = f": {kt.description}" if kt.description else ""
            lines.append(f"- `{kt.slug}` — {kt.name} ({count} document(s)){desc}")
        lines.append("")
        lines.append("_Dùng `get_knowledge_type_docs(knowledge_type_slug=...)` để xem văn bản theo loại._")
        return payloads.knowledge_result("\n".join(lines),knowledge_types=[
            {"id":str(kt.id),"slug":kt.slug,"name":kt.name,"description":kt.description,"document_count":int(count)} for kt,count in rows],sources=[])

    # -- get_knowledge_type_docs ---------------------------------------------

    @kb_tool(mcp, requires=ANY, name="get_knowledge_type_docs", description="List the ready documents of one knowledge type.")
    async def get_knowledge_type_docs(knowledge_type_slug: str, limit: int = 10, offset: int = 0) -> Any:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import KnowledgeType, Source
        from app.services import mcp_auth_service

        limit = _clamp(limit, 1, 100, 10)
        offset = max(0,_clamp(offset,0,10**9,0))
        view = _scope_view(identity)
        slug = (knowledge_type_slug or "").strip()
        if view.allowed_knowledge_types is not None and slug not in view.allowed_knowledge_types:
            return (
                f"Access denied: knowledge type '{slug}' is outside your scope. "
                "Use `list_knowledge_types` to see the types you can access."
            )
        async with _db().async_session_factory() as session:
            kt = (await session.execute(select(KnowledgeType).where(KnowledgeType.slug == slug))).scalars().first()
            if kt is None:
                return f"Knowledge type '{slug}' not found."
            q = mcp_auth_service.apply_scope_filter(
                select(Source).where(Source.knowledge_type_id == kt.id, Source.status == "ready"), view
            ).order_by(Source.created_at.desc()).offset(offset).limit(limit+1)
            docs = list((await session.execute(q.options(*payloads.source_options()))).scalars().all())
            more = len(docs)>limit
            docs = docs[:limit]
            metadata = [payloads.source_metadata(src) for src in docs]
        if not docs:
            return payloads.knowledge_result(f"No documents found for knowledge type: **{kt.name}**",documents=[],sources=[],
                pagination={"offset":offset,"limit":limit,"has_more":False,"next_offset":None})
        lines = [f"**{kt.name} — {len(docs)} document(s)**", ""]
        for src in docs:
            lines.append(f"- {src.title or src.file_name or src.id} (ID: `{src.id}`)")
        if more:
            lines.append(f"_Còn trang sau: gọi lại với offset={offset+limit}._")
        return payloads.knowledge_result("\n".join(lines),documents=metadata,
            pagination={"offset":offset,"limit":limit,"has_more":more,"next_offset":offset+limit if more else None},
            sources=[payloads.source_citation(m) for m in metadata])

    # -- edit_wiki_page ------------------------------------------------------

    @kb_tool(
        mcp, requires=CONTRIB, name="edit_wiki_page",
        description=(
            "Replace the Markdown content of an existing wiki page (contributors only). Pass base_version from "
            "the version you read to avoid overwriting newer edits."
        ),
    )
    async def edit_wiki_page(
        slug: str,
        content_md: str,
        note: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        base_version: Optional[int] = None,
        allow_row_removal: bool = False,
    ) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import Employee, WikiPage
        from app.services import wiki_write_guard

        wiki = _wiki()
        slug = (slug or "").strip()
        if not slug or not content_md:
            return "Error: slug and content_md are required."
        if slug.lower() in _reserved_slugs(wiki):
            return "Error: reserved pages cannot be edited."
        if len(content_md) > WIKI_CONTENT_MAX_CHARS:
            return "Error: content_md exceeds 50,000 character limit."
        if scope_type is not None and scope_type not in ("global", "department"):
            return "Error: scope_type must be global or department."
        sid = None
        if scope_id:
            sid = _as_uuid(str(scope_id))
            if sid is None:
                return "Error: scope_id must be a valid UUID."

        view = _scope_view(identity)
        pf = _page_filter(identity)
        async with _db().async_session_factory() as session:
            if scope_type is not None:
                page = await wiki.get_page_by_slug(
                    session, slug, scope_type=scope_type, scope_id=sid if scope_type == "department" else None,
                    clearance=view.clearance_level, page_filter=pf,
                )
            else:
                q = select(WikiPage).where(WikiPage.slug == slug, pf, security_label.page_label_clause(view.clearance_level))
                if sid is not None:
                    q = q.where(WikiPage.scope_id == sid)
                candidates = list((await session.execute(q)).scalars().all())
                if len(candidates) > 1:
                    scopes = ", ".join(
                        "global" if (c.scope_type or "global") == "global" else f"department:{c.scope_id}"
                        for c in candidates
                    )
                    return (
                        f"Error: slug '{slug}' exists in multiple scopes ({scopes}). "
                        "Re-call with scope_type and scope_id."
                    )
                page = candidates[0] if candidates else None
            if page is None:
                return f"Page '{slug}' not found. Use search_wiki() or list_wiki_pages() to find the slug."
            employee = await session.get(Employee, view.employee_id) if view.employee_id else None
            if employee is None:
                return "Error: employee not found."
            if not _can_contribute_page(identity, page.scope_type, page.scope_id):
                return f"Error: insufficient permission to edit '{slug}'."
            if not allow_row_removal:
                refusal = wiki_write_guard.check_agent_write(page.content_md or "", content_md)
                if refusal:
                    return f"Error: {refusal}"
            current = int(page.version or 1)
            if base_version is not None and int(base_version) > current:
                return f"Error: base_version {base_version} is ahead of current page v{current}."

            conflict_cls = getattr(wiki, "DraftConflictError", None)
            try:
                draft = await wiki.create_draft(
                    session, page.id, employee.id, content_md, note=note, source="mcp_claude_desktop",
                    source_metadata={"tool": "edit_wiki_page"}, base_version=base_version, draft_kind="edit",
                )
                new_version = await _publish(session, wiki, draft, employee, page.id)
                await session.commit()
            except Exception as e:
                if conflict_cls is not None and isinstance(e, conflict_cls):
                    await _safe_rollback(session)
                    cur = getattr(e, "current_version", None)
                    base = getattr(e, "base_version", base_version)
                    return (
                        f"Error: page '{slug}' is now v{cur} (your edit was based on v{base}). "
                        "Re-read the page and re-apply your change."
                    )
                raise
        return (
            f"Page `{slug}` updated to v{new_version}. Note: the edit was published directly and is recorded "
            "in the page history under your account."
        )

    # -- create_wiki_page ----------------------------------------------------

    @kb_tool(
        mcp, requires=CONTRIB, name="create_wiki_page",
        description="Create a new wiki page (contributors only). Use edit_wiki_page to change an existing page.",
    )
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
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import Employee

        wiki = _wiki()
        slug = (slug or "").strip()
        title = (title or "").strip()
        if not slug or not title or not content_md:
            return "Error: slug, title and content_md are required."
        if slug.lower() in _reserved_slugs(wiki):
            return "Error: this slug is reserved."
        if len(content_md) > WIKI_CONTENT_MAX_CHARS:
            return "Error: content_md exceeds 50,000 character limit."
        if re.search(r"\s", slug):
            return "Error: slug must not contain whitespace."
        page_types = set(getattr(wiki, "PAGE_TYPES", None) or {"entity", "concept", "source", "topic", "index", "log", "hot"})
        if page_type not in page_types:
            return f"Error: page_type must be one of: {', '.join(sorted(page_types))}."
        scope_type = scope_type or "global"
        if scope_type not in ("global", "department"):
            return "Error: scope_type must be global or department."
        sid = None
        if scope_type == "department":
            if not scope_id:
                return "Error: scope_id is required when scope_type is department."
            sid = _as_uuid(str(scope_id))
            if sid is None:
                return "Error: scope_id must be a valid UUID."
        if not _can_contribute_page(identity, scope_type, sid):
            if scope_type == "department":
                return "Error: insufficient permission to create pages in this department."
            return "Error: insufficient permission to create wiki pages."

        view = _scope_view(identity)
        scope_label = "global scope" if scope_type == "global" else f"department {sid}"
        async with _db().async_session_factory() as session:
            existing = await wiki.get_page_by_slug(session, slug, scope_type=scope_type, scope_id=sid)
            if existing is not None:
                return f"Error: page '{slug}' already exists in {scope_label}. Use edit_wiki_page() to change it."
            employee = await session.get(Employee, view.employee_id) if view.employee_id else None
            if employee is None:
                return "Error: employee not found."
            slug_conflict = getattr(wiki, "CreateDraftSlugConflict", None)
            try:
                draft = await wiki.create_draft(
                    session, None, employee.id, content_md, note=note, source="mcp_claude_desktop",
                    source_metadata={"tool": "create_wiki_page", "slug": slug, "scope_type": scope_type,
                                     "scope_id": str(sid) if sid else None},
                    base_version=None, draft_kind="create",
                    suggested_metadata={
                        "slug": slug, "title": title, "page_type": page_type,
                        "knowledge_type_slugs": list(knowledge_type_slugs or []),
                        "scope_type": scope_type, "scope_id": str(sid) if sid else None,
                    },
                )
                new_version = await _publish(session, wiki, draft, employee, None, slug=slug)
                await session.commit()
            except Exception as e:
                is_conflict = slug_conflict is not None and isinstance(e, slug_conflict)
                if is_conflict or isinstance(e, ValueError):
                    await _safe_rollback(session)
                    return f"Error: could not create page '{slug}': {e}"
                raise
        return (
            f"Page `{slug}` created at v{new_version}. Note: the page was published directly and is recorded "
            "in the page history under your account."
        )

    # -- query_table ---------------------------------------------------------

    @kb_tool(
        mcp, requires=ANY, name="query_table",
        description=(
            "Run a read-only SQL SELECT over a spreadsheet document (Excel/CSV). Each sheet is a table; "
            "use get_source to find the source ID."
        ),
    )
    @logged_tool("query_table", query_arg="sql_query")
    async def query_table(source_id: str, sql_query: str, max_rows: int = 50) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import Source
        from app.services import storage_service
        from app.services.table_query_service import TableQueryService

        max_rows = _clamp(max_rows, 1, 100, 50)
        sid = _as_uuid(str(source_id or ""))
        if sid is None:
            return f"Invalid source_id format: '{source_id}'."
        async with _db().async_session_factory() as session:
            source = await session.get(Source, sid)
            if source is None:
                return f"Source '{source_id}' not found."
            if not source.minio_key:
                return f"Source '{source_id}' has no stored file."
            allowed = await _this()._get_allowed_source_ids(identity, session)
            if allowed is not None and str(source.id) not in allowed:
                return f"Access denied to source '{source_id}'."
            file_bytes = storage_service.storage_service.download_file(source.minio_key)
            if not file_bytes:
                return f"Failed to retrieve file content for source '{source_id}'."
            file_name = source.file_name or "table.xlsx"

        result = TableQueryService(default_max_rows=max_rows).query_excel_bytes(
            file_bytes, file_name, sql_query, max_rows
        )
        if not result.get("success"):
            return f"❌ Lỗi truy vấn bảng: {result.get('error') or 'không rõ lỗi'}"
        rows = result.get("rows") or []
        if not rows:
            return "Truy vấn thành công nhưng không có dòng phù hợp."
        columns = list(result.get("columns") or (list(rows[0].keys()) if isinstance(rows[0], dict) else []))
        lines = [f"**Kết quả truy vấn bảng `{file_name}` — {len(rows)} dòng**", ""]
        lines.append("| " + " | ".join(_md_cell(c) for c in columns) + " |")
        lines.append("|" + "|".join("---" for _ in columns) + "|")
        for row in rows:
            if isinstance(row, dict):
                vals = [row.get(c) for c in columns]
            else:
                vals = list(row)
            lines.append("| " + " | ".join(_md_cell(v) for v in vals) + " |")
        return "\n".join(lines)

    # -- skills --------------------------------------------------------------

    @kb_tool(
        mcp, requires=ANY, name="list_skills",
        description="List the skills (reusable instruction bundles) you can use; optional keyword query.",
    )
    @logged_tool("list_skills", query_arg="query")
    async def list_skills(query: Optional[str] = None, limit: int = 30) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.database.models import Skill

        limit = _clamp(limit, 1, 100, 30)
        async with _db().async_session_factory() as session:
            res = await session.execute(
                select(Skill).where(Skill.status == "active", Skill.storage_path.isnot(None)).order_by(Skill.slug)
            )
            skills = list(res.scalars().all())
            dept_map = await _skill_department_map(session, [s.id for s in skills])
        skills = [s for s in skills if _can_read_skill(identity, dept_map.get(s.id, set()))]

        async def _one(skill):
            try:
                return skill, await _load_bundle(skill)
            except Exception as e:
                logger.warning("skill bundle %s failed to load: %s", skill.slug, e)
                return skill, None

        loaded = [(s, b) for s, b in await asyncio.gather(*(_one(s) for s in skills)) if b is not None]

        entries = []
        for skill, bundle in loaded:
            meta = bundle.get("meta") or {}
            name = str(meta.get("name") or skill.name)
            desc = str(meta.get("description") or "")
            entries.append((skill, name, desc))

        if query and query.strip():
            words = [w for w in re.findall(r"\w+", _fold(query)) if w]
            scored = []
            for e in entries:
                hay = _fold(f"{e[0].slug} {e[1]} {e[2]}")
                score = sum(1 for w in words if w in hay)
                if score > 0:
                    scored.append((score, e))
            scored.sort(key=lambda t: -t[0])
            entries = [e for _, e in scored]

        if not entries:
            suffix = f" matching '{query}'" if query and query.strip() else ""
            return f"No skills found{suffix}. Use `list_skills` without a query to see every skill you can use."
        total = len(entries)
        lines = [f"**Kho kỹ năng — {total} skill(s)**", "_Gọi `read_skill(slug=...)` để đọc hướng dẫn của kỹ năng._", ""]
        for skill, name, desc in entries[:limit]:
            d = re.sub(r"\s+", " ", desc).strip()
            if len(d) > 400:
                d = d[:400] + "…"
            lines.append(f"- `{skill.slug}` (v{skill.current_version}) — {name}: {d}")
        if total > limit:
            lines.append(f"… {total - limit} more — narrow with `query`.")
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY, name="read_skill", description="Read a skill's SKILL.md instructions and list its bundled files.")
    @logged_tool("read_skill", query_arg="slug")
    async def read_skill(slug: str) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        async with _db().async_session_factory() as session:
            skill, err = await _resolve_skill(session, identity, slug)
        if err:
            return err
        bundle = await _load_bundle(skill)
        if not bundle.get("skill_md"):
            return f"Skill '{slug}' has no SKILL.md in its bundle."
        lines = [f"# Skill `{skill.slug}` (v{skill.current_version})", "", _truncate(bundle["skill_md"]), "", "## Bundled files"]
        for path in sorted(bundle.get("files") or {}):
            lines.append(f"- `{path}` ({_fmt_size(bundle['files'][path][1])})")
        lines.append("")
        lines.append("_Đọc file kèm theo bằng `read_skill_file(slug, path)`._")
        return "\n".join(lines)

    @kb_tool(mcp, requires=ANY, name="read_skill_file", description="Read one text file bundled with a skill.")
    @logged_tool("read_skill_file", query_arg="path")
    async def read_skill_file(slug: str, path: str) -> str:
        identity, err = await _this()._get_identity()
        if err:
            return err
        from app.services import storage_service

        async with _db().async_session_factory() as session:
            skill, err = await _resolve_skill(session, identity, slug)
        if err:
            return err
        bundle = await _load_bundle(skill)
        files = bundle.get("files") or {}
        p = _normalize_skill_path(path)
        if not p or p.startswith("..") or p not in files:
            listing = ", ".join(sorted(files)) or "(none)"
            return f"File '{p or path}' not found in skill '{slug}'. Files: {listing}"
        ext = posixpath.splitext(p)[1].lower()
        if ext not in SKILL_TEXT_EXTENSIONS:
            return f"File '{p}' is not a text file; only text files can be read."
        data = await asyncio.to_thread(storage_service.storage_service.download_file, files[p][0])
        text = _truncate((data or b"").decode("utf-8", errors="replace"))
        header = f"# `{skill.slug}` / `{p}`"
        if ext == ".md":
            return f"{header}\n\n{text}"
        lang = _FENCE_LANG.get(ext, "")
        return f"{header}\n\n```{lang}\n{text}\n```"


def _reserved_slugs(wiki) -> set[str]:
    vals = {"_index", "_log", "_hot", "index", "log", "hot"}
    for name in ("INDEX_SLUG", "LOG_SLUG", "HOT_SLUG"):
        v = getattr(wiki, name, None)
        if isinstance(v, str):
            vals.add(v.lower())
    return vals


async def _safe_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:
        pass


async def _publish(session, wiki, draft, employee, page_id, slug: Optional[str] = None) -> Optional[int]:
    """Publish ``draft`` right away and return the resulting page version."""
    from app.database.models import WikiPage

    result = None
    publisher = None
    try:
        from app.services import wiki_draft_publish  # type: ignore

        publisher = getattr(wiki_draft_publish, "publish_draft", None)
    except ImportError:
        publisher = None
    if publisher is not None:
        result = await publisher(session, draft, employee)
    else:
        approve = getattr(wiki, "approve_draft")
        result = await approve(session, draft.id, employee)

    version = getattr(result, "version", None)
    if isinstance(version, int):
        return version
    if isinstance(result, dict) and isinstance(result.get("version"), int):
        return result["version"]
    target_id = page_id or getattr(draft, "page_id", None) or getattr(result, "page_id", None)
    if target_id is not None:
        page = await session.get(WikiPage, target_id)
        if page is not None:
            return page.version
    if slug:
        res = await session.execute(select(WikiPage.version).where(WikiPage.slug == slug).limit(1))
        return res.scalars().first()
    return None
