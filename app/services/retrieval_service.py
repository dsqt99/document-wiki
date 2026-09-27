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


async def unified_search(
    session: AsyncSession,
    query: str,
    query_embedding: list[float],
    top_k: int = 10,
    allowed_kt_slugs: Optional[list[str]] = None,
    department_ids: Optional[list[uuid.UUID]] = None,
    project_ids: Optional[list[uuid.UUID]] = None,
    all_scopes: bool = False,
    allowed_source_ids: Optional[list[uuid.UUID]] = None,
    apply_reranker: bool = True,
) -> dict[str, Any]:
    """
    Unified multi-stage search orchestrator:
    1. Exact legal routing: checks for article & doc number match.
    2. Hybrid search (vector + vi-tokenized FTS) over wiki pages & source chunks.
    3. 1-hop graph expansion over legal knowledge graph.
    4. Reranking & MMR diversification.
    """
    from app.services import wiki_service
    import asyncio

    # 1. Exact Legal Routing
    exact_route_res = await route_exact_legal_query(session, query)

    # 2. Hybrid Search Arms
    wiki_task = wiki_service.search_pages_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=top_k * 2 if apply_reranker else top_k,
        allowed_kt_slugs=allowed_kt_slugs,
        department_ids=department_ids,
        project_ids=project_ids,
        all_scopes=all_scopes,
    )
    source_task = wiki_service.search_source_chunks_hybrid(
        session,
        query_embedding=query_embedding,
        query_text=query,
        top_k=top_k * 2 if apply_reranker else top_k,
        allowed_source_ids=allowed_source_ids,
    )

    wiki_hits, source_hits = await asyncio.gather(wiki_task, source_task)

    # 3. 1-Hop Graph Neighbor Expansion from Top Wiki Pages
    top_page_ids = [h["page"].id for h in wiki_hits[:5] if "page" in h]
    graph_neighbors = await expand_graph_neighbors(session, top_page_ids)

    # 4. Prepare candidate texts for reranking
    candidates: list[dict[str, Any]] = []
    candidate_texts: list[str] = []

    for h in wiki_hits:
        p = h["page"]
        body = getattr(p, "content_md", "") or getattr(p, "content", "")
        text = f"{p.title}\n{body}"
        candidates.append({"kind": "wiki", "hit": h, "text": text})
        candidate_texts.append(text)

    for h in source_hits:
        c = h["chunk"]
        text = c.content
        candidates.append({"kind": "source", "hit": h, "text": text})
        candidate_texts.append(text)

    # 5. Rerank if enabled and candidates exist
    reranker = RerankerService.get_instance()
    if apply_reranker and candidates and reranker:
        reranked_docs = await reranker.rerank(query, candidates, text_key="text", top_n=top_k)
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
    }
