"""Measured ingest coverage. Ready branch flags are not proof of full coverage."""
from __future__ import annotations

from copy import deepcopy


_FIELDS = {
    "extraction": ("total_pages", "text_pages", "empty_pages", "ocr_pages"),
    "source_index": ("expected", "indexed"),
    "wiki": ("expected", "published", "failed"),
}


def _metadata(source):
    value = getattr(source, "metadata_", None)
    return deepcopy(value) if isinstance(value, dict) else {}


def _attempts(source, section):
    branch = {"source_index": "chunk_attempt_id", "wiki": "wiki_attempt_id"}.get(section)
    return (str(getattr(source, "attempt_id", None) or ""),
            str(getattr(source, branch, None) or "") if branch else "")


def record_quality(source, section: str, observation: dict) -> None:
    metadata = _metadata(source)
    quality = metadata.get("processing_quality")
    quality = dict(quality) if isinstance(quality, dict) else {}
    attempt, branch = _attempts(source, section)
    quality[section] = {**observation, "_attempt_id": attempt, "_branch_attempt_id": branch}
    metadata["processing_quality"] = quality
    source.metadata_ = metadata


async def _locked_source(session, source):
    from sqlalchemy import select
    from app.database.models import Source

    result = await session.execute(
        select(Source.metadata_.label("metadata_"), Source.attempt_id, Source.chunk_attempt_id,
               Source.wiki_attempt_id).where(Source.id == source.id).with_for_update()
    )
    return result.one_or_none()


async def lock_current_attempt(session, source, section: str) -> bool:
    """Hold the source lock through branch finalization; reject a superseded job."""
    row = await _locked_source(session, source)
    return row is not None and _attempts(row, section) == _attempts(source, section)


async def save_quality(session, source, section: str, observation: dict) -> bool:
    """Merge the current attempt under a row lock. Caller commits."""
    row = await _locked_source(session, source)
    if row is None or _attempts(row, section) != _attempts(source, section):
        return False
    latest = getattr(row, "metadata_", None)
    source.metadata_ = deepcopy(latest) if isinstance(latest, dict) else {}
    record_quality(source, section, observation)
    await session.flush()
    return True


def reset_quality(source) -> None:
    metadata = _metadata(source)
    metadata.pop("processing_quality", None)
    source.metadata_ = metadata


def record_extraction(source, pages) -> None:
    # PDF records carry the real document total, even when max_pages truncates.
    total = max([len(pages), *(p.get("total_doc_pages", 0) for p in pages)])
    text = sum(bool((p.get("content") or "").strip()) for p in pages)
    empty = len(pages) - text
    ocr = sum(p.get("is_ocr") is True for p in pages) if all("is_ocr" in p for p in pages) else None
    missing_ocr = sum(p.get("ocr_required") is True and p.get("is_ocr") is not True for p in pages)
    record_quality(source, "extraction", {
        "status": "error" if not text else "partial" if empty or missing_ocr or len(pages) < total else "complete",
        "total_pages": total, "text_pages": text, "empty_pages": empty, "ocr_pages": ocr,
        "warnings": [{"code": "ocr_incomplete", "message": f"{missing_ocr} page(s) requiring OCR did not produce OCR text; native text was retained."}] if missing_ocr else [],
    })


def public_source_quality(source) -> dict:
    quality = _metadata(source).get("processing_quality") or {}
    quality = quality if isinstance(quality, dict) else {}
    result = {}
    warnings = []
    branches = {"source_index": "chunk_status", "wiki": "wiki_status"}
    for section, fields in _FIELDS.items():
        measured = quality.get(section) or {}
        measured = measured if isinstance(measured, dict) else {}
        attempt, branch = _attempts(source, section)
        if measured.get("_attempt_id", "") != attempt or measured.get("_branch_attempt_id", "") != branch:
            measured = {}
        counters = {key: value if isinstance(value := measured.get(key), int) and not isinstance(value, bool) and value >= 0 else None
                    for key in fields}
        state = measured.get("status") or "unknown"
        live = getattr(source, branches.get(section, "status"), None)
        if section in branches:
            if live == "error":
                state = "partial" if state == "partial" else "error"
            elif live in ("awaiting_approval", "plan_ready", "skipped"):
                state = live
            elif state in ("unknown", "processing") and live not in (None, "ready", "pending"):
                state = live
        if state == "complete":
            required = list(counters.values())
            if any(v is None for v in required):
                state = "unknown"
            elif section == "source_index" and counters["indexed"] != counters["expected"]:
                state = "partial"
            elif section == "wiki" and (counters["failed"] or counters["published"] != counters["expected"]):
                state = "partial"
            elif section == "extraction" and (counters["empty_pages"] or counters["text_pages"] != counters["total_pages"]):
                state = "partial"
        result[section] = {"status": state, **counters}
        if section in branches and live == "error":
            warnings.append({"code": f"{section}_failed", "message": f"{section.replace('_', ' ').capitalize()} processing failed; retry is available."})
        for item in measured.get("warnings") or []:
            if isinstance(item, dict) and isinstance(item.get("code"), str) and isinstance(item.get("message"), str):
                warnings.append({"code": item["code"], "message": item["message"]})
    extraction = result["extraction"]
    if extraction["empty_pages"]:
        warnings.append({"code": "empty_pages", "message": f'{extraction["empty_pages"]} extracted page(s) have no text.'})
    if all(extraction[k] is not None for k in ("total_pages", "text_pages", "empty_pages")):
        if extraction["text_pages"] + extraction["empty_pages"] < extraction["total_pages"]:
            warnings.append({"code": "unprocessed_pages", "message": "Some document pages were not extracted."})
    if quality.get("review_expired") and (
        getattr(source, "wiki_status", None) == "awaiting_approval"
        or getattr(source, "status", None) == "awaiting_approval"
    ):
        warnings.append({"code": "review_expired", "message": "Approval window expired. Original retained; approval or retry is available."})
    result["warnings"] = list({(w["code"], w["message"]): w for w in warnings}.values())
    return result
