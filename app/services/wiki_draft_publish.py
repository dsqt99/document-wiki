"""Publish a wiki draft immediately — the review step is disabled.

Proposals (web UI and MCP) are still recorded as drafts so the history keeps
author + note, but they are approved in the same transaction by their author.
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, WikiPage, WikiPageDraft
from app.services import wiki_service
from app.services.wiki_chunk_service import index_wiki_page_chunks


async def publish_draft(
    session: AsyncSession, draft: WikiPageDraft, author: Employee,
) -> WikiPage:
    """Approve `draft` as its author, refresh _index/_log and re-embed the page.

    Raises wiki_service.DraftConflictError / CreateDraftSlugConflict /
    ValueError like approve_draft; the caller rolls back.
    """
    page = await wiki_service.approve_draft(
        session, draft, author.id, reviewer_note="Tự động áp dụng (không cần duyệt)",
    )
    scope_type = page.scope_type or "global"
    scope_id = page.scope_id
    await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
    action = "Created" if draft.draft_kind == "create" else "Updated"
    await wiki_service.append_log(
        session,
        f"{action} page: {page.title} ({page.slug}) → v{page.version} by {author.name or author.email}",
        scope_type=scope_type,
        scope_id=scope_id,
    )
    draft.page = page
    try:
        await index_wiki_page_chunks(session, page)
    except Exception as e:
        logger.warning(f"Failed to embed published page {page.slug}: {e}")
    return page
