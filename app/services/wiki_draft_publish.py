"""Publish a proposed wiki draft immediately (review step disabled).

The proposal is still stored as a draft for history, but the author approves it
in the same transaction. The caller owns commit / rollback.
"""

from __future__ import annotations

from loguru import logger

from app.services import wiki_service
from app.services.wiki_chunk_service import index_wiki_page_chunks

AUTO_PUBLISH_NOTE = "Tự động áp dụng, không cần duyệt"


async def publish_draft(session, draft, author):
    page = await wiki_service.approve_draft(session, draft, author.id, reviewer_note=AUTO_PUBLISH_NOTE)

    scope_type = getattr(page, "scope_type", None) or "global"
    scope_id = getattr(page, "scope_id", None)
    await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)

    verb = "Created" if getattr(draft, "draft_kind", "edit") == "create" else "Updated"
    who = getattr(author, "name", None) or getattr(author, "email", None) or str(author.id)
    entry = f"{verb} page: {page.title} ({page.slug}) → v{page.version} by {who}"
    await wiki_service.append_log(session, entry, scope_type=scope_type, scope_id=scope_id)

    draft.page = page
    try:
        await index_wiki_page_chunks(session, page)
    except Exception as e:
        logger.warning(f"publish_draft: chunk indexing failed for {page.slug}: {e}")
    return page
