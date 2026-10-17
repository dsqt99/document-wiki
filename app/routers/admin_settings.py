"""Admin settings: config values, provider tests, OCR and extraction previews (06 §5).

The test-* endpoints intentionally carry no auth dependency (spec 06 §12 #5).
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import get_current_user, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()

PROVIDER_LABELS = {
    "google": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "ollama": "Ollama",
    "voyage": "Voyage AI",
    "cohere": "Cohere",
}
OPTIONAL_MODEL_FIELDS = (
    "context_window_tokens", "max_output_tokens", "supports_tools", "supports_vision", "dimension",
    "max_input_tokens", "cost_per_1m_input_tokens", "cost_per_1m_output_tokens", "cost_per_1m_tokens",
    "cost_per_image", "notes",
)
MASK_CHAR = "•"
PREVIEW_IMAGE_BUDGET = 8 * 1024 * 1024
PREVIEW_MIN_IMAGE_BYTES = 2048
OVER_BUDGET_NOTE = "*[Ảnh — quá dung lượng xem trước]*"
_IMG_RE = re.compile(r"<!--img:([^>]*?)-->")
_IMAGE_EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".bmp": "image/bmp", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
}


def _config(db):
    from app.services import config_service

    return config_service.ConfigService(db)


def _mask_value(value: str) -> str:
    if len(value) > 8:
        return MASK_CHAR * 8 + value[-4:]
    return MASK_CHAR * len(value)


# ---------------------------------------------------------------- dashboard / settings


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    from app.database.models import Department, Employee, Source

    async def _count(model) -> int:
        try:
            return int((await db.execute(select(func.count()).select_from(model))).scalar() or 0)
        except Exception as e:
            logger.warning("dashboard count failed for %s: %s", model.__name__, e)
            return 0

    return {
        "total_sources": await _count(Source),
        "total_departments": await _count(Department),
        "total_employees": await _count(Employee),
    }


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    from app.services import config_service

    raw = await _config(db).get_all()
    out: dict = {}
    for key, value in raw.items():
        if config_service._is_sensitive(key):
            out[key] = _mask_value(value) if value else value
            out[f"{key}_configured"] = bool(value)
        else:
            out[key] = value
    return out


class SettingsUpdate(BaseModel):
    settings: dict[str, Optional[str]]


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user=require_permission("org:settings:manage"),
):
    from app.services import audit_service

    updated = await _config(db).set_batch(body.settings)
    changed = sorted(k for k, ok in updated.items() if ok)
    await audit_service.log_audit(
        db, user, "update", "settings", "global", reason=f"Updated keys: {', '.join(changed)}"
    )
    await db.commit()
    return {"updated": updated}


# ---------------------------------------------------------------- provider tests


def _registry(db):
    from app.ai.registry import ProviderRegistry

    return ProviderRegistry(db)


@router.post("/settings/test-providers")
async def test_providers(db: AsyncSession = Depends(get_db)):
    results = await _registry(db).test_all()
    out = {}
    for kind in ("embedding", "llm", "vision"):
        res = results.get(kind) or (False, "Not configured: unknown")
        entry = {"success": bool(res[0]), "message": res[1]}
        if len(res) > 2 and res[2] is not None:
            entry["details"] = res[2]
        out[kind] = entry
    return out


async def _run_test(build):
    try:
        provider = await build()
        if provider is None:
            return None
        ok, msg = (await provider.test_connection())[:2]
        return {"success": bool(ok), "message": msg}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/settings/test-embedding")
async def test_embedding(db: AsyncSession = Depends(get_db)):
    return await _run_test(_registry(db).get_embedding)


@router.post("/settings/test-llm")
async def test_llm(db: AsyncSession = Depends(get_db)):
    return await _run_test(_registry(db).get_llm)


@router.post("/settings/test-vision")
async def test_vision(db: AsyncSession = Depends(get_db)):
    res = await _run_test(_registry(db).get_vision)
    return res or {"success": False, "message": "No vision provider configured"}


@router.get("/settings/providers")
async def list_providers():
    from app.ai.registry import ProviderRegistry

    supported = ProviderRegistry.supported_providers() or {}
    out: dict = {}
    for kind in ("embedding", "llm", "vision"):
        groups = supported.get(kind) or {}
        items = groups.items() if isinstance(groups, dict) else [
            (g.get("id"), g.get("models", [])) for g in groups
        ]
        providers = []
        for pid, models in items:
            pid = getattr(pid, "value", pid)
            entries = []
            for m in models or []:
                d = m if isinstance(m, dict) else vars(m)
                entry = {"id": d.get("id"), "model_id": d.get("model_id"), "label": d.get("label")}
                for f in OPTIONAL_MODEL_FIELDS:
                    if d.get(f) is not None:
                        entry[f] = d[f]
                entries.append(entry)
            providers.append({"id": pid, "name": PROVIDER_LABELS.get(pid, str(pid)), "models": entries})
        out[kind] = providers
    return out


# ---------------------------------------------------------------- OCR


class OCRConnectionTest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    model_spec_id: Optional[str] = None


async def _ocr_endpoint(db, spec_id, base_url, api_key, model):
    """Resolve (base_url, api_key, model); spec id wins, gaps fall back to config."""
    if spec_id:
        from app.routers import admin_custom_models

        base_url, model, api_key = await admin_custom_models.resolve_ocr_endpoint(db, spec_id)
    cfg = _config(db)
    if not base_url:
        base_url = await cfg.get("ocr_base_url")
    if not api_key:
        api_key = await cfg.get("ocr_api_key")
    if not model:
        model = await cfg.get("ocr_model")
    return base_url, api_key, model


@router.post("/settings/test-ocr-connection")
async def test_ocr_connection(body: Optional[OCRConnectionTest] = None, db: AsyncSession = Depends(get_db)):
    from app.services import ocr_service

    body = body or OCRConnectionTest()
    try:
        base_url, api_key, model = await _ocr_endpoint(
            db, body.model_spec_id, body.base_url, body.api_key, body.model
        )
    except HTTPException as e:
        return {"success": False, "message": str(e.detail)}
    ok, msg, latency = await ocr_service.ocr_service.test_connection(
        base_url=base_url, api_key=api_key, model=model
    )
    return {"success": bool(ok), "message": msg, "latency_ms": latency}


def _render_pdf_page(data: bytes, target_page: int):
    """(jpeg_bytes, page_number, total_pages, error)."""
    from app.services.parsers import pdf_backend

    try:
        doc = pdf_backend.open_document(data)
    except Exception as e:
        return None, 0, 0, f"Không thể render trang PDF: {e}"
    try:
        total = len(doc)
        if total == 0:
            return None, 0, 0, "File PDF không có trang nào"
        page_no = min(max(int(target_page or 1), 1), total)
        try:
            page = doc[page_no - 1]
            try:
                return pdf_backend.render_page_jpeg(page), page_no, total, None
            finally:
                page.close()
        except Exception as e:
            return None, page_no, total, f"Không thể render trang PDF: {e}"
    finally:
        doc.close()


def _word_count(text: str) -> int:
    return len((text or "").split())


@router.post("/settings/test-ocr")
async def test_ocr(
    file: UploadFile = File(...),
    target_page: int = Form(1),
    override_base_url: Optional[str] = Form(None),
    override_api_key: Optional[str] = Form(None),
    override_model: Optional[str] = Form(None),
    override_prompt: Optional[str] = Form(None),
    model_spec_id: Optional[str] = Form(None),
    llm_refine: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    from app.config import settings
    from app.services import ocr_service

    result = {
        "success": False, "text": "", "model": None, "latency_ms": 1, "chars_count": 0, "words_count": 0,
        "page_number": 1, "total_pages": 1, "error": None, "raw_text": None, "ocr_latency_ms": None,
        "refine_model": None, "refine_latency_ms": None, "refine_error": None,
    }
    started = time.perf_counter()
    data = await file.read()
    name = (file.filename or "").lower()
    mime = file.content_type or "application/octet-stream"

    if name.endswith(".pdf") or mime == "application/pdf":
        image, page_no, total, err = _render_pdf_page(data, target_page)
        result["page_number"], result["total_pages"] = page_no, total
        if err:
            result["error"] = err
            return result
        mime = "image/jpeg"
    else:
        image = data
        if not mime.startswith("image/"):
            mime = next((m for ext, m in _IMAGE_EXT_MIME.items() if name.endswith(ext)), "image/png")

    try:
        base_url, api_key, model = await _ocr_endpoint(
            db, model_spec_id, override_base_url, override_api_key, override_model
        )
    except HTTPException as e:
        result["error"] = str(e.detail)
        return result
    model = model or getattr(settings, "ocr_model", None)
    prompt = override_prompt or await _config(db).get("ocr_prompt")
    result["model"] = model

    t0 = time.perf_counter()
    try:
        text = await ocr_service.ocr_service.ocr_image(
            image_bytes=image, mime_type=mime, prompt=prompt, base_url=base_url,
            api_key=api_key, model=model, db=db,
        )
    except Exception as e:
        logger.warning("test-ocr failed: %s", e)
        text = None
    result["ocr_latency_ms"] = max(1, int((time.perf_counter() - t0) * 1000))
    if not text:
        result["error"] = "OCR không trả về nội dung hoặc OCR endpoint chưa được cấu hình."
        result["latency_ms"] = max(1, int((time.perf_counter() - started) * 1000))
        return result

    final = text
    if llm_refine:
        vision = None
        try:
            vision = await _registry(db).get_vision()
        except Exception as e:
            logger.info("vision provider unavailable for refine: %s", e)
        if vision is None:
            result["refine_error"] = "Chưa cấu hình Vision Model để hiệu đính."
        else:
            cfg = getattr(vision, "config", None)
            result["refine_model"] = getattr(cfg, "model", None) or getattr(vision, "model", None)
            t1 = time.perf_counter()
            refined = await ocr_service.refine_ocr_with_llm(vision, image, mime, text)
            result["refine_latency_ms"] = max(1, int((time.perf_counter() - t1) * 1000))
            if refined and refined.strip():
                result["raw_text"] = text
                final = refined
            else:
                result["refine_error"] = "LLM không trả về kết quả hợp lệ — giữ bản OCR."

    result.update(
        success=True, text=final, chars_count=len(final), words_count=_word_count(final),
        latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
    )
    return result


# ---------------------------------------------------------------- extraction preview


def _preview_images(text: str, blobs: dict, budget: list) -> str:
    """Replace ``<!--img:rId-->`` placeholders with inline data-URI images.

    ``budget`` is a one-element list holding the bytes still allowed (mutated).
    Unknown ids and tiny images are dropped; images past the budget, or blobs
    that are not images, become a short note.
    """

    def _sub(m: re.Match) -> str:
        entry = blobs.get(m.group(1).strip())
        if not entry:
            return ""
        content_type, blob = entry
        size = len(blob or b"")
        if size < PREVIEW_MIN_IMAGE_BYTES:
            return ""
        if not (content_type or "").startswith("image/") or size > budget[0]:
            return OVER_BUDGET_NOTE
        budget[0] -= size
        return f"![](data:{content_type};base64,{base64.b64encode(blob).decode('ascii')})"

    return _IMG_RE.sub(_sub, text or "")


def _flag(value: Optional[str], cfg_value: Optional[str]) -> bool:
    if value is not None and str(value).strip() != "":
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return (cfg_value or "").strip().lower() != "false"


@router.post("/settings/test-extraction")
async def test_extraction(
    file: UploadFile = File(...),
    max_pages: int = Form(3),
    engine: Optional[str] = Form(None),
    pdf_parser_engine: Optional[str] = Form(None),
    excel_parser_engine: Optional[str] = Form(None),
    ocr_mode: Optional[str] = Form(None),
    strip_headers_footers: Optional[str] = Form(None),
    enhance_headings: Optional[str] = Form(None),
    override_ocr_base_url: Optional[str] = Form(None),
    override_ocr_api_key: Optional[str] = Form(None),
    override_ocr_model: Optional[str] = Form(None),
    ocr_llm_refine: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    file_name = file.filename or "file"
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    out = {
        "success": False, "file_name": file_name, "file_type": ext,
        "stats": {"total_pages": 0, "preview_pages_count": 0, "ocr_pages_count": 0,
                  "total_words": 0, "total_chars": 0, "latency_ms": 0},
        "pages": [], "error": None,
    }
    try:
        data = await file.read()
        cfg = _config(db)
        if ext == "pdf":
            from app.services.parsers.pdf_parser import PDFParser

            pdf_engine = engine or pdf_parser_engine or await cfg.get("pdf_parser_engine") or "pdfplumber"
            if ocr_llm_refine is not None and str(ocr_llm_refine).strip() != "":
                refine = str(ocr_llm_refine).strip().lower() in ("true", "1", "yes", "on")
            else:
                refine = (await cfg.get("ocr_llm_refine") or "").strip().lower() == "true"
            pages = await PDFParser().parse(
                data, file_name,
                engine=pdf_engine,
                ocr_mode=ocr_mode or "auto",
                strip_headers_footers=_flag(strip_headers_footers, await cfg.get("strip_headers_footers")),
                enhance_headings=_flag(enhance_headings, await cfg.get("enhance_headings")),
                max_pages=max_pages if max_pages and max_pages > 0 else None,
                ocr_base_url=override_ocr_base_url or None,
                ocr_api_key=override_ocr_api_key or None,
                ocr_model=override_ocr_model or None,
                ocr_fallback_vision=False,
                ocr_llm_refine=refine,
                db=db,
            )
        elif ext in ("xlsx", "xls"):
            from app.services.parsers.excel_parser import ExcelParser

            xl_engine = engine or excel_parser_engine or await cfg.get("excel_parser_engine") or "openpyxl"
            pages = await ExcelParser().parse(data, file_name, engine=xl_engine)
        else:
            from app.services import kb_service

            pages = await kb_service._extract_text_from_file(data, file_name, None, None)
            if ext == "docx":
                from app.services.image_service import docx_image_blobs

                try:
                    blobs = docx_image_blobs(data)
                except Exception as e:
                    logger.info("docx image preview skipped: %s", e)
                    blobs = {}
                budget = [PREVIEW_IMAGE_BUDGET]
                for p in pages:
                    p["content"] = _preview_images(p.get("content") or "", blobs, budget)

        pages = list(pages or [])
        total = len(pages)
        preview = pages[:max_pages] if max_pages and max_pages > 0 else pages
        out_pages = []
        for i, p in enumerate(preview, start=1):
            content = p.get("content") or ""
            out_pages.append({
                "page_number": p.get("page_number") or i,
                "content": content,
                "is_ocr": bool(p.get("is_ocr")),
                "char_count": len(content),
                "word_count": _word_count(content),
            })
        out["pages"] = out_pages
        out["stats"].update(
            total_pages=total,
            preview_pages_count=len(out_pages),
            ocr_pages_count=sum(1 for p in pages if p.get("is_ocr")),
            total_words=sum(_word_count(p.get("content") or "") for p in pages),
            total_chars=sum(len(p.get("content") or "") for p in pages),
        )
        out["success"] = True
    except Exception as e:
        logger.warning("test-extraction failed for %s: %s", file_name, e)
        out["error"] = str(e)
    out["stats"]["latency_ms"] = max(1, int((time.perf_counter() - started) * 1000))
    return out
