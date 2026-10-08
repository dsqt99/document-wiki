"""Shared ProgressTracker utility for background tasks."""

import uuid

from loguru import logger

# Branch B states during which progress updates belong to the wiki branch.
WIKI_ACTIVE = {"queued", "processing", "mapping", "reducing", "refining", "verifying", "indexing"}


class ProgressTracker:
    """Updates source progress in DB.

    Before the dual-pipeline split (extraction) it writes the aggregate
    source.progress/progress_message. Once branch B is running, updates go to
    wiki_progress/wiki_progress_message and the aggregate is recomputed, so
    branch A's state is never clobbered.
    """

    def __init__(self, source_id: uuid.UUID):
        self.source_id = source_id

    async def update(self, progress: int, message: str):
        from app.database import async_session_factory
        from app.database.models import Source
        from app.services.source_status import compute_source_dual_status

        async with async_session_factory() as session:
            source = await session.get(Source, self.source_id)
            if source:
                if (getattr(source, "wiki_status", None) or "pending") in WIKI_ACTIVE:
                    source.wiki_progress = progress
                    source.wiki_progress_message = message
                    source.status, source.progress, source.progress_message = (
                        compute_source_dual_status(source)
                    )
                else:
                    source.progress = progress
                    source.progress_message = message
                await session.commit()
        logger.debug(f"[{self.source_id}] Progress: {progress}% — {message}")
