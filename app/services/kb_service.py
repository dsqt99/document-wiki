"""Text extraction for uploaded files and URLs, plus inline image markers."""

from __future__ import annotations

import io
import os
import re
import tempfile
from collections import defaultdict
from typing import Any, Optional

from loguru import logger

_TRUE_STRINGS = {"1", "true", "yes", "on"}
_DOC_CONFIG_EXTS = {"pdf", "xlsx", "xls", "doc", "ppt", "rtf"}
_LIBREOFFICE_EXTS = {"doc", "ppt", "rtf"}

# (parser kwarg, doc-processing config key)
_PDF_KWARG_KEYS = (
    ("engine", "pdf_engine"),
    ("ocr_mode", "ocr_mode"),
    ("ocr_fallback_vision", "ocr_fallback_vision"),
    ("ocr_llm_refine", "ocr_llm_refine"),
    ("strip_headers_footers", "strip_headers_footers"),
    ("enhance_headings", "enhance_headings"),
    ("ocr_base_url", "ocr_base_url"),
    ("ocr_api_key", "ocr_api_key"),
    ("ocr_model", "ocr_model"),
    ("ocr_prompt", "ocr_prompt"),
    ("ocr_model_prompt", "ocr_model_prompt"),
)

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in _TRUE_STRINGS


def _as_str(value: Optional[str], default: Optional[str] = None) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _ext_of(file_name: str) -> str:
    name = file_name or ""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _guess_content_type(file_name: str) -> str:
    return _CONTENT_TYPES.get(_ext_of(file_name), "application/octet-stream")


async def _load_doc_processing_config() -> dict:
    try:
        import app.database as _db
        from app.services.config_service import ConfigService
        from app.services.ocr_service import (
            OCR_MODEL_SPEC_KEY,
            OCR_PROMPT_MODE_KEY,
            resolve_ocr_prompt,
        )

        async with _db.async_session_factory() as session:
            svc = ConfigService(session)

            async def get(key: str) -> Optional[str]:
                return await svc.get(key)

            return {
                "pdf_engine": _as_str(await get("pdf_parser_engine"), "pdfplumber"),
                "excel_engine": _as_str(await get("excel_parser_engine"), "openpyxl"),
                "ocr_mode": _as_str(await get("ocr_mode"), "auto"),
                "ocr_fallback_vision": _as_bool(await get("ocr_fallback_vision"), True),
                "ocr_llm_refine": _as_bool(await get("ocr_llm_refine"), False),
                "strip_headers_footers": _as_bool(await get("pdf_strip_headers_footers"), True),
                "enhance_headings": _as_bool(await get("pdf_enhance_headings"), True),
                "ocr_base_url": _as_str(await get("ocr_base_url")),
                "ocr_api_key": _as_str(await get("ocr_api_key")),
                "ocr_model": _as_str(await get("ocr_model")),
                "ocr_prompt": _as_str(await get("ocr_prompt")),
                "ocr_model_prompt": resolve_ocr_prompt(
                    await get(OCR_MODEL_SPEC_KEY),
                    await get(OCR_PROMPT_MODE_KEY),
                    await get("ocr_prompt"),
                ),
            }
    except Exception as e:  # noqa: BLE001 - config is optional at extraction time
        logger.warning(f"Could not load document processing config, using parser defaults: {e}")
        return {}


def _pdf_kwargs(cfg: dict) -> dict:
    out: dict[str, Any] = {}
    for kwarg, key in _PDF_KWARG_KEYS:
        if key in cfg and cfg[key] is not None:
            out[kwarg] = cfg[key]
    return out


async def _content_core_extract(source: dict) -> str:
    import content_core as cc  # optional dependency

    result = await cc.extract({**source, "output_format": "markdown"})
    if isinstance(result, dict):
        return str(result.get("content") or "")
    return str(getattr(result, "content", "") or "")


async def _extract_with_content_core(file_data: bytes, ext: str) -> list[dict]:
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}" if ext else "")
        with os.fdopen(fd, "wb") as fh:
            fh.write(file_data)
        content = await _content_core_extract({"file_path": tmp_path})
        return [{"content": content, "page_number": 1}]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"content-core extraction failed for .{ext}: {e}")
        return [{"content": "", "page_number": 1}]
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def _extract_text_from_file(
    file_data: bytes,
    file_name: str,
    vision_provider: Any = None,
    tracker: Any = None,
) -> list[dict]:
    import sys

    ext = _ext_of(file_name)
    cfg: dict = {}
    if ext in _DOC_CONFIG_EXTS:
        cfg = await sys.modules[__name__]._load_doc_processing_config() or {}
    pdf_kw = _pdf_kwargs(cfg)

    if ext == "pdf":
        from app.services.parsers import pdf_parser

        return await pdf_parser.PDFParser().parse(
            file_data=file_data,
            file_name=file_name,
            vision_provider=vision_provider,
            tracker=tracker,
            **pdf_kw,
        )

    if ext in ("xlsx", "xls"):
        from app.services.parsers.excel_parser import ExcelParser

        return await ExcelParser().parse(
            file_data=file_data,
            file_name=file_name,
            vision_provider=vision_provider,
            tracker=tracker,
            engine=cfg.get("excel_engine") or "openpyxl",
        )

    if ext == "csv":
        try:
            import pandas as pd

            df = pd.read_csv(io.BytesIO(file_data))
            return [{"content": df.to_markdown(index=False), "page_number": 1}]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"CSV parse failed for '{file_name}', falling back to content-core: {e}")
            return await _extract_with_content_core(file_data, ext)

    if ext == "docx":
        from app.services.parsers.docx_parser import DocxParser

        return await DocxParser().parse(
            file_data=file_data, file_name=file_name, vision_provider=vision_provider, tracker=tracker
        )

    if ext == "pptx":
        from app.services.parsers.pptx_parser import PPTXParser

        return await PPTXParser().parse(
            file_data=file_data, file_name=file_name, vision_provider=vision_provider, tracker=tracker
        )

    if ext in ("txt", "md"):
        return [{"content": file_data.decode("utf-8", errors="ignore"), "page_number": 1}]

    if ext in _LIBREOFFICE_EXTS:
        from app.services.parsers import libreoffice_converter as lo_mod
        from app.services.parsers import pdf_parser

        converter = lo_mod.libreoffice_converter
        if not converter.is_available():
            raise ValueError(
                f"Định dạng file .{ext} yêu cầu LibreOffice để chuyển đổi tự động nhưng hệ thống chưa cài đặt. "
                "Vui lòng chuyển đổi sang .docx hoặc .pdf trước khi tải lên."
            )
        try:
            pdf = await converter.convert_to_pdf(file_data, ext)
            return await pdf_parser.PDFParser().parse(
                file_data=pdf,
                file_name=f"{file_name}.pdf",
                vision_provider=vision_provider,
                tracker=tracker,
                **pdf_kw,
            )
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Không thể chuyển đổi file .{ext} sang PDF: {e}") from e

    return await _extract_with_content_core(file_data, ext)


async def _extract_text_from_url(url: str) -> list[dict]:
    try:
        content = await _content_core_extract({"url": url})
        return [{"content": content, "page_number": 1}]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"content-core URL extraction failed for {url}, falling back to plain GET: {e}")
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url)
        return [{"content": resp.text, "page_number": 1}]


# ---------------------------------------------------------------------------
# Inline image markers
# ---------------------------------------------------------------------------


def _marker(image: Any) -> str:
    caption = getattr(image, "caption", None) or ""
    alt = caption.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    alt = alt.replace("[", "(").replace("]", ")").strip()
    return f"![{alt}](image://{image.image_id})"


def _page_index(pages_data: list[dict], page_number: int) -> Optional[int]:
    for i, page in enumerate(pages_data):
        if page.get("page_number") == page_number:
            return i
    if 1 <= page_number <= len(pages_data):
        return page_number - 1
    return None


def _inline_image_markers(pages_data: list[dict], images: Optional[list]) -> None:
    from app.services.parsers.base import IMAGE_PLACEHOLDER_RE

    by_ref: dict[str, Any] = {}
    by_page: dict[int, list] = defaultdict(list)
    for image in images or []:
        if not getattr(image, "image_id", None):
            continue
        ref = getattr(image, "ref", None)
        if ref:
            by_ref.setdefault(ref, image)
        else:
            by_page[getattr(image, "page_number", None) or 1].append(image)

    placed: set[str] = set()
    for page in pages_data:
        content = page.get("content") or ""
        if "<!--img:" not in content:
            continue

        def _swap(m: re.Match) -> str:
            ref = m.group(1)
            image = by_ref.get(ref)
            if image is None or ref in placed:
                return ""
            placed.add(ref)
            return f"\n\n{_marker(image)}\n\n"

        content = IMAGE_PLACEHOLDER_RE.sub(_swap, content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        page["content"] = content

    leftovers = [img for ref, img in by_ref.items() if ref not in placed]
    if leftovers and pages_data:
        idx = _page_index(pages_data, 1)
        if idx is not None:
            block = "\n\n".join(_marker(img) for img in leftovers)
            pages_data[idx]["content"] = (pages_data[idx].get("content") or "") + f"\n\n{block}\n"

    for page_number, imgs in by_page.items():
        if not imgs:
            continue
        idx = _page_index(pages_data, page_number)
        if idx is None:
            continue
        block = "\n\n".join(_marker(img) for img in imgs)
        pages_data[idx]["content"] = (pages_data[idx].get("content") or "") + f"\n\n{block}\n"
