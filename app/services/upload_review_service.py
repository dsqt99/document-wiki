"""Opt-in human review between extraction and searchable content creation."""
from datetime import datetime, timezone

from loguru import logger


def review_status(source):
    metadata = getattr(source, "metadata_", None)
    return metadata.get("upload_review") if isinstance(metadata, dict) else None


def mark_reviewed(source):
    from app.services.doc_metadata_service import EDITABLE_META_KEYS

    doc = dict((source.metadata_ or {}).get("doc") or {})
    reviewed_fields = {key for key in EDITABLE_META_KEYS if doc.get(key)}
    doc["manual_fields"] = sorted(set(doc.get("manual_fields") or []) | reviewed_fields)
    source.metadata_ = {
        **(source.metadata_ or {}), "upload_review": "approved",
        "doc": doc,
        "upload_reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


async def pause_for_review(session, source):
    if review_status(source) not in ("pending", "awaiting"):
        return False
    if review_status(source) == "pending":
        from app.services import doc_metadata_service

        try:
            await doc_metadata_service.store_document_metadata(session, source)
        except Exception as exc:
            logger.warning("Upload metadata review extraction failed for {}: {}", source.id, exc)
            await session.rollback()
            await session.refresh(source)
            source.metadata_ = {
                **(source.metadata_ or {}),
                "upload_review_error": "Chưa nhận diện được thông tin tự động. Bạn có thể nhập và duyệt thủ công.",
            }
    source.metadata_ = {**(source.metadata_ or {}), "upload_review": "awaiting"}
    source.status = "awaiting_approval"
    source.progress = 50
    source.progress_message = "Chờ duyệt thông tin trích xuất trước khi tạo Wiki và chỉ mục"
    source.chunk_status = "pending"
    source.wiki_status = "awaiting_approval"
    source.wiki_progress = 50
    source.wiki_progress_message = source.progress_message
    await session.commit()
    return True
