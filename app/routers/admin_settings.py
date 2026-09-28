"""
Admin settings router — provider config, connection testing, dashboard stats.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Department, Employee, Source
from app.database.repository import Repository
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_sources: int
    total_departments: int
    total_employees: int


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    repo = Repository(db)
    return DashboardStats(
        total_sources=await repo.count(Source),
        total_departments=await repo.count(Department),
        total_employees=await repo.count(Employee),
    )


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    """Batch update config values."""
    settings: dict[str, str]


class TestConnectionResult(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    """Get current app settings (masked sensitive values for UI)."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    ui_config = await svc.get_all_for_ui()
    return ui_config


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    """Update config values in database."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    results = await svc.set_batch(body.settings)
    
    # Audit log
    keys_updated = list(body.settings.keys())
    await log_audit(db, _user, "update", "settings", "global", reason=f"Updated keys: {', '.join(keys_updated)}")
    await db.commit()
    return {"updated": results}


# ---------------------------------------------------------------------------
# Provider connection testing
# ---------------------------------------------------------------------------

@router.post("/settings/test-providers", response_model=dict[str, TestConnectionResult])
async def test_all_providers(db: AsyncSession = Depends(get_db)):
    """Test all configured AI providers (embedding, LLM, vision)."""
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    results = await registry.test_all()

    return {
        capability: TestConnectionResult(success=ok, message=msg)
        for capability, (ok, msg) in results.items()
    }


@router.post("/settings/test-embedding", response_model=TestConnectionResult)
async def test_embedding(db: AsyncSession = Depends(get_db)):
    """Test the configured embedding provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_embedding()
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-llm", response_model=TestConnectionResult)
async def test_llm(db: AsyncSession = Depends(get_db)):
    """Test the configured LLM provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_llm()
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-vision", response_model=TestConnectionResult)
async def test_vision(db: AsyncSession = Depends(get_db)):
    """Test the configured vision provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_vision()
        if not provider:
            return TestConnectionResult(success=False, message="No vision provider configured")
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


# ---------------------------------------------------------------------------
# Supported providers list (for admin UI dropdowns)
# ---------------------------------------------------------------------------

@router.get("/settings/providers")
async def list_providers():
    """
    Catalog-derived listing of supported providers per capability. Each model
    entry includes spec_id, label, cost, and capability metadata so the UI can
    render rich dropdowns.
    """
    from app.ai.registry import supported_providers
    return supported_providers()


# ---------------------------------------------------------------------------
# OCR & Document Extraction Testing / Preview Playground
# ---------------------------------------------------------------------------

class TestOCRConnectionRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class TestOCRConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int = 0


@router.post("/settings/test-ocr-connection", response_model=TestOCRConnectionResponse)
async def test_ocr_connection(
    body: Optional[TestOCRConnectionRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Test dedicated OCR service endpoint connectivity."""
    from app.services.config_service import ConfigService
    from app.services.ocr_service import ocr_service

    base_url = body.base_url if body else None
    api_key = body.api_key if body else None
    model = body.model if body else None

    if not base_url or not api_key:
        cfg = ConfigService(db)
        base_url = base_url or await cfg.get("ocr_base_url")
        api_key = api_key or await cfg.get("ocr_api_key")
        model = model or await cfg.get("ocr_model")

    ok, msg, latency = await ocr_service.test_connection(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    return TestOCRConnectionResponse(success=ok, message=msg, latency_ms=latency)


class TestOCRResponse(BaseModel):
    success: bool
    text: str = ""
    model: str = ""
    latency_ms: int = 0
    chars_count: int = 0
    words_count: int = 0
    error: Optional[str] = None


@router.post("/settings/test-ocr", response_model=TestOCRResponse)
async def test_ocr(
    file: UploadFile = File(...),
    override_base_url: Optional[str] = Form(None),
    override_api_key: Optional[str] = Form(None),
    override_model: Optional[str] = Form(None),
    override_prompt: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Run OCR on a single image or first page of a PDF for testing/preview."""
    import time
    from app.config import settings
    from app.services.config_service import ConfigService
    from app.services.ocr_service import ocr_service

    content = await file.read()
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    image_bytes = content
    mime_type = file.content_type or "image/png"

    if ext == "pdf":
        try:
            import pymupdf as fitz
            doc = fitz.open(stream=content, filetype="pdf")
            if len(doc) == 0:
                return TestOCRResponse(success=False, error="File PDF không có trang nào")
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_bytes = pix.tobytes("jpg", jpg_quality=85)
            mime_type = "image/jpeg"
            doc.close()
        except Exception as e:
            return TestOCRResponse(success=False, error=f"Không thể render trang PDF: {str(e)}")

    start_t = time.perf_counter()
    try:
        cfg = ConfigService(db)
        model_name = override_model or await cfg.get("ocr_model") or settings.ocr_model
        prompt_text = override_prompt or await cfg.get("ocr_prompt")

        text = await ocr_service.ocr_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt_text,
            base_url=override_base_url,
            api_key=override_api_key,
            model=model_name,
            db=db,
        )
        latency_ms = max(1, int((time.perf_counter() - start_t) * 1000))

        if text is None:
            return TestOCRResponse(
                success=False,
                error="OCR không trả về nội dung hoặc OCR endpoint chưa được cấu hình.",
                latency_ms=latency_ms,
            )

        return TestOCRResponse(
            success=True,
            text=text,
            model=model_name,
            latency_ms=latency_ms,
            chars_count=len(text),
            words_count=len(text.split()),
        )
    except Exception as e:
        latency_ms = max(1, int((time.perf_counter() - start_t) * 1000))
        return TestOCRResponse(success=False, error=str(e), latency_ms=latency_ms)


class PagePreviewItem(BaseModel):
    page_number: int
    content: str
    is_ocr: bool = False
    char_count: int = 0
    word_count: int = 0


class ExtractionStats(BaseModel):
    total_pages: int
    preview_pages_count: int
    ocr_pages_count: int
    total_words: int
    total_chars: int
    latency_ms: int


class TestExtractionResponse(BaseModel):
    success: bool
    file_name: str
    file_type: str
    stats: Optional[ExtractionStats] = None
    pages: list[PagePreviewItem] = []
    error: Optional[str] = None


@router.post("/settings/test-extraction", response_model=TestExtractionResponse)
async def test_extraction(
    file: UploadFile = File(...),
    max_pages: int = Form(3),
    engine: Optional[str] = Form(None),
    ocr_mode: Optional[str] = Form(None),
    strip_headers_footers: Optional[bool] = Form(None),
    enhance_headings: Optional[bool] = Form(None),
    override_ocr_base_url: Optional[str] = Form(None),
    override_ocr_api_key: Optional[str] = Form(None),
    override_ocr_model: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Test full document extraction pipeline with per-page preview and stats."""
    import time
    from app.services.config_service import ConfigService

    content = await file.read()
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    cfg = ConfigService(db)
    eff_engine = engine or await cfg.get("pdf_parser_engine") or "pymupdf4llm"
    eff_ocr_mode = ocr_mode or await cfg.get("ocr_mode") or "auto"
    
    if strip_headers_footers is None:
        eff_strip = (await cfg.get("pdf_strip_headers_footers")) != "false"
    else:
        eff_strip = strip_headers_footers

    if enhance_headings is None:
        eff_enhance = (await cfg.get("pdf_enhance_headings")) != "false"
    else:
        eff_enhance = enhance_headings

    eff_max_pages = max_pages if max_pages > 0 else None
    start_t = time.perf_counter()

    try:
        pages_raw: list[dict] = []
        total_doc_pages = 0

        if ext == "pdf":
            import pymupdf as fitz
            from app.services.parsers.pdf_parser import PDFParser

            doc = fitz.open(stream=content, filetype="pdf")
            total_doc_pages = len(doc)
            doc.close()

            parser = PDFParser()
            pages_raw = await parser.parse(
                file_data=content,
                file_name=filename,
                engine=eff_engine,
                ocr_mode=eff_ocr_mode,
                strip_headers_footers=eff_strip,
                enhance_headings=eff_enhance,
                max_pages=eff_max_pages,
                ocr_base_url=override_ocr_base_url,
                ocr_api_key=override_ocr_api_key,
                ocr_model=override_ocr_model,
                db=db,
            )
        else:
            from app.services.kb_service import _extract_text_from_file

            pages_raw = await _extract_text_from_file(content, filename)
            total_doc_pages = len(pages_raw)
            if eff_max_pages:
                pages_raw = pages_raw[:eff_max_pages]

        latency_ms = max(1, int((time.perf_counter() - start_t) * 1000))

        pages = [
            PagePreviewItem(
                page_number=p.get("page_number", i + 1),
                content=p.get("content", ""),
                is_ocr=bool(p.get("is_ocr", False)),
                char_count=p.get("char_count", len(p.get("content", ""))),
                word_count=p.get("word_count", len(p.get("content", "").split())),
            )
            for i, p in enumerate(pages_raw)
        ]

        ocr_pages_count = sum(1 for p in pages if p.is_ocr)
        total_words = sum(p.word_count for p in pages)
        total_chars = sum(p.char_count for p in pages)

        stats = ExtractionStats(
            total_pages=max(total_doc_pages, len(pages)),
            preview_pages_count=len(pages),
            ocr_pages_count=ocr_pages_count,
            total_words=total_words,
            total_chars=total_chars,
            latency_ms=latency_ms,
        )

        return TestExtractionResponse(
            success=True,
            file_name=filename,
            file_type=ext,
            stats=stats,
            pages=pages,
        )

    except Exception as e:
        latency_ms = max(1, int((time.perf_counter() - start_t) * 1000))
        return TestExtractionResponse(
            success=False,
            file_name=filename,
            file_type=ext,
            error=str(e),
        )

