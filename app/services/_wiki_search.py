"""Wiki page / source chunk search (semantic + hybrid vector/lexical with RRF).

Kept separate from ``wiki_service`` so that module can re-export these names:
callers (and tests) use ``wiki_service.search_pages_hybrid`` etc.

Vectors are searched in Milvus; every candidate is then re-checked against
PostgreSQL with the scope / knowledge-type / clearance filters, so a page the
user may not see never leaves this module. The lexical arm runs in PostgreSQL
on the chunk tables (``simple`` FTS over accent-folded text plus exact
document-number / quoted-phrase needles).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, Iterable, Optional, Sequence

from loguru import logger
from sqlalchemy import String, and_, func, literal_column, or_, select, tuple_
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.vi_tokenizer import (
    DASHES,
    DOC_NUMBER_RE,
    keyword_terms,
    quoted_phrases,
    strip_accents,
    term_coverage,
    websearch_all,
    websearch_any,
)
from app.database.models import (
    Source,
    WikiPage,
    get_source_chunk_embedding_model_for_dim,
    get_wiki_page_chunk_embedding_model_for_dim,
)
from app.services.search_fusion import fuse_and_sort

_HYBRID_CANDIDATE_POOL = 50
_FTS_CONFIG = "simple"
_STRONG_COVERAGE = 0.6
_RRF_K = 60
RESERVED_SLUGS = ("_index", "_log", "_hot")
_SEMANTIC_OVERFETCH = 8

_ELIGIBLE_SOURCE_STATUSES = ("ready", "partial")


# ---------------------------------------------------------------------------
# Lexical plan
# ---------------------------------------------------------------------------

def _doc_needle_regex(doc_number: str) -> Optional[str]:
    """Bounded regex for a normalized doc number, valid in Python re and PG ARE."""
    parts = [p for p in re.split(r"[/\-]", doc_number.lower()) if p]
    if not parts:
        return None
    body = r"\s*[-/.]\s*".join(re.escape(p) for p in parts)
    return r"(?<![a-z0-9/])" + body + r"(?![a-z0-9]|[-/.][a-z0-9])"


def _find_doc_numbers(query_text: str) -> list[str]:
    try:
        from app.services.legal_route_service import find_doc_numbers
    except Exception as exc:  # module chain not importable (e.g. partial install)
        logger.debug(f"legal_route_service unavailable, using local doc-number scan: {exc}")
        return _local_doc_numbers(query_text)
    return find_doc_numbers(query_text)


def _local_doc_numbers(query_text: str) -> list[str]:
    """Same normalization as legal_route_service.find_doc_numbers (fallback only)."""
    text = unicodedata.normalize("NFC", query_text or "")
    for d in DASHES:
        text = text.replace(d, "-")
    folded = strip_accents(text).lower()
    out: list[str] = []
    for m in DOC_NUMBER_RE.finditer(folded):
        n = re.sub(r"\s+", "", m.group(1)).upper()
        if n not in out:
            out.append(n)
    return out


def _lexical_plan(query_text: Optional[str]) -> tuple[list[str], list[tuple[str, str]]]:
    text = query_text or ""
    terms = keyword_terms(text)
    needles: list[tuple[str, str]] = []
    for doc in _find_doc_numbers(text):
        rx = _doc_needle_regex(doc)
        if rx and ("doc", rx) not in needles:
            needles.append(("doc", rx))
    for phrase in quoted_phrases(text):
        pair = ("phrase", phrase)
        if phrase and pair not in needles:
            needles.append(pair)
    return terms, needles


def _folded(col):
    return func.lower(func.f_unaccent(func.coalesce(col, literal_column("''"))))


def _exact_clause(col, needles: Sequence[tuple[str, str]]):
    clauses = []
    hay = _folded(col)
    for kind, pattern in needles:
        if kind == "doc":
            clauses.append(hay.op("~")(pattern))
        elif kind == "phrase":
            clauses.append(hay.contains(pattern, autoescape=True))
    if not clauses:
        return None
    return or_(*clauses)


def _ts_vector(col):
    return func.to_tsvector(
        literal_column(f"'{_FTS_CONFIG}'::regconfig"), func.f_unaccent(func.coalesce(col, literal_column("''")))
    )


def _ts_query(q: str):
    return func.websearch_to_tsquery(literal_column(f"'{_FTS_CONFIG}'::regconfig"), q)


# ---------------------------------------------------------------------------
# Shared filters
# ---------------------------------------------------------------------------

def _scope_clause(
    *,
    scope_type: Optional[str],
    scope_id: Optional[uuid.UUID],
    department_ids: Optional[Iterable[uuid.UUID]],
    project_ids: Optional[Iterable[uuid.UUID]],
    inverse_scope: bool,
    all_scopes: bool,
):
    if all_scopes:
        return None
    depts = list(department_ids or [])
    projs = list(project_ids or [])
    if inverse_scope:
        dept_c = WikiPage.scope_type == "department"
        if depts:
            dept_c = and_(dept_c, or_(WikiPage.scope_id.is_(None), WikiPage.scope_id.notin_(depts)))
        proj_c = WikiPage.scope_type == "project"
        if projs:
            proj_c = and_(proj_c, or_(WikiPage.scope_id.is_(None), WikiPage.scope_id.notin_(projs)))
        return or_(dept_c, proj_c)
    if department_ids is not None or project_ids is not None:
        parts = [WikiPage.scope_type == "global"]
        if depts:
            parts.append(and_(WikiPage.scope_type == "department", WikiPage.scope_id.in_(depts)))
        if projs:
            parts.append(and_(WikiPage.scope_type == "project", WikiPage.scope_id.in_(projs)))
        return or_(*parts)
    st = scope_type or "global"
    if scope_id is None:
        if st == "global":
            return WikiPage.scope_type == "global"
        return and_(WikiPage.scope_type == st, WikiPage.scope_id.is_(None))
    return and_(WikiPage.scope_type == st, WikiPage.scope_id == scope_id)


def _page_conditions(
    *,
    allowed_kt_slugs: Optional[Sequence[str]] = None,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
    department_ids=None,
    project_ids=None,
    inverse_scope: bool = False,
    all_scopes: bool = False,
    clearance: Optional[str] = None,
    page_filter: Any = None,
) -> list:
    conds: list = [WikiPage.slug.notin_(RESERVED_SLUGS)]
    scope = _scope_clause(
        scope_type=scope_type,
        scope_id=scope_id,
        department_ids=department_ids,
        project_ids=project_ids,
        inverse_scope=inverse_scope,
        all_scopes=all_scopes,
    )
    if scope is not None:
        conds.append(scope)
    if allowed_kt_slugs is not None:
        slugs = [s for s in allowed_kt_slugs if s]
        no_type = func.coalesce(func.cardinality(WikiPage.knowledge_type_slugs), 0) == 0
        if slugs:
            conds.append(
                or_(WikiPage.knowledge_type_slugs.op("&&")(pg_array(slugs, type_=String)), no_type)
            )
        else:
            conds.append(no_type)
    if clearance:
        from app.services.security_label import page_label_clause

        conds.append(page_label_clause(clearance))
    if page_filter is not None:
        conds.append(page_filter)
    return conds


def _source_conditions(
    allowed_source_ids: Optional[Iterable[uuid.UUID]], clearance: Optional[str]
) -> list:
    conds: list = [
        or_(
            Source.chunk_status == "ready",
            Source.status.in_(_ELIGIBLE_SOURCE_STATUSES),
            Source.preserve_verbatim.is_(True),
        )
    ]
    if allowed_source_ids is not None:
        conds.append(Source.id.in_(list(allowed_source_ids)))
    if clearance:
        from app.services.security_label import source_label_clause

        conds.append(source_label_clause(clearance))
    return conds


# ---------------------------------------------------------------------------
# Spec / Milvus helpers
# ---------------------------------------------------------------------------

async def _resolve_spec(session: AsyncSession, spec_id: Optional[str]):
    if not spec_id:
        from app.ai.registry import ProviderRegistry

        spec_id = await ProviderRegistry(session).get_active_embedding_spec_id()
    if not spec_id:
        return None
    from app.ai.embedding_catalog import get_spec

    try:
        return get_spec(spec_id)
    except KeyError:
        logger.warning(f"search: unknown embedding spec {spec_id!r}")
        return None


def _milvus_search(collection: str, vector, limit: int, spec_id: str) -> list[dict]:
    from app.services import milvus_service

    safe = str(spec_id).replace('"', '\\"')
    try:
        return milvus_service.search_milvus_vectors(
            collection, list(vector), limit=limit, filter_expr=f'model_spec_id == "{safe}"'
        ) or []
    except Exception as exc:
        logger.warning(f"Milvus search failed on {collection}: {exc}")
        return []


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _vector_hits(raw: list[dict], id_field: str) -> list[tuple[tuple[uuid.UUID, int], float]]:
    """Milvus hits -> [((object_id, chunk_index), cosine)] best-first, de-duplicated."""
    out: list[tuple[tuple[uuid.UUID, int], float]] = []
    seen: set = set()
    for hit in raw:
        oid = _as_uuid(hit.get(id_field))
        if oid is None:
            continue
        try:
            idx = int(hit.get("chunk_index", 0))
        except (TypeError, ValueError):
            continue
        key = (oid, idx)
        if key in seen:
            continue
        seen.add(key)
        out.append((key, float(hit.get("score", 0.0) or 0.0)))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


async def _lexical_arm(
    session: AsyncSession,
    *,
    base_select,
    text_col,
    key_cols: tuple,
    terms: list[str],
    needles: list[tuple[str, str]],
) -> list[dict]:
    """Run the lexical arm; returns [{"key", "row", "strong", "exact"}] in rank order.

    ``base_select`` must already select (chunk_row, parent_row) with all filters
    applied; this adds the exact / FTS predicates.
    """
    if not terms and not needles:
        return []
    out: list[dict] = []
    seen: set = set()

    def _key(chunk) -> tuple:
        return tuple(getattr(chunk, c) for c in key_cols)

    exact = _exact_clause(text_col, needles)
    if exact is not None:
        res = await session.execute(base_select.where(exact).limit(_HYBRID_CANDIDATE_POOL))
        for chunk, parent in res.all():
            k = _key(chunk)
            if k in seen:
                continue
            seen.add(k)
            out.append({"key": k, "chunk": chunk, "parent": parent, "strong": True, "exact": True})

    q_any = websearch_any(terms) if terms else ""
    if q_any and len(out) < _HYBRID_CANDIDATE_POOL:
        vec = _ts_vector(text_col)
        q_all = websearch_all(terms)
        all_match = vec.op("@@")(_ts_query(q_all))
        rank = func.ts_rank(vec, _ts_query(q_any))
        stmt = (
            base_select.where(vec.op("@@")(_ts_query(q_any)))
            .order_by(all_match.desc(), rank.desc())
            .limit(_HYBRID_CANDIDATE_POOL)
        )
        res = await session.execute(stmt)
        single = len(terms) == 1
        for chunk, parent in res.all():
            k = _key(chunk)
            if k in seen:
                continue
            seen.add(k)
            strong = single or term_coverage(terms, getattr(chunk, "text", "") or "") >= _STRONG_COVERAGE
            out.append({"key": k, "chunk": chunk, "parent": parent, "strong": strong, "exact": False})
    return out[:_HYBRID_CANDIDATE_POOL]


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

async def search_pages_semantic(
    session: AsyncSession,
    query_embedding,
    top_k: int = 10,
    allowed_kt_slugs: Optional[Sequence[str]] = None,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
    spec_id: Optional[str] = None,
    department_ids=None,
    project_ids=None,
    inverse_scope: bool = False,
    all_scopes: bool = False,
    clearance: Optional[str] = None,
    page_filter: Any = None,
) -> list[tuple[WikiPage, float]]:
    if query_embedding is None or top_k <= 0:
        return []
    spec = await _resolve_spec(session, spec_id)
    if spec is None:
        return []
    raw = _milvus_search(
        f"arkon_wiki_chunks_{spec.dimension}", query_embedding, top_k * _SEMANTIC_OVERFETCH, spec.id
    )
    best: dict[uuid.UUID, float] = {}
    for (page_id, _idx), score in _vector_hits(raw, "page_id"):
        if score > best.get(page_id, float("-inf")):
            best[page_id] = score
    if not best:
        return []
    conds = _page_conditions(
        allowed_kt_slugs=allowed_kt_slugs,
        scope_type=scope_type,
        scope_id=scope_id,
        department_ids=department_ids,
        project_ids=project_ids,
        inverse_scope=inverse_scope,
        all_scopes=all_scopes,
        clearance=clearance,
        page_filter=page_filter,
    )
    res = await session.execute(select(WikiPage).where(WikiPage.id.in_(list(best)), *conds))
    pages = list(res.scalars().all())
    ranked = sorted(((p, best[p.id]) for p in pages if p.id in best), key=lambda t: t[1], reverse=True)
    return ranked[:top_k]


async def search_pages_hybrid(
    session: AsyncSession,
    query_embedding,
    query_text: Optional[str],
    top_k: int = 10,
    allowed_kt_slugs: Optional[Sequence[str]] = None,
    spec_id: Optional[str] = None,
    department_ids=None,
    project_ids=None,
    all_scopes: bool = False,
    clearance: Optional[str] = None,
    page_filter: Any = None,
) -> list[dict]:
    if top_k <= 0:
        return []
    spec = await _resolve_spec(session, spec_id)
    if spec is None:
        return []
    Chunk = get_wiki_page_chunk_embedding_model_for_dim(spec.dimension)
    conds = _page_conditions(
        allowed_kt_slugs=allowed_kt_slugs,
        department_ids=department_ids,
        project_ids=project_ids,
        all_scopes=all_scopes,
        clearance=clearance,
        page_filter=page_filter,
    )
    base = (
        select(Chunk, WikiPage)
        .join(WikiPage, WikiPage.id == Chunk.page_id)
        .where(Chunk.model_spec_id == spec.id, *conds)
    )

    # Vector arm (Milvus, then PG re-check which also yields the chunk rows).
    info: dict[tuple, dict] = {}
    vector_keys: list[tuple] = []
    if query_embedding is not None:
        raw = _milvus_search(
            f"arkon_wiki_chunks_{spec.dimension}", query_embedding, _HYBRID_CANDIDATE_POOL, spec.id
        )
        hits = _vector_hits(raw, "page_id")
        if hits:
            keys = [k for k, _ in hits]
            res = await session.execute(
                base.where(tuple_(Chunk.page_id, Chunk.chunk_index).in_(keys))
            )
            allowed = {(c.page_id, c.chunk_index): (c, p) for c, p in res.all()}
            for key, score in hits:
                if key not in allowed:
                    continue
                chunk, page = allowed[key]
                vector_keys.append(key)
                info[key] = {"chunk": chunk, "page": page, "cosine": score, "fts": False, "exact": False}

    # Lexical arm.
    terms, needles = _lexical_plan(query_text)
    lexical = await _lexical_arm(
        session,
        base_select=base,
        text_col=Chunk.text,
        key_cols=("page_id", "chunk_index"),
        terms=terms,
        needles=needles,
    )
    lexical_keys: list[tuple] = []
    for hit in lexical:
        key = hit["key"]
        lexical_keys.append(key)
        entry = info.setdefault(
            key, {"chunk": hit["chunk"], "page": hit["parent"], "cosine": None, "fts": False, "exact": False}
        )
        entry["fts"] = entry["fts"] or bool(hit["strong"])
        entry["exact"] = entry["exact"] or bool(hit["exact"])

    if not info:
        return []

    fused = fuse_and_sort([vector_keys, lexical_keys], k=_RRF_K)
    by_page: dict[uuid.UUID, dict] = {}
    for key, score in fused:
        entry = info[key]
        page = entry["page"]
        grouped = by_page.get(page.id)
        if grouped is None:
            chunk = entry["chunk"]
            by_page[page.id] = {
                "page": page,
                "rrf": score,
                "cosine": entry["cosine"],
                "heading_path": getattr(chunk, "heading_path", "") or "",
                "fts_matched": entry["fts"],
                "exact_match": entry["exact"],
                "chunk_index": chunk.chunk_index,
                "chunk_text": getattr(chunk, "text", "") or "",
            }
        else:
            grouped["fts_matched"] = grouped["fts_matched"] or entry["fts"]
            grouped["exact_match"] = grouped["exact_match"] or entry["exact"]
    results = sorted(by_page.values(), key=lambda d: d["rrf"], reverse=True)
    return results[:top_k]


async def search_source_chunks_hybrid(
    session: AsyncSession,
    query_embedding,
    query_text: Optional[str],
    top_k: int = 10,
    allowed_source_ids: Optional[Iterable[uuid.UUID]] = None,
    spec_id: Optional[str] = None,
    clearance: Optional[str] = None,
) -> list[dict]:
    if allowed_source_ids is not None:
        allowed_source_ids = list(allowed_source_ids)
        if not allowed_source_ids:
            return []
    if top_k <= 0:
        return []
    spec = await _resolve_spec(session, spec_id)
    if spec is None:
        return []
    Chunk = get_source_chunk_embedding_model_for_dim(spec.dimension)
    base = (
        select(Chunk, Source)
        .join(Source, Source.id == Chunk.source_id)
        .where(Chunk.model_spec_id == spec.id, *_source_conditions(allowed_source_ids, clearance))
    )

    info: dict[tuple, dict] = {}
    vector_keys: list[tuple] = []
    if query_embedding is not None:
        raw = _milvus_search(
            f"arkon_source_chunks_{spec.dimension}", query_embedding, _HYBRID_CANDIDATE_POOL, spec.id
        )
        hits = _vector_hits(raw, "source_id")
        if hits:
            keys = [k for k, _ in hits]
            res = await session.execute(
                base.where(tuple_(Chunk.source_id, Chunk.chunk_index).in_(keys))
            )
            allowed = {(c.source_id, c.chunk_index): (c, s) for c, s in res.all()}
            for key, score in hits:
                if key not in allowed:
                    continue
                chunk, src = allowed[key]
                vector_keys.append(key)
                info[key] = {"chunk": chunk, "source": src, "cosine": score, "fts": False, "exact": False}

    terms, needles = _lexical_plan(query_text)
    lexical = await _lexical_arm(
        session,
        base_select=base,
        text_col=Chunk.text,
        key_cols=("source_id", "chunk_index"),
        terms=terms,
        needles=needles,
    )
    lexical_keys: list[tuple] = []
    for hit in lexical:
        key = hit["key"]
        lexical_keys.append(key)
        entry = info.setdefault(
            key, {"chunk": hit["chunk"], "source": hit["parent"], "cosine": None, "fts": False, "exact": False}
        )
        entry["fts"] = entry["fts"] or bool(hit["strong"])
        entry["exact"] = entry["exact"] or bool(hit["exact"])

    if not info:
        return []
    fused = fuse_and_sort([vector_keys, lexical_keys], k=_RRF_K)
    out: list[dict] = []
    for key, score in fused[:top_k]:
        entry = info[key]
        out.append(
            {
                "source": entry["source"],
                "chunk": entry["chunk"],
                "rrf": score,
                "cosine": entry["cosine"],
                "heading_path": "",
                "fts_matched": entry["fts"],
                "exact_match": entry["exact"],
            }
        )
    return out


__all__ = [
    "_HYBRID_CANDIDATE_POOL",
    "_FTS_CONFIG",
    "_STRONG_COVERAGE",
    "RESERVED_SLUGS",
    "_lexical_plan",
    "search_pages_semantic",
    "search_pages_hybrid",
    "search_source_chunks_hybrid",
]
