"""
Retrieval Service — Advanced Hybrid, Graph-Expanded & Reranked Retrieval Orchestrator.

Combines:
1. Exact Legal Match Routing: Directly resolves "Điều X Văn bản Y" queries against LegalUnit.
2. Dual-Arm Hybrid Search: Cosine vector kNN + Vietnamese-tokenized BM25/FTS via RRF.
3. 1-Hop Graph Neighbor Expansion: Traverses LegalRelation edges (amendments, guidances, repeals)
   to pull in cross-document context from the legal knowledge graph.
4. Cross-Encoder Reranking & MMR Diversification: Re-scores candidates via BGE-Reranker or local fallback.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LegalRelation, LegalRelationType, LegalUnit, WikiPage
from app.services.legal_route_service import route_exact_legal_query
from app.services.reranker_service import RerankerService


async def expand_graph_neighbors(
    session: AsyncSession,
    page_ids: list[uuid.UUID],
    max_neighbors_per_node: int = 5,
) -> list[dict[str, Any]]:
    """
    Expand 1-hop relations on the legal knowledge graph for the given wiki page IDs.

    Finds the underlying LegalUnits, then queries incoming & outgoing LegalRelations
    (e.g., sua_doi, bo_sung, thay_the, bai_bo, huong_dan, quy_dinh, can_cu).
    Returns deduplicated list of related legal nodes.
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

    rel_stmt = (
        select(LegalRelation)
        .where(
            or_(*conditions),
            LegalRelation.is_effective.is_(True),
        )
        .limit(max_neighbors_per_node * len(units) * 2)
    )
    rel_res = await session.execute(rel_stmt)
    relations = rel_res.scalars().all()

    neighbors: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for rel in relations:
        rel_type_str = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)
        
        # Determine direction and neighbor details
        if rel.target_unit_id in unit_map or (rel.target_doc_number, rel.target_article_number) in unit_doc_art_map:
            # Incoming: another document modified/guided this unit
            source_u = getattr(rel, "source_unit", None)
            doc_num = (source_u.doc_number if source_u else None) or "Văn bản liên quan"
            art_num = (source_u.unit_number if source_u else None) or ""
            title = (source_u.title if source_u else None) or ""
            content = (source_u.content if source_u else None) or ""
            direction = "incoming"
            target_unit_ref = source_u
        else:
            # Outgoing: this unit references/guides another unit
            target_u = getattr(rel, "target_unit", None)
            doc_num = (target_u.doc_number if target_u else None) or rel.target_doc_number or ""
            art_num = (target_u.unit_number if target_u else None) or rel.target_article_number or ""
            title = (target_u.title if target_u else None) or ""
            content = (target_u.content if target_u else None) or ""
            direction = "outgoing"
            target_unit_ref = target_u

        dedup_key = (doc_num, art_num, rel_type_str)
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
        "🔗 **VĂN BẢN & ĐIỀU KHOẢN LIÊN QUAN TRÊN ĐỒ THỊ PHÁP LÝ**:\n"
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
        direction_arrow = "↳" if n.get("direction") == "incoming" else "→"

        lines.append(f"- {direction_arrow} **{doc}{art_ref}** [{rel_label}]{title}")
        if n.get("quote_context"):
            lines.append(f"  *Trích yếu*: \"{n['quote_context'][:180]}...\"")

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
        cur = group[0]
        for nxt in group[1:]:
            cur_idx = _get_idx(cur)
            nxt_idx = _get_idx(nxt)
            if nxt_idx == cur_idx + 1:
                # Sequential chunk: merge text
                c_cur = cur.get("chunk")
                c_nxt = nxt.get("chunk")
                if c_cur and c_nxt and hasattr(c_cur, "text") and hasattr(c_nxt, "text"):
                    c_cur.text = f"{c_cur.text}\n\n{c_nxt.text}"
                    cur["rrf"] = max(cur.get("rrf", 0.0), nxt.get("rrf", 0.0))
                elif "chunk_text" in cur and "chunk_text" in nxt:
                    cur["chunk_text"] = f"{cur['chunk_text']}\n\n{nxt['chunk_text']}"
                    cur["rrf"] = max(cur.get("rrf", 0.0), nxt.get("rrf", 0.0))
                else:
                    merged.append(cur)
                    cur = nxt
            else:
                merged.append(cur)
                cur = nxt
        merged.append(cur)

    # Sort merged results by rrf descending
    merged.sort(key=lambda x: x.get("rrf", 0.0), reverse=True)
    return merged


async def unified_search(
    session: AsyncSession,
    query: str,
    query_embedding: list[float],
    top_k: int = 10,
    allowed_kt_slugs: Optional[list[str]] = None,
    department_ids: Optional[list[uuid.UUID]] = None,
    project_ids: Optional[list[uuid.UUID]] = None,
    all_scopes: bool = False,
    allowed_source_ids: Optional[Any] = None,
    apply_reranker: bool = True,
    apply_mmr: bool = True,
    check_out_of_scope: bool = False,
) -> dict[str, Any]:
    """Unified multi-stage search orchestrator:

    1. Exact legal routing: checks for article & doc number match.
    2. Fault-tolerant hybrid search (vector + vi-tokenized FTS) over wiki pages & source chunks.
    3. Winning-chunk text extraction & threshold filtering.
    4. 1-hop graph expansion over legal knowledge graph.
    5. Cross-encoder reranking with auto-degradation floor and MMR diversification.
    """
    from app.services import wiki_service
    import asyncio

    # 1. Exact Legal Routing
    exact_route_res = await route_exact_legal_query(session, query)

    # 2. Hybrid Search Arms with Fault Tolerance
    fetch_k = top_k * 2 if apply_reranker else top_k
    wiki_task = wiki_service.search_pages_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=fetch_k,
        allowed_kt_slugs=allowed_kt_slugs,
        department_ids=department_ids,
        project_ids=project_ids,
        all_scopes=all_scopes,
    )
    source_task = wiki_service.search_source_chunks_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=fetch_k,
        allowed_source_ids=allowed_source_ids,
    )

    tasks = [wiki_task, source_task]
    if check_out_of_scope and not all_scopes:
        oos_task = wiki_service.search_pages_semantic(
            session,
            query_embedding=query_embedding,
            top_k=5,
            department_ids=department_ids,
            project_ids=project_ids,
            inverse_scope=True,
        )
        tasks.append(oos_task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    wiki_res = results[0]
    source_res = results[1]
    oos_res = results[2] if len(results) > 2 else []

    if isinstance(wiki_res, Exception):
        logger.warning(f"unified_search: wiki arm failed: {wiki_res}")
        wiki_hits = []
    else:
        wiki_hits = wiki_res or []

    if isinstance(source_res, Exception):
        logger.warning(f"unified_search: source arm failed: {source_res}")
        source_hits = []
    else:
        source_hits = source_res or []

    if isinstance(oos_res, Exception):
        logger.warning(f"unified_search: out-of-scope arm failed: {oos_res}")
        oos_hits = []
    else:
        oos_hits = oos_res or []

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

    # 5. 1-Hop Graph Neighbor Expansion from Top Wiki Pages
    top_page_ids = [h["page"].id for h in wiki_hits[:5] if "page" in h]
    graph_neighbors = []
    if top_page_ids:
        try:
            graph_neighbors = await expand_graph_neighbors(session, top_page_ids)
        except Exception as e:
            logger.warning(f"unified_search: graph expansion failed: {e}")

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
        candidates.append({"kind": "wiki", "hit": h, "text": text})

    for h in source_hits:
        c = h.get("chunk")
        text = (getattr(c, "text", "") or getattr(c, "content", "") or "") if c else ""
        s = h.get("source")
        doc_title = (getattr(s, "title", "") or getattr(s, "file_name", "") or "") if s else ""
        if doc_title:
            text = f"[{doc_title}]\n\n{text}"
        candidates.append({"kind": "source", "hit": h, "text": text})

    # 7. Cross-encoder Rerank with auto-degrade floor and MMR diversification
    reranker = RerankerService.get_instance()
    if apply_reranker and candidates and reranker and reranker.enabled:
        reranked_docs = await reranker.rerank(
            query=query,
            documents=candidates,
            text_key="text",
            top_n=top_k,
            threshold=0.2,
            degrade_floor=0.15,
            apply_mmr=apply_mmr,
        )
        final_ranked = []
        for cand in reranked_docs:
            score = cand.get("rerank_score", cand["hit"].get("rrf", 0.0))
            cand["hit"]["rerank_score"] = score
            final_ranked.append((cand["kind"], score, cand["hit"]))
    else:
        # Fallback to RRF ordering
        unified = [("wiki", h["rrf"], h) for h in wiki_hits] + [("source", h["rrf"], h) for h in source_hits]
        unified.sort(key=lambda r: r[1], reverse=True)
        final_ranked = unified[:top_k]

    return {
        "exact_match": exact_route_res,
        "ranked_results": final_ranked,
        "graph_neighbors": graph_neighbors,
        "out_of_scope_hits": oos_hits,
    }
