"""Sources router — CRUD + upload + arq ingestion pipeline (compiles into wiki).

Permission model v2:
  - doc:read:own_dept → only own department + global docs
  - doc:read:all → all docs
  - Upload creates source_departments M2M entries
"""

import uuid
from typing import Optional

from arq.connections import ArqRedis, create_pool
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.database.models import Employee, ScopeType, Source, SourceDepartment, WikiPage
from app.database.repository import Repository
from app.services.audit_service import log_audit
from app.services.auth_service import (
    get_current_user,
    require_permission,
    security,
)
from app.services.permission_engine import (
    _get_user_permissions,
    get_scope_level,
)

router = APIRouter()

_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Lazy-init arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        from app.worker import _get_redis_settings
        _arq_pool = await create_pool(_get_redis_settings())
    return _arq_pool


class SourceResponse(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    source_type: Optional[str]
    file_name: Optional[str]
    url: Optional[str]
    file_size: Optional[int] = None
    status: str
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
    # Multi-department (v2)
    department_ids: list[str] = []
    department_names: list[str] = []
    contributed_by_employee_id: Optional[uuid.UUID] = None
    contributed_by_name: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    preserve_verbatim: bool = False
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class SourceDetail(SourceResponse):
    full_text: Optional[str] = None
    outline: Optional[list] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    file_url: Optional[str] = None


class SourceCreateURL(BaseModel):
    url: str
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: list[uuid.UUID] = []
    preserve_verbatim: bool = False


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: Optional[list[uuid.UUID]] = None
    scope_type: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None


async def _wiki_page_count(session: AsyncSession, source_id: uuid.UUID) -> int:
    """How many wiki pages reference this source in their source_ids array."""
    stmt = select(func.count()).select_from(WikiPage).where(WikiPage.source_ids.any(source_id))  # type: ignore[arg-type]
    return (await session.execute(stmt)).scalar_one()


async def _image_count(session: AsyncSession, source_id: uuid.UUID) -> int:
    """How many SourceImage rows exist for this source."""
    from app.database.models import SourceImage
    stmt = select(func.count()).select_from(SourceImage).where(SourceImage.source_id == source_id)
    return (await session.execute(stmt)).scalar_one()


def _to_response(source: Source, wiki_page_count: int = 0, image_count: int = 0) -> SourceResponse:
    # Extract departments from M2M relationship
    dept_ids = []
    dept_names = []
    if hasattr(source, 'departments') and source.departments:
        for sd in source.departments:
            dept_ids.append(str(sd.department_id))
            if hasattr(sd, 'department') and sd.department:
                dept_names.append(sd.department.name)

    return SourceResponse(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        file_name=source.file_name,
        url=source.url,
        file_size=source.file_size,
        status=source.status,
        error_message=source.error_message,
        progress=source.progress,
        progress_message=source.progress_message,
        job_id=source.job_id,
        page_count=len(source.page_offsets or []),
        wiki_page_count=wiki_page_count,
        extracted_token_count=source.extracted_token_count,
        image_count=image_count,
        auto_recover_count=source.auto_recover_count or 0,
        knowledge_type_id=source.knowledge_type_id,
        knowledge_type_name=source.knowledge_type.name if source.knowledge_type else None,
        knowledge_type_color=source.knowledge_type.color if source.knowledge_type else None,
        department_ids=dept_ids,
        department_names=dept_names,
        contributed_by_employee_id=source.contributed_by_employee_id,
        contributed_by_name=source.contributor.name if source.contributor else None,
        scope_type=source.scope_type or "global",
        scope_id=source.scope_id,
        preserve_verbatim=bool(source.preserve_verbatim),
        created_at=source.created_at.isoformat(),
        updated_at=source.updated_at.isoformat(),
    )


def _source_load_options():
    """Common selectinload options for Source queries."""
    return [
        selectinload(Source.knowledge_type),
        selectinload(Source.departments).selectinload(SourceDepartment.department),
        selectinload(Source.contributor),
    ]


@router.get("/sources")
async def list_sources(
    knowledge_type_id: Optional[uuid.UUID] = Query(None),
    department_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List sources with scoped filtering based on user permissions."""
    # Check user has at least some doc:read permission
    perms = _get_user_permissions(user)
    if user.role != "admin" and not any(p.startswith("doc:read:") for p in perms):
        raise HTTPException(403, "Permission required: doc:read")

    base = select(Source).options(*_source_load_options())
    count_base = select(func.count(Source.id))

    # --- Scope filtering ---
    scope_level = "all" if user.role == "admin" else get_scope_level(list(perms), "doc", "read")

    if scope_level == "own_dept":
        # Only show: global docs (no departments) OR docs overlapping the
        # user's department set. Empty set → only global docs.
        user_dept_ids = list(user.department_ids)
        global_clause = ~exists(
            select(SourceDepartment.source_id)
            .where(SourceDepartment.source_id == Source.id)
        )
        if user_dept_ids:
            dept_filter = or_(
                global_clause,
                exists(
                    select(SourceDepartment.source_id)
                    .where(
                        SourceDepartment.source_id == Source.id,
                        SourceDepartment.department_id.in_(user_dept_ids),
                    )
                ),
            )
        else:
            dept_filter = global_clause
        base = base.where(dept_filter)
        count_base = count_base.where(dept_filter)
    elif scope_level is None:
        # No doc:read permission at all
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

    # --- Additional filters ---
    if knowledge_type_id:
        base = base.where(Source.knowledge_type_id == knowledge_type_id)
        count_base = count_base.where(Source.knowledge_type_id == knowledge_type_id)
    if department_id:
        dept_exists = exists(
            select(SourceDepartment.source_id)
            .where(
                SourceDepartment.source_id == Source.id,
                SourceDepartment.department_id == department_id,
            )
        )
        base = base.where(dept_exists)
        count_base = count_base.where(dept_exists)
    if status:
        base = base.where(Source.status == status)
        count_base = count_base.where(Source.status == status)
    if search:
        like = f"%{search}%"
        base = base.where(Source.title.ilike(like) | Source.file_name.ilike(like))
        count_base = count_base.where(Source.title.ilike(like) | Source.file_name.ilike(like))

    total = (await db.execute(count_base)).scalar() or 0

    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(Source.created_at.desc()).offset(offset).limit(page_size)
    sources = (await db.execute(stmt)).scalars().all()

    items: list[SourceResponse] = []
    for s in sources:
        items.append(_to_response(s, await _wiki_page_count(db, s.id)))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.get("/sources/{source_id}")
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Check access using permission engine
    from app.services.permission_engine import can_access_document
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")

    wiki_count = await _wiki_page_count(db, source_id)
    img_count = await _image_count(db, source_id)
    download_url = None
    preview_url = None
    file_url = None
    if source.minio_key:
        try:
            from app.services.auth_service import create_access_token
            auth_token = create_access_token(str(user.id), user.role, user.name)
            download_url = f"/api/sources/{source.id}/file?download=1&token={auth_token}"
            preview_url = f"/api/sources/{source.id}/preview?token={auth_token}"
            file_url = f"/api/sources/{source.id}/file?token={auth_token}"
        except Exception as e:
            logger.warning(f"Failed to generate URLs for source {source.id}: {e}")

    base = _to_response(source, wiki_count, img_count)
    return SourceDetail(
        **base.model_dump(),
        full_text=source.full_text,
        outline=source.outline_json,
        download_url=download_url,
        preview_url=preview_url,
        file_url=file_url,
    )


def _get_source_mime_type(filename: Optional[str]) -> str:
    if not filename:
        return "application/octet-stream"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
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
    return mime_map.get(ext, "application/octet-stream")


async def _authenticate_request_user(
    token: Optional[str],
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> Employee:
    jwt_token = None
    if credentials and credentials.credentials:
        jwt_token = credentials.credentials
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from app.services.auth_service import decode_access_token
    payload = decode_access_token(jwt_token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    user = await db.get(Employee, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@router.get("/sources/{source_id}/file")
async def get_source_file(
    source_id: uuid.UUID,
    token: Optional[str] = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Serve the raw file of a source directly. Supports inline display or download."""
    user = await _authenticate_request_user(token, credentials, db)
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from app.services.permission_engine import can_access_document
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    if not source.minio_key:
        raise HTTPException(status_code=404, detail="Source file not stored")

    from app.services.storage_service import storage_service
    try:
        data = storage_service.download_file(source.minio_key)
    except Exception as e:
        logger.error(f"Failed to download file for source {source_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file from storage")

    mime_type = _get_source_mime_type(source.file_name)
    fname = source.file_name or "document"
    import urllib.parse
    quoted_name = urllib.parse.quote(fname)
    disposition = "attachment" if download else "inline"

    headers = {
        "Content-Disposition": f'{disposition}; filename="{quoted_name}"; filename*=UTF-8\'\'{quoted_name}',
        "Content-Length": str(len(data)),
        "Cache-Control": "private, max-age=3600",
    }
    return Response(content=data, media_type=mime_type, headers=headers)


@router.get("/sources/{source_id}/preview")
async def get_source_preview(
    source_id: uuid.UUID,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Return an interactive HTML preview or directly streamable content for any file format."""
    import io
    import urllib.parse
    user = await _authenticate_request_user(token, credentials, db)
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from app.services.permission_engine import can_access_document
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    if not source.minio_key:
        raise HTTPException(status_code=404, detail="Source file not stored")

    from app.services.storage_service import storage_service
    try:
        data = storage_service.download_file(source.minio_key)
    except Exception as e:
        logger.error(f"Failed to read file for preview {source_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file from storage")

    fname = (source.file_name or "").lower()

    # 1. PDF or Images: stream directly as inline content
    if fname.endswith(".pdf") or fname.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        mime_type = _get_source_mime_type(source.file_name)
        quoted_name = urllib.parse.quote(source.file_name or "document")
        return Response(
            content=data,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{quoted_name}"',
                "Content-Length": str(len(data)),
                "Cache-Control": "private, max-age=3600",
            },
        )

    # 2. Word documents (.docx, .doc): convert to HTML with mammoth
    if fname.endswith((".docx", ".doc")):
        html_body = ""
        try:
            import mammoth
            result = mammoth.convert_to_html(io.BytesIO(data))
            html_body = result.value
        except Exception as e:
            logger.warning(f"mammoth conversion failed for {source.file_name}: {e}")
            html_body = f"<p><em>Không thể trích xuất định dạng HTML: {e}</em></p><pre>{source.full_text or ''}</pre>"

        styled_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{source.title or source.file_name}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.7;
      color: #1e293b;
      background: #f8fafc;
      padding: 32px 16px;
      margin: 0;
    }}
    .document-container {{
      max-width: 880px;
      margin: 0 auto;
      background: #ffffff;
      padding: 48px 56px;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
    }}
    h1, h2, h3, h4, h5, h6 {{ color: #0f172a; margin-top: 1.6em; margin-bottom: 0.6em; font-weight: 700; }}
    h1 {{ font-size: 1.75rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.3em; }}
    h2 {{ font-size: 1.4rem; }}
    h3 {{ font-size: 1.2rem; }}
    p {{ margin: 0.8em 0; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 1.5em 0;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid #cbd5e1;
      padding: 10px 14px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background-color: #f1f5f9; font-weight: 600; color: #334155; }}
    tr:nth-child(even) td {{ background-color: #fafafa; }}
    ul, ol {{ padding-left: 28px; margin: 1em 0; }}
    li {{ margin: 0.4em 0; }}
    blockquote {{
      border-left: 4px solid #3b82f6;
      color: #475569;
      margin: 1.2em 0;
      background: #f0f9ff;
      padding: 12px 16px;
      border-radius: 0 8px 8px 0;
    }}
    a {{ color: #2563eb; text-decoration: underline; }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .document-container {{ box-shadow: none; padding: 0; }}
    }}
  </style>
</head>
<body>
  <div class="document-container">
    {html_body}
  </div>
</body>
</html>"""
        return HTMLResponse(content=styled_html)

    # 3. Excel Spreadsheets (.xlsx, .xls, .csv)
    if fname.endswith((".xlsx", ".xls", ".csv")):
        tables_parts = []
        try:
            import pandas as pd
            if fname.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(data))
                tables_parts.append("<h3>Dữ liệu CSV</h3>" + df.to_html(classes="table", index=False))
            else:
                xl = pd.ExcelFile(io.BytesIO(data))
                for sheet_name in xl.sheet_names[:10]:
                    df = xl.parse(sheet_name)
                    tables_parts.append(f"<h3>Sheet: {sheet_name} ({len(df)} dòng)</h3>" + df.to_html(classes="table", index=False))
        except Exception as e:
            tables_parts.append(f"<p>Lỗi đọc bảng tính: {e}</p>")

        tables_html = "".join(tables_parts)
        styled_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>{source.title or source.file_name}</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; padding: 24px; background: #f8fafc; color: #1e293b; }}
    .container {{ max-width: 98%; margin: 0 auto; background: #fff; padding: 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow-x: auto; }}
    h3 {{ margin-top: 24px; color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px 0; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; }}
    th {{ background: #f1f5f9; position: sticky; top: 0; }}
    tr:nth-child(even) td {{ background: #f8fafc; }}
  </style>
</head>
<body>
  <div class="container">{tables_html}</div>
</body>
</html>"""
        return HTMLResponse(content=styled_html)

    # 4. Text / Markdown / Code:
    if fname.endswith((".txt", ".md", ".json", ".xml", ".yaml", ".yml", ".py", ".sql")):
        text_content = data.decode("utf-8", errors="replace")
        import html
        escaped_text = html.escape(text_content)
        styled_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; padding: 24px; background: #0f172a; color: #e2e8f0; font-size: 14px; line-height: 1.6; margin: 0; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-all; }}
  </style>
</head>
<body>
  <pre>{escaped_text}</pre>
</body>
</html>"""
        return HTMLResponse(content=styled_html)

    # 5. Default fallback: serve raw file
    return Response(content=data, media_type=_get_source_mime_type(source.file_name))


@router.get("/sources/{source_id}/progress")
async def get_source_progress(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:read"),
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    wiki_count = await _wiki_page_count(db, source_id)
    return {
        "id": str(source.id),
        "status": source.status,
        "progress": source.progress,
        "progress_message": source.progress_message,
        "page_count": len(source.page_offsets or []),
        "wiki_page_count": wiki_count,
    }


@router.post("/sources/upload", response_model=SourceResponse)
async def upload_source(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    knowledge_type_id: Optional[str] = Form(None),
    department_ids: Optional[str] = Form(None),  # comma-separated UUIDs
    scope_type: Optional[str] = Form(None),
    scope_id: Optional[str] = Form(None),
    preserve_verbatim: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    file_data = await file.read()
    file_name = file.filename or "unknown"

    # Parse department_ids
    dept_uuids: list[uuid.UUID] = []
    if department_ids:
        for d in department_ids.split(","):
            d = d.strip()
            if d:
                try:
                    dept_uuids.append(uuid.UUID(d))
                except ValueError:
                    raise HTTPException(400, f"Invalid department_id: {d}")

    # Scope validation: own_dept users can only assign their own department
    perms = _get_user_permissions(user)
    if user.role != "admin" and "doc:create:all" not in perms:
        # User only has doc:create:own_dept — every assigned dept must overlap.
        user_depts = set(user.department_ids)
        for did in dept_uuids:
            if did not in user_depts:
                raise HTTPException(403, "You can only assign documents to your own departments")

    repo = Repository(db)
    source = Source(
        title=title or file.filename,
        source_type="file",
        file_name=file_name,
        file_size=len(file_data),
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=uuid.UUID(knowledge_type_id) if knowledge_type_id else None,
        contributed_by_employee_id=user.id,
        scope_type=scope_type or ScopeType.GLOBAL.value,
        scope_id=uuid.UUID(scope_id) if scope_id else None,
        preserve_verbatim=preserve_verbatim,
    )
    source = await repo.create(source)
    await db.flush()

    # Create M2M department links
    for did in dept_uuids:
        db.add(SourceDepartment(source_id=source.id, department_id=did))
    await db.flush()

    await log_audit(db, user, "create", "source", str(source.id), reason=source.title)
    await db.commit()
    await db.refresh(source)

    # Upload to MinIO before enqueuing so the worker downloads from storage
    from app.services.kb_service import _guess_content_type
    from app.services.storage_service import storage_service
    minio_key = f"sources/{source.id}/original/{file_name}"
    storage_service.upload_file(
        object_name=minio_key,
        data=file_data,
        content_type=_guess_content_type(file_name),
    )
    source.minio_key = minio_key
    source.file_name = file_name
    await db.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "ingest_file_task", str(source.id),
    )
    if job:
        source.job_id = job.job_id
    await db.commit()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source.id)
    )).scalar_one()

    logger.info(f"Enqueued ingestion job {job.job_id if job else 'N/A'} for source {source.id}")
    return _to_response(source)


@router.post("/sources/url", response_model=SourceResponse)
async def add_url_source(
    req: SourceCreateURL,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    repo = Repository(db)
    source = Source(
        title=req.title or req.url,
        source_type="url",
        url=req.url,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=req.knowledge_type_id,
        contributed_by_employee_id=user.id,
        scope_type=ScopeType.GLOBAL.value,
        preserve_verbatim=req.preserve_verbatim,
    )
    source = await repo.create(source)
    await db.flush()

    # Create M2M department links
    for did in req.department_ids:
        db.add(SourceDepartment(source_id=source.id, department_id=did))
    await db.flush()

    await log_audit(db, user, "create", "source", str(source.id), reason=source.title)
    await db.commit()
    await db.refresh(source)

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_url_task", str(source.id))
    if job:
        source.job_id = job.job_id
    await db.commit()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source.id)
    )).scalar_one()

    logger.info(f"Enqueued URL ingestion job {job.job_id if job else 'N/A'} for source {source.id}")
    return _to_response(source)


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:edit"),
):
    from app.services import wiki_service

    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Scope and department assignments drive where wiki pages get committed.
    # The ingestion worker reads them from DB at commit time, so an edit while
    # the pipeline is mid-flight can cause pages to land in the wrong scope
    # (visibility leak). Block those fields for any in-flight status; title
    # and knowledge_type are cosmetic for the pipeline and remain editable.
    in_flight_statuses = ("pending", "processing", "awaiting_approval", "plan_ready")
    if source.status in in_flight_statuses:
        changing_scope = body.scope_type is not None or body.scope_id is not None
        changing_dept = body.department_ids is not None
        if changing_scope or changing_dept:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot change visibility or departments while the document "
                    "is being processed. Wait until it finishes (or fails) and try again."
                ),
            )

    if body.title is not None:
        source.title = body.title
    if body.knowledge_type_id is not None:
        source.knowledge_type_id = body.knowledge_type_id
    if body.scope_type is not None:
        source.scope_type = body.scope_type
        source.scope_id = body.scope_id

    # Detect department changes and trigger re-ingestion when needed
    dept_changed = False
    if body.department_ids is not None:
        # Permission check: own_dept users may only assign their own department
        perms = _get_user_permissions(_user)
        if _user.role != "admin" and "doc:edit:all" not in perms:
            user_depts = set(_user.department_ids)
            for did in body.department_ids:
                if did not in user_depts:
                    raise HTTPException(403, "You can only assign documents to your own departments")

        old_dept_rows = (await db.execute(
            select(SourceDepartment.department_id).where(SourceDepartment.source_id == source_id)
        )).scalars().all()
        old_dept_ids = set(old_dept_rows)
        new_dept_ids = set(body.department_ids)

        # Verbatim sources have no wiki pages whose scope needs rebuilding —
        # their visibility is enforced at query time via RBAC. Skip re-ingest.
        if old_dept_ids != new_dept_ids and source.status == "ready" and not source.preserve_verbatim:
            dept_changed = True

            # Snapshot old scopes before detaching so we can regenerate their indexes
            from app.ai.mrp.pipeline import _resolve_wiki_scopes
            old_scopes = await _resolve_wiki_scopes(db, source)

            # Detach source from wiki pages in old scopes
            await wiki_service.detach_source_from_wiki(db, source.id)

            # Regenerate index for each old scope after detach
            for st, sid in old_scopes:
                await wiki_service.regenerate_index(db, scope_type=st, scope_id=sid)

        # Replace M2M rows
        await db.execute(
            sql_delete(SourceDepartment).where(SourceDepartment.source_id == source_id)
        )
        for did in body.department_ids:
            db.add(SourceDepartment(source_id=source_id, department_id=did))

    await log_audit(db, _user, "update", "source", str(source.id), reason=source.title)
    await db.flush()

    if dept_changed:
        source.status = "processing"
        source.progress = 0
        source.progress_message = "Re-queued after department change..."
        source.error_message = None
        await db.flush()

        pool = await get_arq_pool()
        job = await pool.enqueue_job("ingest_map_reduce_task", str(source_id))
        if job:
            source.job_id = job.job_id

    await db.commit()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one()
    return _to_response(source, await _wiki_page_count(db, source_id))


@router.post("/sources/{source_id}/retry", response_model=SourceResponse)
async def retry_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:edit"),
):
    """
    Retry ingestion for a source whose previous attempt failed.

    Only allowed when the source is in `error` status — successful sources
    cannot be re-ingested.
    """
    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    allowed_statuses = ("error", "plan_ready")
    if source.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Retry is only allowed for sources in {allowed_statuses} status",
        )
    # Block runaway loops: if the sweep cron has flipped this source back to
    # 'error' too many times in a row, the failure is almost certainly
    # deterministic (bad provider key, malformed file). Force human review.
    cap = settings.max_auto_recover_attempts
    if (source.auto_recover_count or 0) >= cap and _user.role != "admin":
        raise HTTPException(
            status_code=409,
            detail=(
                f"This source has failed {source.auto_recover_count} consecutive "
                f"auto-recoveries (cap={cap}). Check LLM provider config and the "
                f"source file, then ask an admin to reset and retry."
            ),
        )
    if source.source_type == "url" and not source.url:
        raise HTTPException(status_code=400, detail="Source has no URL to retry")
    if source.source_type == "file" and not source.minio_key:
        raise HTTPException(status_code=400, detail="Source file not found in storage")

    source.status = "pending"
    source.progress = 0
    source.progress_message = "Queued for retry..."
    source.error_message = None
    await db.flush()

    pool = await get_arq_pool()
    # Route to the right task based on pipeline phase
    pipeline_phase = source.pipeline_phase
    if pipeline_phase in ("refine", "verify", "commit"):
        task_name = "ingest_refine_task"
    elif pipeline_phase in ("map", "reduce", "plan_review") or source.status == "plan_ready":
        task_name = "ingest_map_reduce_task"
    else:
        task_name = "ingest_url_task" if source.source_type == "url" else "ingest_file_task"
    job = await pool.enqueue_job(task_name, str(source_id))

    if job:
        source.job_id = job.job_id
    await db.commit()
    await db.refresh(source)

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one()
    logger.info(f"Queued retry job {job.job_id if job else 'N/A'} for source {source_id}")
    return _to_response(source)


# ---------------------------------------------------------------------------
# Compilation Plan review endpoints (MRP Phase 2.5)
# ---------------------------------------------------------------------------

class PlanApproveRequest(BaseModel):
    note: Optional[str] = None


class PlanRejectRequest(BaseModel):
    note: str


class PlanRegenerateRequest(BaseModel):
    note: str


@router.get("/sources/{source_id}/plan")
async def get_compilation_plan(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:read"),
):
    """Return the current compilation plan for a source (MRP Phase 2.5)."""
    from app.database.models import SourceCompilationPlan
    plan = (await db.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source_id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No compilation plan found for this source")

    plan_json = dict(plan.plan_json or {})
    # Strip internal keys before returning
    plan_json.pop("_claims", None)
    plan_json.pop("_entities", None)
    plan_json.pop("_concepts", None)
    plan_json.pop("_page_drafts", None)

    return {
        "id": str(plan.id),
        "source_id": str(plan.source_id),
        "status": plan.status,
        "plan": plan_json,
        "created_at": plan.created_at.isoformat(),
        "reviewed_at": plan.reviewed_at.isoformat() if plan.reviewed_at else None,
        "review_note": plan.review_note,
    }


@router.post("/sources/{source_id}/approve-extraction")
async def approve_extraction(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    """Resume the pipeline for a source paused at status='awaiting_approval'.

    Triggered after a human reviews the extracted token count + image count and
    decides to spend AI tokens on it. Enqueues caption_images_task (if images
    exist) or ingest_map_reduce_task directly.
    """
    from app.worker import enqueue_post_extraction_pipeline

    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    if source.status != "awaiting_approval":
        raise HTTPException(
            400,
            f"Source is not awaiting approval (status={source.status})",
        )

    has_images = (await _image_count(db, source_id)) > 0
    job_id = await enqueue_post_extraction_pipeline(str(source_id), has_images=has_images)

    source.status = "processing"
    source.progress = 56
    source.progress_message = (
        "Captioning images before extraction..." if has_images
        else "Extraction queued..."
    )
    if job_id:
        source.job_id = job_id

    await log_audit(db, user, "approve", "source_extraction", str(source.id))
    await db.commit()

    return {
        "status": "processing",
        "job_id": job_id,
        "has_images": has_images,
        "token_count": source.extracted_token_count,
    }


@router.post("/sources/{source_id}/plan/approve")
async def approve_compilation_plan(
    source_id: uuid.UUID,
    body: PlanApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    """Approve (and optionally modify) the compilation plan, then enqueue REFINE task."""
    from datetime import datetime, timezone

    from app.database.models import SourceCompilationPlan

    plan = (await db.execute(
        select(SourceCompilationPlan)
        .where(SourceCompilationPlan.source_id == source_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan found for this source")
    if plan.status == "regenerating":
        raise HTTPException(
            status_code=409,
            detail="Plan is being regenerated. Wait for it to finish before approving.",
        )
    if plan.status != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Plan is not pending review (status={plan.status})",
        )

    plan.status = "approved"
    plan.reviewed_by = user.id
    plan.review_note = body.note
    plan.reviewed_at = datetime.now(timezone.utc)
    await log_audit(db, user, "approve", "compilation_plan", str(plan.id), reason=body.note or None)

    source = await db.get(Source, source_id)
    if source:
        source.status = "processing"
        source.progress = 78
        source.progress_message = "Plan approved — compiling wiki pages..."

    await db.flush()

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_refine_task", str(source_id))

    if job and source:
        source.job_id = job.job_id
    await db.commit()

    logger.info(f"Plan approved for source {source_id} by user {user.id}, refine job: {job.job_id if job else 'N/A'}")
    return {"approved": True, "job_id": job.job_id if job else None}


@router.post("/sources/{source_id}/plan/regenerate")
async def regenerate_compilation_plan(
    source_id: uuid.UUID,
    body: PlanRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    """
    Enqueue a background task to re-run planning with reviewer feedback.

    Plan status transitions: pending_review/rejected → regenerating → pending_review.
    Frontend should poll GET /sources/{id}/plan to detect completion (status flips
    back to pending_review and plan content updates).
    """
    from app.database.models import SourceCompilationPlan

    if not body.note.strip():
        raise HTTPException(status_code=400, detail="Note is required to regenerate plan")

    # SELECT FOR UPDATE — atomic state transition, prevents concurrent regenerate/approve.
    plan = (await db.execute(
        select(SourceCompilationPlan)
        .where(SourceCompilationPlan.source_id == source_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan found for this source")
    if plan.status not in ("pending_review", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Plan cannot be regenerated (status={plan.status})",
        )

    plan.status = "regenerating"
    plan.review_note = body.note[:1000]
    await log_audit(db, user, "regenerate", "compilation_plan", str(plan.id), reason=body.note[:200])
    await db.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job("regenerate_plan_task", str(source_id), body.note)

    logger.info(f"Plan regenerate queued for source {source_id} by user {user.id}, job: {job.job_id if job else 'N/A'}")
    return {
        "queued": True,
        "status": plan.status,
        "job_id": job.job_id if job else None,
    }


@router.post("/sources/{source_id}/plan/reject")
async def reject_compilation_plan(
    source_id: uuid.UUID,
    body: PlanRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    """Reject the compilation plan. Source moves to error status."""
    from datetime import datetime, timezone

    from app.database.models import SourceCompilationPlan

    plan = (await db.execute(
        select(SourceCompilationPlan)
        .where(SourceCompilationPlan.source_id == source_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan found for this source")
    if plan.status == "regenerating":
        raise HTTPException(
            status_code=409,
            detail="Plan is being regenerated. Wait for it to finish before rejecting.",
        )
    if plan.status != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Plan is not pending review (status={plan.status})",
        )

    plan.status = "rejected"
    plan.reviewed_by = user.id
    plan.review_note = body.note
    plan.reviewed_at = datetime.now(timezone.utc)
    await log_audit(db, user, "reject", "compilation_plan", str(plan.id), reason=body.note)

    source = await db.get(Source, source_id)
    if source:
        source.status = "error"
        source.error_message = f"Compilation plan rejected: {body.note}"

    await db.commit()
    logger.info(f"Plan rejected for source {source_id} by user {user.id}: {body.note}")
    return {"rejected": True}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:delete"),
):
    repo = Repository(db)
    source = await repo.get_by_id(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        from app.services.storage_service import storage_service
        storage_service.delete_prefix(f"sources/{source_id}/")
    except Exception as e:
        logger.warning(f"Failed to clean MinIO files for source {source_id}: {e}")

    # Detach from wiki — single-source pages are deleted, then rebuild index.
    from app.services import wiki_service
    await wiki_service.detach_source_from_wiki(db, source_id)
    await wiki_service.regenerate_index(
        db,
        scope_type=source.scope_type or "global",
        scope_id=source.scope_id,
    )

    await log_audit(db, _user, "delete", "source", str(source.id), reason=source.title)
    await repo.delete_by_id(Source, source_id)
    return {"deleted": True}
