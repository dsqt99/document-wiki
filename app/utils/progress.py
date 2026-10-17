"""Progress reporting for long-running source tasks."""

import logging
import uuid

logger = logging.getLogger(__name__)

WIKI_ACTIVE = frozenset({"queued", "processing", "mapping", "reducing", "refining", "verifying", "indexing"})


class ProgressTracker:
    def __init__(self, source_id):
        self.source_id = source_id

    async def update(self, progress: int, message: str) -> None:
        try:
            from app import database
            from app.database.models import Source
            from app.services.source_status import compute_source_dual_status

            sid = self.source_id if isinstance(self.source_id, uuid.UUID) else uuid.UUID(str(self.source_id))
            async with database.async_session_factory() as session:
                source = await session.get(Source, sid)
                if source is None:
                    return
                if (source.wiki_status or "pending") in WIKI_ACTIVE:
                    source.wiki_progress = progress
                    source.wiki_progress_message = message
                    status, overall, overall_msg = compute_source_dual_status(source)
                    source.status = status
                    source.progress = overall
                    source.progress_message = overall_msg
                else:
                    source.progress = progress
                    source.progress_message = message
                await session.commit()
        except Exception as e:
            logger.warning("Progress update failed for source %s: %s", self.source_id, e)
