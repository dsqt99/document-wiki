"""Document (source) endpoints: listing, detail, file access, upload and pipeline control."""

import hashlib
import html
import inspect
import io
import logging
import math
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.database.models import (
    Employee,
    Source,
    SourceCompilationPlan,
    SourceDepartment,
    SourceImage,
    WikiPage,
)
from app.services import auth_service, security_label
from app.services.auth_service import get_current_user, require_permission
from app.services.permission_engine import (
    _get_user_permissions,
    _is_admin,
    can_access_document,
    get_scope_level,
    personal_visible_clause,
)

logger = logging.getLogger(__name__)

router = APIRouter()

from app.database.repository import Repository  # noqa: E402,F401  (tests patch this name)
from app.services.audit_service import log_audit  # noqa: E402,F401

_arq_pool = None


async def get_arq_pool():
    global _arq_pool
    if _arq_pool is None:
        from arq import create_pool

        from app.worker import redis_settings

        _arq_pool = await create_pool(redis_settings())
    return _arq_pool


_optional_bearer = HTTPBearer(auto_error=False)

SCOPE_TYPES = ("global", "department", "personal")
SCOPE_ERROR = "scope_type phải là global, department hoặc personal"
DEPT_ERROR = "You can only assign documents to your own departments"
RETRYABLE = ("error", "partial", "plan_ready")
READ_CHUNK = 64 * 1024
LIBREOFFICE_EXTS = ("doc", "ppt", "rtf")
REFINE_PHASES = ("refine", "verify", "commit")
PLAN_PRIVATE_KEYS = ("_claims", "_entities", "_concepts", "_page_drafts")

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
}
INLINE_RAW = ("pdf", "png", "jpg", "jpeg", "gif", "webp", "svg")
CODE_LIKE = ("txt", "md", "json", "xml", "yaml", "yml", "py", "sql")


def _self():
    return sys.modules[__name__]


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _enqueue(task_name: str, *args):
    pool = await _maybe_await(_self().get_arq_pool())
    return await _maybe_await(pool.enqueue_job(task_name, *args))


def _job_id_of(job) -> Optional[str]:
    jid = getattr(job, "job_id", None) if job is not None else None
    return str(jid) if jid else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def _ext_of(name: Optional[str]) -> str:
    name = (name or "").lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SourceResponse(BaseModel):
    id: uuid.UUID
    security_label: str = "INTERNAL"
    title: Optional[str] = None
    source_type: Optional[str] = None
    file_name: Optional[str] = None
    url: Optional[str] = None
    file_size: Optional[int] = None
    status: str = "pending"
    error_message: Optional[str] = None
    progress: int = 0
    progress_message: Optional[str] = None
    job_id: Optional[str] = None
    page_count: int = 0
    wiki_page_count: int = 0
    extracted_token_count: Optional[int] = None
    image_count: int = 0
    auto_recover_count: int = 0
    knowledge_type_id: Optional[uuid.UUID] = None
    knowledge_type_name: Optional[str] = None
    knowledge_type_color: Optional[str] = None
    department_ids: list[str] = Field(default_factory=list)
    department_names: list[str] = Field(default_factory=list)
    contributed_by_employee_id: Optional[uuid.UUID] = None
    contributed_by_name: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    preserve_verbatim: bool = False
    chunk_status: str = "pending"
    wiki_status: str = "pending"
    chunk_progress: int = 0
    wiki_progress: int = 0
    chunk_progress_message: Optional[str] = None
    chunk_error_message: Optional[str] = None
    wiki_progress_message: Optional[str] = None
    wiki_error_message: Optional[str] = None
    doc_meta: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SourceDetail(SourceResponse):
    full_text: Optional[str] = None
    outline: Optional[Any] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    file_url: Optional[str] = None


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class UrlSourceCreate(BaseModel):
    url: str
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: list[uuid.UUID] = Field(default_factory=list)
    scope_type: Optional[str] = None
    preserve_verbatim: bool = False
    security_label: Optional[str] = None


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: Optional[list[uuid.UUID]] = None
    scope_type: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None
    security_label: Optional[str] = None
    doc_meta: Optional[dict[str, Optional[str]]] = None


class PlanApproveBody(BaseModel):
    note: Optional[str] = None


class PlanNoteBody(BaseModel):
    note: str


def _department_pairs(source) -> tuple[list[str], list[str]]:
    ids, names = [], []
    for link in getattr(source, "departments", None) or []:
        dep_id = getattr(link, "department_id", None)
        if dep_id is None:
            continue
        ids.append(str(dep_id))
        dep = getattr(link, "department", None)
        names.append(getattr(dep, "name", None) or "")
    return ids, names


def _doc_meta_payload(source, lifecycle=None) -> Optional[dict]:
    from app.services import doc_metadata_service

    try:
        meta = doc_metadata_service.get_doc_meta(source)
    except Exception:  # noqa: BLE001
        return None
    if not meta:
        return None
    try:
        meta["validity"] = doc_metadata_service.compute_validity(meta, lifecycle)
    except Exception:  # noqa: BLE001
        pass
    return meta


def _to_response(source, wiki_page_count: int = 0, image_count: int = 0, lifecycle=None) -> SourceResponse:
    return SourceResponse(**_response_fields(source, wiki_page_count, image_count, lifecycle))


def _response_fields(source, wiki_page_count=0, image_count=0, lifecycle=None) -> dict:
    kt = getattr(source, "knowledge_type", None)
    contributor = getattr(source, "contributor", None)
    dep_ids, dep_names = _department_pairs(source)
    offsets = getattr(source, "page_offsets", None) or []
    return {
        "id": source.id,
        "security_label": security_label.normalize(getattr(source, "security_label", None)),
        "title": source.title,
        "source_type": source.source_type,
        "file_name": source.file_name,
        "url": source.url,
        "file_size": source.file_size,
        "status": source.status or "pending",
        "error_message": source.error_message,
        "progress": source.progress or 0,
        "progress_message": source.progress_message,
        "job_id": source.job_id,
        "page_count": len(offsets) if isinstance(offsets, (list, tuple)) else 0,
        "wiki_page_count": int(wiki_page_count or 0),
        "extracted_token_count": source.extracted_token_count,
        "image_count": int(image_count or 0),
        "auto_recover_count": source.auto_recover_count or 0,
        "knowledge_type_id": source.knowledge_type_id,
        "knowledge_type_name": getattr(kt, "name", None) if kt is not None else None,
        "knowledge_type_color": getattr(kt, "color", None) if kt is not None else None,
        "department_ids": dep_ids,
        "department_names": dep_names,
        "contributed_by_employee_id": source.contributed_by_employee_id,
        "contributed_by_name": getattr(contributor, "name", None) if contributor is not None else None,
        "scope_type": source.scope_type or "global",
        "scope_id": source.scope_id,
        "preserve_verbatim": bool(source.preserve_verbatim),
        "chunk_status": source.chunk_status or "pending",
        "wiki_status": source.wiki_status or "pending",
        "chunk_progress": source.chunk_progress or 0,
        "wiki_progress": source.wiki_progress or 0,
        "chunk_progress_message": source.chunk_progress_message,
        "chunk_error_message": source.chunk_error_message,
        "wiki_progress_message": source.wiki_progress_message,
        "wiki_error_message": source.wiki_error_message,
        "doc_meta": _doc_meta_payload(source, lifecycle),
        "created_at": _iso(source.created_at),
        "updated_at": _iso(source.updated_at),
    }


def _with_relations(stmt):
    return stmt.options(
        selectinload(Source.knowledge_type),
        selectinload(Source.departments).selectinload(SourceDepartment.department),
        selectinload(Source.contributor),
    )


async def _load_source(db: AsyncSession, source_id) -> Optional[Source]:
    stmt = _with_relations(select(Source).where(Source.id == source_id))
    return (await db.execute(stmt)).scalar_one_or_none()


async def _reload(db: AsyncSession, source_id) -> Source:
    stmt = _with_relations(select(Source).where(Source.id == source_id)).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one()


async def _wiki_counts(db: AsyncSession, ids: list) -> dict:
    if not ids:
        return {}
    sid = func.unnest(WikiPage.source_ids).label("sid")
    inner = select(sid).subquery()
    stmt = select(inner.c.sid, func.count()).where(inner.c.sid.in_(ids)).group_by(inner.c.sid)
    return {row[0]: int(row[1]) for row in (await db.execute(stmt)).all()}


async def _image_counts(db: AsyncSession, ids: list) -> dict:
    if not ids:
        return {}
    stmt = (
        select(SourceImage.source_id, func.count())
        .where(SourceImage.source_id.in_(ids))
        .group_by(SourceImage.source_id)
    )
    return {row[0]: int(row[1]) for row in (await db.execute(stmt)).all()}


# ---------------------------------------------------------------------------
# Access helpers (spec 02)
# ---------------------------------------------------------------------------


def _checked_label(user, value) -> str:
    if not isinstance(value, str) or not value.strip():
        return security_label.DEFAULT_LEVEL
    label = value.strip().upper()
    if label not in security_label.LEVELS:
        raise HTTPException(400, "security_label phải thuộc " + ", ".join(security_label.LEVELS))
    if not _is_admin(user) and label not in security_label.allowed_labels(getattr(user, "clearance_level", None)):
        raise HTTPException(403, "Không thể đặt nhãn cao hơn mức tiếp cận của bạn")
    return label


def source_read_filter(user):
    if _is_admin(user):
        return True, None
    perms = _self()._get_user_permissions(user)
    level = get_scope_level(perms, "doc", "read")
    if level is None:
        raise HTTPException(403, "Permission required: doc:read")
    clause = and_(
        security_label.source_label_clause(getattr(user, "clearance_level", None)),
        personal_visible_clause(getattr(user, "id", None)),
    )
    if level != "all":
        dept_ids = list(getattr(user, "department_ids", None) or [])
        no_departments = ~exists().where(SourceDepartment.source_id == Source.id)
        if dept_ids:
            in_mine = exists().where(
                SourceDepartment.source_id == Source.id, SourceDepartment.department_id.in_(dept_ids)
            )
            clause = and_(clause, or_(no_departments, in_mine))
        else:
            clause = and_(clause, no_departments)
    return True, clause


async def _authenticate_request_user(token, credentials, db, source_id):
    if credentials is not None:
        return await auth_service.employee_from_bearer(db, credentials.credentials)
    if not token:
        raise HTTPException(401, "Not authenticated")
    subject = auth_service.decode_source_file_token(token, str(source_id))
    if subject is None:
        raise HTTPException(401, "Invalid or expired token")
    try:
        emp_id = uuid.UUID(str(subject))
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid token subject")
    employee = await db.get(Employee, emp_id)
    if employee is None or not getattr(employee, "is_active", False):
        raise HTTPException(401, "User not found or inactive")
    return employee


def _has_all(user, action: str) -> bool:
    return _is_admin(user) or f"doc:{action}:all" in _self()._get_user_permissions(user)


def _check_own_departments(user, dept_ids, action: str) -> None:
    if not dept_ids or _has_all(user, action):
        return
    mine = {str(d) for d in (getattr(user, "department_ids", None) or [])}
    if any(str(d) not in mine for d in dept_ids):
        raise HTTPException(403, DEPT_ERROR)


def _foreign_personal(user, source) -> bool:
    return (
        not _is_admin(user)
        and (source.scope_type or "global") == "personal"
        and source.scope_id != getattr(user, "id", None)
    )


async def _resolve_wiki_scopes(db, source) -> list:
    from app.services import wiki_service

    return list(await wiki_service.resolve_wiki_scopes(db, source))


def _serialize_scopes(scopes) -> list:
    return [[st or "global", str(sid) if sid else None] for st, sid in scopes or []]


async def _update_dual(db, source) -> None:
    from app.services import source_status

    await source_status.update_source_dual_status(db, source)


# ---------------------------------------------------------------------------
# Listing and detail
# ---------------------------------------------------------------------------


def _sort_clauses(sort: str):
    field, _, direction = (sort or "created_desc").rpartition("_")
    if not field:
        field, direction = direction, "desc"
    asc = direction == "asc"
    doc = Source.metadata_["doc"]
    columns = {
        "created": Source.created_at,
        "title": func.lower(Source.title),
        "issued": doc["issued_date"].astext,
        "effective": doc["effective_date"].astext,
    }
    col = columns.get(field, Source.created_at)
    primary = (col.asc() if asc else col.desc()).nulls_last()
    return [primary, Source.created_at.desc()]


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    knowledge_type_id: Optional[uuid.UUID] = Query(None),
    department_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("created_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    allowed, clause = source_read_filter(user)
    if not allowed:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

    filters = []
    if clause is not None:
        filters.append(clause)
    if knowledge_type_id:
        filters.append(Source.knowledge_type_id == knowledge_type_id)
    if department_id:
        filters.append(
            exists().where(SourceDepartment.source_id == Source.id, SourceDepartment.department_id == department_id)
        )
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        if wanted:
            filters.append(Source.status.in_(wanted))
    if search:
        pattern = f"%{search}%"
        filters.append(or_(Source.title.ilike(pattern), Source.file_name.ilike(pattern)))

    total = (await db.execute(select(func.count()).select_from(Source).where(*filters))).scalar() or 0
    stmt = (
        _with_relations(select(Source).where(*filters))
        .order_by(*_sort_clauses(sort))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    ids = [s.id for s in rows]
    wiki_counts = await _wiki_counts(db, ids)
    image_counts = await _image_counts(db, ids)

    from app.services import doc_metadata_service

    numbers = []
    for s in rows:
        number = doc_metadata_service.get_doc_meta(s).get("doc_number")
        if number:
            numbers.append(number)
    lifecycles = await doc_metadata_service.load_lifecycle(db, numbers) if numbers else {}

    items = []
    for s in rows:
        number = doc_metadata_service.get_doc_meta(s).get("doc_number")
        items.append(
            _self()._to_response(
                s,
                wiki_page_count=wiki_counts.get(s.id, 0),
                image_count=image_counts.get(s.id, 0),
                lifecycle=doc_metadata_service.lifecycle_for(lifecycles, number),
            )
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


async def _source_for_read(db, user, source_id) -> Source:
    source = await _load_source(db, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")
    return source


@router.get("/sources/{source_id}", response_model=SourceDetail)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    source = await _source_for_read(db, user, source_id)
    wiki_counts = await _wiki_counts(db, [source.id])
    image_counts = await _image_counts(db, [source.id])

    from app.services import doc_metadata_service

    number = doc_metadata_service.get_doc_meta(source).get("doc_number")
    lifecycle = None
    if number:
        lifecycles = await doc_metadata_service.load_lifecycle(db, [number])
        lifecycle = doc_metadata_service.lifecycle_for(lifecycles, number)

    fields = _response_fields(source, wiki_counts.get(source.id, 0), image_counts.get(source.id, 0), lifecycle)
    download_url = preview_url = file_url = None
    if source.minio_key:
        try:
            ticket = auth_service.create_source_file_token(str(user.id), str(source.id))
            base = f"/api/sources/{source.id}"
            download_url = f"{base}/file?download=1&token={ticket}"
            preview_url = f"{base}/preview?token={ticket}"
            file_url = f"{base}/file?token={ticket}"
        except Exception as e:  # noqa: BLE001
            logger.warning("create_source_file_token failed for %s: %s", source.id, e)
    return SourceDetail(
        **fields,
        full_text=source.full_text,
        outline=source.outline_json,
        download_url=download_url,
        preview_url=preview_url,
        file_url=file_url,
    )


# ---------------------------------------------------------------------------
# File and preview
# ---------------------------------------------------------------------------


async def _file_bytes(db, user, source_id) -> tuple[Source, bytes]:
    source = await _source_for_read(db, user, source_id)
    if not source.minio_key:
        raise HTTPException(404, "Source file not stored")
    from app.services import storage_service as storage_module

    try:
        data = storage_module.storage_service.download_file(source.minio_key)
    except Exception as e:  # noqa: BLE001
        logger.error("download_file(%s) failed: %s", source.minio_key, e)
        raise HTTPException(500, "Failed to retrieve file from storage")
    return source, data


def _disposition(kind: str, file_name: str) -> str:
    encoded = quote(file_name or "file", safe="")
    return f"{kind}; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"


def _media_type(file_name: Optional[str]) -> str:
    return MEDIA_TYPES.get(_ext_of(file_name), "application/octet-stream")


@router.get("/sources/{source_id}/file")
async def get_source_file(
    source_id: uuid.UUID,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await _authenticate_request_user(token, credentials, db, source_id)
    source, data = await _file_bytes(db, user, source_id)
    name = source.file_name or "file"
    return Response(
        content=data,
        media_type=_media_type(name),
        headers={
            "Content-Disposition": _disposition("attachment" if download else "inline", name),
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",
        },
    )


_PAPER_CSS = """
body{margin:0;background:#f1f3f5;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.7;color:#1f2933}
.paper{max-width:880px;margin:24px auto;background:#fff;padding:48px 56px;box-shadow:0 2px 10px rgba(0,0,0,.08);border-radius:4px}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #cbd2d9;padding:6px 10px;vertical-align:top}
th{background:#f5f7fa}
tr:nth-child(even) td{background:#fafbfc}
img{max-width:100%}
pre{white-space:pre-wrap}
@media print{body{background:#fff}.paper{box-shadow:none;margin:0;max-width:none}}
"""

_SHEET_CSS = """
body{margin:0;background:#f1f3f5;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#1f2933}
.wrap{width:98vw;margin:12px auto;background:#fff;padding:16px;box-sizing:border-box;overflow-x:auto}
table{border-collapse:collapse;font-size:13px;margin-bottom:24px}
th,td{border:1px solid #cbd2d9;padding:4px 8px;white-space:nowrap}
thead th{position:sticky;top:0;background:#e4e7eb;z-index:1}
tr:nth-child(even) td{background:#fafbfc}
"""

_CODE_CSS = """
body{margin:0;background:#1e1e1e}
pre{margin:0;padding:20px;color:#d4d4d4;font-family:Consolas,'Courier New',monospace;font-size:13px;white-space:pre-wrap;word-wrap:break-word}
"""


def _html_page(title: str, css: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{css}</style></head><body>{body}</body></html>"
    )


def _docx_html(source, data: bytes) -> str:
    title = source.title or source.file_name or ""
    try:
        import mammoth

        converted = mammoth.convert_to_html(io.BytesIO(data)).value
        inner = converted
    except Exception as e:  # noqa: BLE001
        inner = (
            f"<p><em>Không thể trích xuất định dạng HTML: {html.escape(str(e))}</em></p>"
            f"<pre>{html.escape(source.full_text or '')}</pre>"
        )
    return _html_page(title, _PAPER_CSS, f"<div class=\"paper\">{inner}</div>")


def _sheet_html(source, data: bytes, ext: str) -> str:
    title = source.title or source.file_name or ""
    parts = []
    try:
        import pandas as pd

        if ext == "csv":
            frame = pd.read_csv(io.BytesIO(data))
            parts.append("<h3>Dữ liệu CSV</h3>")
            parts.append(frame.to_html(index=False, na_rep="", escape=True))
        else:
            sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
            for name, frame in list(sheets.items())[:10]:
                parts.append(f"<h3>Sheet: {html.escape(str(name))} ({len(frame)} dòng)</h3>")
                parts.append(frame.to_html(index=False, na_rep="", escape=True))
    except Exception as e:  # noqa: BLE001
        parts = [f"<p>Lỗi đọc bảng tính: {html.escape(str(e))}</p>"]
    return _html_page(title, _SHEET_CSS, f"<div class=\"wrap\">{''.join(parts)}</div>")


def _code_html(source, data: bytes) -> str:
    title = source.title or source.file_name or ""
    text = data.decode("utf-8", errors="replace")
    return _html_page(title, _CODE_CSS, f"<pre>{html.escape(text)}</pre>")


@router.get("/sources/{source_id}/preview")
async def preview_source_file(
    source_id: uuid.UUID,
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await _authenticate_request_user(token, credentials, db, source_id)
    source, data = await _file_bytes(db, user, source_id)
    name = source.file_name or "file"
    ext = _ext_of(name)
    no_store = {"Cache-Control": "no-store"}

    if ext in INLINE_RAW:
        return Response(
            content=data,
            media_type=_media_type(name),
            headers={**no_store, "Content-Disposition": _disposition("inline", name), "Content-Length": str(len(data))},
        )
    if ext in ("docx", "doc"):
        return HTMLResponse(_docx_html(source, data), headers=no_store)
    if ext in ("xlsx", "xls", "csv"):
        return HTMLResponse(_sheet_html(source, data, ext), headers=no_store)
    if ext in CODE_LIKE:
        return HTMLResponse(_code_html(source, data), headers=no_store)
    return Response(content=data, media_type=_media_type(name), headers=no_store)


@router.get("/sources/{source_id}/progress")
async def get_source_progress(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:read"),
):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    counts = await _wiki_counts(db, [source.id])
    offsets = source.page_offsets or []
    return {
        "id": str(source.id),
        "status": source.status,
        "progress": source.progress or 0,
        "progress_message": source.progress_message,
        "page_count": len(offsets) if isinstance(offsets, list) else 0,
        "wiki_page_count": counts.get(source.id, 0),
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _parse_department_ids(raw) -> list[uuid.UUID]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(uuid.UUID(part))
        except ValueError:
            raise HTTPException(400, f"Invalid department_id: {part}")
    return out


def _form_value(value):
    """Form(...) defaults leak through when tests call the endpoint directly."""
    return value if isinstance(value, (str, bool, int)) or value is None else None


async def _reject_upload(db, user, rejection, ext: str):
    try:
        await _self().log_audit(
            db, user, "source.upload_rejected", "source", "-",
            decision="DENY", reason=f"{rejection.code}: ext={(ext or '')[:10]}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("audit for rejected upload failed: %s", e)
    raise HTTPException(rejection.status, rejection.message)


@router.post("/sources/upload", response_model=SourceResponse)
async def upload_source(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    knowledge_type_id: Optional[str] = Form(None),
    department_ids: Optional[str] = Form(None),
    scope_type: Optional[str] = Form(None),
    scope_id: Optional[str] = Form(None),
    preserve_verbatim: bool = Form(False),
    security_label: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    from app.services import upload_guard
    from app.services.kb_service import _guess_content_type
    from app.services.parsers.libreoffice_converter import libreoffice_converter

    title = _form_value(title)
    knowledge_type_id = _form_value(knowledge_type_id)
    department_ids = _form_value(department_ids)
    scope_type = _form_value(scope_type)
    preserve_verbatim = bool(_form_value(preserve_verbatim))

    label = _checked_label(user, _form_value(security_label))

    # Name and extension first; content sniffing happens after the duplicate check.
    allowed = upload_guard.parse_extensions(settings.allowed_upload_extensions)
    raw_ext = _ext_of(getattr(file, "filename", None))
    try:
        file_name = upload_guard.safe_filename(file.filename)
        ext = upload_guard.check_extension(file_name, allowed)
    except upload_guard.UploadRejected as rejection:
        await _reject_upload(db, user, rejection, raw_ext)

    if ext in LIBREOFFICE_EXTS and not libreoffice_converter.is_available():
        raise HTTPException(
            400,
            f"Định dạng file .{ext} cần LibreOffice để chuyển đổi nhưng máy chủ chưa cài đặt. "
            "Vui lòng chuyển đổi file sang định dạng .docx hoặc .pdf trước khi tải lên.",
        )

    limit = int(settings.max_upload_size_bytes)
    digest = hashlib.sha256()
    total = 0
    await file.seek(0)
    while True:
        chunk = await file.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, f"File tải lên vượt quá giới hạn dung lượng ({limit // 1048576}MB).")
        digest.update(chunk)
    content_hash = digest.hexdigest()

    dup = (
        await db.execute(select(Source).where(Source.content_hash == content_hash, Source.status != "error"))
    ).scalars().first()
    if dup is not None:
        raise HTTPException(409, f"Tài liệu này đã tồn tại trên hệ thống (ID: {dup.id}, Tiêu đề: '{dup.title}').")

    file.file.seek(0)
    try:
        upload_guard.check_content(ext, file.file)
    except upload_guard.UploadRejected as rejection:
        await _reject_upload(db, user, rejection, ext)
    file.file.seek(0)

    dept_ids = _parse_department_ids(department_ids)
    scope = scope_type or "global"
    if scope not in SCOPE_TYPES:
        raise HTTPException(400, SCOPE_ERROR)
    resolved_scope_id = None
    if scope == "personal":
        dept_ids = []
        resolved_scope_id = user.id
        preserve_verbatim = True
    elif isinstance(scope_id, str) and scope_id.strip():
        try:
            resolved_scope_id = uuid.UUID(scope_id.strip())
        except ValueError:
            resolved_scope_id = None
    _check_own_departments(user, dept_ids, "create")

    kt_id = None
    if isinstance(knowledge_type_id, str) and knowledge_type_id.strip():
        try:
            kt_id = uuid.UUID(knowledge_type_id.strip())
        except ValueError:
            raise HTTPException(400, f"Invalid knowledge_type_id: {knowledge_type_id}")

    attempt_id = uuid.uuid4()
    source = Source(
        title=title or file_name,
        source_type="file",
        file_name=file_name,
        file_size=total,
        content_hash=content_hash,
        attempt_id=attempt_id,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=kt_id,
        contributed_by_employee_id=user.id,
        scope_type=scope,
        scope_id=resolved_scope_id,
        preserve_verbatim=preserve_verbatim,
        security_label=label,
    )
    source = await _self().Repository(db).create(source)
    await db.flush()
    for dep in dept_ids:
        db.add(SourceDepartment(source_id=source.id, department_id=dep))
    await db.flush()
    await _self().log_audit(db, user, "create", "source", source.id, reason=f"{source.title} [{label}]")
    await db.commit()
    await db.refresh(source)

    from app.services import storage_service as storage_module

    object_name = f"sources/{source.id}/original/{file_name}"
    file.file.seek(0)
    await storage_module.storage_service.upload_stream_async(
        object_name=object_name,
        stream=file.file,
        length=total,
        content_type=_guess_content_type(file_name),
    )
    source.minio_key = object_name
    source.file_name = file_name
    await db.commit()

    job = await _enqueue("ingest_file_task", str(source.id), str(attempt_id))
    source.job_id = _job_id_of(job)
    await db.commit()

    source = await _reload(db, source.id)
    return _self()._to_response(source)


@router.post("/sources/url", response_model=SourceResponse)
async def create_url_source(
    body: UrlSourceCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    label = _checked_label(user, body.security_label)
    scope = body.scope_type or "global"
    if scope not in SCOPE_TYPES:
        raise HTTPException(400, SCOPE_ERROR)
    dept_ids = list(body.department_ids or [])
    preserve = bool(body.preserve_verbatim)
    scope_id = None
    if scope == "personal":
        dept_ids, scope_id, preserve = [], user.id, True
    _check_own_departments(user, dept_ids, "create")

    attempt_id = uuid.uuid4()
    source = Source(
        title=body.title or body.url,
        source_type="url",
        url=body.url,
        attempt_id=attempt_id,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=body.knowledge_type_id,
        contributed_by_employee_id=user.id,
        scope_type=scope,
        scope_id=scope_id,
        preserve_verbatim=preserve,
        security_label=label,
    )
    source = await _self().Repository(db).create(source)
    await db.flush()
    for dep in dept_ids:
        db.add(SourceDepartment(source_id=source.id, department_id=dep))
    await db.flush()
    await _self().log_audit(db, user, "create", "source", source.id, reason=f"{source.title} [{label}]")
    await db.commit()

    job = await _enqueue("ingest_url_task", str(source.id), str(attempt_id))
    source.job_id = _job_id_of(job)
    await db.commit()
    source = await _reload(db, source.id)
    return _self()._to_response(source)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    source = await _load_source(db, source_id)
    if source is None or _foreign_personal(user, source):
        raise HTTPException(404, "Source not found")
    if body.scope_type is not None and body.scope_type not in SCOPE_TYPES:
        raise HTTPException(400, SCOPE_ERROR)

    old_depts = {link.department_id for link in (source.departments or [])}
    old_scope_type = source.scope_type or "global"
    old_scope_id = source.scope_id
    old_scopes = await _resolve_wiki_scopes(db, source)
    was_compiled = not source.preserve_verbatim

    label_change = None
    if body.security_label is not None:
        if not _has_all(user, "edit"):
            raise HTTPException(403, "Chỉ quản trị viên hoặc người có doc:edit:all được đổi nhãn bảo mật")
        new_label = _checked_label(user, body.security_label)
        old_label = security_label.normalize(source.security_label)
        if new_label != old_label:
            source.security_label = new_label
            label_change = f"{old_label}->{new_label}"

    if body.title is not None:
        source.title = body.title
    if body.knowledge_type_id is not None:
        source.knowledge_type_id = body.knowledge_type_id
    if body.doc_meta:
        from app.services import doc_metadata_service

        try:
            doc_metadata_service.apply_manual_doc_meta(source, body.doc_meta)
        except ValueError as e:
            raise HTTPException(400, str(e))

    if body.scope_type is not None:
        source.scope_type = body.scope_type
        if body.scope_type == "personal":
            source.scope_id = source.contributed_by_employee_id or user.id
        else:
            source.scope_id = None

    to_personal = body.scope_type == "personal"
    new_depts = set(old_depts)
    if body.department_ids is not None and not to_personal:
        wanted = list(dict.fromkeys(body.department_ids))
        _check_own_departments(user, wanted, "edit")
        await db.execute(delete(SourceDepartment).where(SourceDepartment.source_id == source.id))
        for dep in wanted:
            db.add(SourceDepartment(source_id=source.id, department_id=dep))
        new_depts = set(wanted)
    elif (source.scope_type or "global") in ("global", "personal"):
        await db.execute(delete(SourceDepartment).where(SourceDepartment.source_id == source.id))
        new_depts = set()

    scope_changed = (
        (source.scope_type or "global") != old_scope_type
        or source.scope_id != old_scope_id
        or new_depts != old_depts
    )

    reason = f"{source.title} [security_label {label_change}]" if label_change else source.title
    await _self().log_audit(db, user, "update", "source", source.id, reason=reason)
    await db.flush()

    serialized = _serialize_scopes(old_scopes)
    if to_personal and scope_changed:
        source.preserve_verbatim = True
        source.wiki_status = "skipped"
        source.wiki_progress = 100
        source.wiki_progress_message = "Skipped (personal source)"
        if was_compiled:
            await db.commit()
            await _enqueue("detach_source_wiki_task", str(source.id), serialized)
    elif scope_changed and source.status in ("ready", "partial") and not source.preserve_verbatim:
        source.wiki_status = "queued"
        source.wiki_progress = 0
        source.wiki_progress_message = "Re-queued scope reassignment..."
        source.wiki_error_message = None
        source.error_message = None
        await _update_dual(db, source)
        await db.flush()
        await db.commit()
        job = await _enqueue("reassign_source_scope_task", str(source.id), serialized)
        source.job_id = _job_id_of(job) or source.job_id

    await db.commit()
    source = await _reload(db, source.id)
    counts = await _wiki_counts(db, [source.id])
    return _self()._to_response(source, wiki_page_count=counts.get(source.id, 0))


# ---------------------------------------------------------------------------
# Retry and approval
# ---------------------------------------------------------------------------


def _pick_branch(source, branch: Optional[str]) -> str:
    has_text = bool((source.full_text or "").strip())
    chunk_status = source.chunk_status or "pending"
    wiki_status = source.wiki_status or "pending"
    chunk_failed = chunk_status == "error"
    wiki_failed = wiki_status == "error" or source.status == "plan_ready"
    legacy = chunk_status == "pending" and wiki_status == "pending"

    if not branch:
        if not has_text or legacy or not (chunk_failed or wiki_failed):
            branch = "all"
        elif chunk_failed and wiki_failed:
            branch = "both"
        elif chunk_failed:
            branch = "chunk"
        else:
            branch = "wiki"
    if branch in ("chunk", "wiki", "both") and not has_text:
        raise HTTPException(400, "Source has no extracted text; retry with branch=all")
    if branch in ("wiki", "both") and source.preserve_verbatim:
        branch = "chunk"
    return branch


@router.post("/sources/{source_id}/retry", response_model=SourceResponse)
async def retry_source(
    source_id: uuid.UUID,
    branch: Optional[str] = Query(None, pattern="^(chunk|wiki|all)$"),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:edit"),
):
    source = (await db.execute(_with_relations(select(Source).where(Source.id == source_id)))).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Source not found")
    if source.status not in RETRYABLE:
        raise HTTPException(400, f"Retry is only allowed for sources in {RETRYABLE} status")
    cap = int(settings.max_auto_recover_attempts)
    count = int(source.auto_recover_count or 0)
    if count >= cap and not _is_admin(_user):
        raise HTTPException(
            409,
            f"This source has failed {count} consecutive auto-recoveries (cap={cap}). "
            "Check LLM provider config and the source file, then ask an admin to reset and retry.",
        )
    if source.source_type == "url":
        if not source.url:
            raise HTTPException(400, "Source has no URL to retry")
    elif not source.minio_key:
        raise HTTPException(400, "Source file not found in storage")

    chosen = _pick_branch(source, branch)
    source.error_message = None
    job_id = None

    if chosen == "all":
        source.attempt_id = uuid.uuid4()
        source.status = "pending"
        source.progress = 0
        source.progress_message = "Queued for retry..."
        await db.flush()
        task = "ingest_url_task" if source.source_type == "url" else "ingest_file_task"
        await db.commit()
        job_id = _job_id_of(await _enqueue(task, str(source.id), str(source.attempt_id)))
    else:
        if chosen in ("chunk", "both"):
            from app import worker

            attempt = str(source.attempt_id) if source.attempt_id else None
            job_id = await worker.commit_and_enqueue_chunk_branch(db, source, attempt)
        if chosen in ("wiki", "both"):
            from app.services import source_status

            task = "ingest_refine_task" if source.pipeline_phase in REFINE_PHASES else "ingest_map_reduce_task"
            source.wiki_status = "queued"
            source.wiki_progress = 0
            source.wiki_progress_message = "Queued for retry..."
            source.wiki_error_message = None
            wiki_attempt = source_status.start_wiki_attempt(source)
            await source_status.update_source_dual_status(db, source)
            await db.commit()
            job_id = _job_id_of(await _enqueue(task, str(source.id), wiki_attempt)) or job_id

    if isinstance(job_id, str) and job_id:
        source.job_id = job_id
    await db.commit()
    source = await _reload(db, source.id)
    return _self()._to_response(source)


@router.post("/sources/{source_id}/approve-extraction")
async def approve_extraction(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    if source.status != "awaiting_approval" and source.wiki_status != "awaiting_approval":
        raise HTTPException(400, f"Source is not awaiting approval (status={source.status})")

    from app import worker
    from app.services import source_status

    has_images = (
        await db.execute(select(SourceImage.id).where(SourceImage.source_id == source.id).limit(1))
    ).first() is not None
    job_id = await worker.enqueue_post_extraction_pipeline(
        str(source.id), has_images=has_images, attempt_id_str=source_status.wiki_attempt_of(source)
    )
    source.wiki_status = "processing"
    source.wiki_progress = 56
    source.wiki_progress_message = (
        "Captioning images before extraction..." if has_images else "Extraction queued..."
    )
    await source_status.update_source_dual_status(db, source)
    source.job_id = job_id if isinstance(job_id, str) else source.job_id
    await _self().log_audit(db, user, "approve", "source_extraction", source.id, reason=source.title)
    await db.commit()
    return {
        "status": "processing",
        "job_id": job_id,
        "has_images": has_images,
        "token_count": source.extracted_token_count,
    }


# ---------------------------------------------------------------------------
# Compilation plan
# ---------------------------------------------------------------------------


async def _locked_plan(db, source_id) -> Optional[SourceCompilationPlan]:
    stmt = select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source_id).with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/sources/{source_id}/plan")
async def get_compilation_plan(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:read"),
):
    plan = (
        await db.execute(select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source_id))
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(404, "No compilation plan found for this source")
    public = {k: v for k, v in (plan.plan_json or {}).items() if k not in PLAN_PRIVATE_KEYS}
    return {
        "id": str(plan.id),
        "source_id": str(plan.source_id),
        "status": plan.status,
        "plan": public,
        "created_at": _iso(plan.created_at),
        "reviewed_at": _iso(plan.reviewed_at),
        "review_note": plan.review_note,
    }


def _check_reviewable(plan, verb: str) -> None:
    if plan is None:
        raise HTTPException(404, "No plan found for this source")
    if plan.status == "regenerating":
        raise HTTPException(409, f"Plan is being regenerated. Wait for it to finish before {verb}.")
    if plan.status != "pending_review":
        raise HTTPException(400, f"Plan is not pending review (status={plan.status})")


@router.post("/sources/{source_id}/plan/approve")
async def approve_compilation_plan(
    source_id: uuid.UUID,
    body: Optional[PlanApproveBody] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    plan = await _locked_plan(db, source_id)
    _check_reviewable(plan, "approving")
    note = body.note if body is not None else None
    plan.status = "approved"
    plan.reviewed_by = user.id
    plan.review_note = note
    plan.reviewed_at = _now()
    await _self().log_audit(db, user, "approve", "compilation_plan", plan.id, reason=note)

    from app.services import source_status

    source = await db.get(Source, source_id)
    job_id = None
    if source is not None:
        source.wiki_status = "refining"
        source.wiki_progress = 78
        source.wiki_progress_message = "Plan approved — compiling wiki pages..."
        await source_status.update_source_dual_status(db, source)
        await db.flush()
        await db.commit()
        job_id = _job_id_of(
            await _enqueue("ingest_refine_task", str(source.id), source_status.wiki_attempt_of(source))
        )
        if job_id:
            source.job_id = job_id
    await db.commit()
    return {"approved": True, "job_id": job_id}


@router.post("/sources/{source_id}/plan/reject")
async def reject_compilation_plan(
    source_id: uuid.UUID,
    body: PlanNoteBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    plan = await _locked_plan(db, source_id)
    _check_reviewable(plan, "rejecting")
    plan.status = "rejected"
    plan.reviewed_by = user.id
    plan.review_note = body.note
    plan.reviewed_at = _now()
    await _self().log_audit(db, user, "reject", "compilation_plan", plan.id, reason=(body.note or "")[:200])

    from app.services import source_status

    source = await db.get(Source, source_id)
    if source is not None:
        message = f"Compilation plan rejected: {body.note}"
        source.wiki_status = "error"
        source.wiki_error_message = message
        source.error_message = message
        await source_status.update_source_dual_status(db, source)
    await db.commit()
    return {"rejected": True}


@router.post("/sources/{source_id}/plan/regenerate")
async def regenerate_compilation_plan(
    source_id: uuid.UUID,
    body: PlanNoteBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(400, "Note is required to regenerate plan")
    plan = await _locked_plan(db, source_id)
    if plan is None:
        raise HTTPException(404, "No plan found for this source")
    if plan.status not in ("pending_review", "rejected"):
        raise HTTPException(400, f"Plan cannot be regenerated (status={plan.status})")
    plan.status = "regenerating"
    plan.review_note = note[:1000]
    await _self().log_audit(db, user, "regenerate", "compilation_plan", plan.id, reason=note[:200])
    await db.commit()
    job_id = _job_id_of(await _enqueue("regenerate_plan_task", str(source_id), note))
    return {"queued": True, "status": "regenerating", "job_id": job_id}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    source = await db.get(Source, source_id)
    if source is None or _foreign_personal(user, source):
        raise HTTPException(404, "Source not found")
    own_personal = (source.scope_type or "global") == "personal" and source.scope_id == getattr(user, "id", None)
    if not own_personal and not await can_access_document(db, user, source, "delete"):
        raise HTTPException(403, "Permission required: doc:delete")

    from app.services import storage_service as storage_module

    try:
        storage_module.storage_service.delete_prefix(f"sources/{source.id}/")
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_prefix for source %s failed: %s", source.id, e)
    try:
        from app.services.embedding_storage import delete_source_chunk_embeddings

        await delete_source_chunk_embeddings(db, source.id)
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_source_chunk_embeddings(%s) failed: %s", source.id, e)
    try:
        from app.services import wiki_service

        await wiki_service.detach_source_from_wiki(db, source.id)
        await wiki_service.regenerate_index(db, scope_type=source.scope_type or "global", scope_id=source.scope_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("wiki detach for source %s failed: %s", source.id, e)

    await _self().log_audit(db, user, "delete", "source", source.id, reason=source.title)
    await db.delete(source)
    await db.commit()
    return {"deleted": True}
