"""Bounded Wiki search shared by quick search and the library."""
from __future__ import annotations

from sqlalchemy import or_, select

from app.ai.registry import ProviderRegistry
from app.database.models import WikiPage
from app.services import wiki_service
from app.services.wiki_reranker import configured_rank_candidates, search_metadata

CANDIDATE_LIMIT = 100


async def search(db, query, *, page_filter=None, limit=30, offset=0):
    q = query.strip()
    try:
        embedder = await ProviderRegistry(db).get_embedding(task='search_query')
        vector = await embedder.embed(q)
        if not vector:
            raise ValueError('Empty query embedding')
    except Exception:
        vector = None
    hits = await wiki_service.search_pages_hybrid(
        db, vector, q, top_k=CANDIDATE_LIMIT, all_scopes=True, page_filter=page_filter)
    # Include readable unindexed pages, with deterministic order and no wildcard injection.
    needle = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    stmt = select(WikiPage).where(
        WikiPage.slug.notin_(wiki_service.RESERVED_SLUGS),
        or_(*(c.ilike(needle, escape='\\') for c in (WikiPage.title, WikiPage.slug, WikiPage.summary))))
    if page_filter is not None:
        stmt = stmt.where(page_filter)
    titles = (await db.execute(stmt.order_by(WikiPage.id).limit(CANDIDATE_LIMIT))).scalars().all()
    # Reciprocal-rank fusion at page level: title-only matches can compete before the cap.
    entries, scores = {}, {}
    for rank, hit in enumerate(hits):
        page = hit['page']
        if page.id in entries:
            continue
        entries[page.id] = hit
        scores[page.id] = 1. / (60 + rank + 1)
    for rank, page in enumerate(titles):
        entries.setdefault(page.id, {'page':page})
        scores[page.id] = scores.get(page.id, 0.) + 1. / (60 + rank + 1)
    order = sorted(entries, key=lambda pid:(-scores[pid], str(pid)))[:CANDIDATE_LIMIT]
    candidates = []
    for pid in order:
        hit, page = entries[pid], entries[pid]['page']
        body = hit.get('chunk_text') or page.summary or page.content_md or ''
        candidates.append({'page':page, 'text':f'{page.title}\n{hit.get("heading_path", "")}\n{body[:2000]}'})
    result = await configured_rank_candidates(db, q, candidates)
    return {'items':result.items[offset:offset+limit], 'total':len(result.items),
            'search':search_metadata(result, lexical_fallback=vector is None,
                      candidate_limit=CANDIDATE_LIMIT, candidate_count=len(candidates))}
