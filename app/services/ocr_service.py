"""
Dedicated OCR service using OpenAI-compatible vision/OCR endpoint (e.g. GLM-OCR).
Supports dynamic configuration from Database with fallback to environment variables.
"""

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from app.config import settings


def normalize_ocr_base_url(url: str) -> str:
    """Normalize base URL to ensure proper protocol and /v1 suffix."""
    url = (url or "").strip()
    if not url:
        return ""
    url = url.rstrip("/")
    if "://" in url:
        proto, path = url.split("://", 1)
        while "//" in path:
            path = path.replace("//", "/")
        url = f"{proto}://{path}"
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class OCRService:
    """Service for running dedicated OCR on document page images."""

    def __init__(self):
        self._cached_client = None
        self._cached_key: Optional[str] = None
        self._cached_url: Optional[str] = None

    def is_configured(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> bool:
        """Check if OCR base URL and API key are configured."""
        effective_url = base_url or settings.effective_ocr_base_url
        effective_key = api_key or settings.ocr_api_key
        return bool(effective_url and effective_key)

    def _get_client(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        from openai import OpenAI

        url = normalize_ocr_base_url(base_url) if base_url else settings.effective_ocr_base_url
        key = api_key or settings.ocr_api_key

        if not url or not key:
            raise ValueError("OCR Base URL and API Key must be provided.")

        # Cache default client if using settings
        if not base_url and not api_key:
            if (
                self._cached_client is not None
                and self._cached_url == url
                and self._cached_key == key
            ):
                return self._cached_client
            self._cached_client = OpenAI(
                base_url=url,
                api_key=key,
                default_headers={"User-Agent": "curl/8.5.0"},
                timeout=120.0,
            )
            self._cached_url = url
            self._cached_key = key
            return self._cached_client

        return OpenAI(
            base_url=url,
            api_key=key,
            default_headers={"User-Agent": "curl/8.5.0"},
            timeout=120.0,
        )

    def _call_ocr_stream_sync(
        self,
        b64_image: str,
        mime_type: str,
        prompt: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Synchronous helper executed in thread pool for streaming completion."""
        client = self._get_client(base_url=base_url, api_key=api_key)
        target_model = model or settings.ocr_model
        data_url = f"data:{mime_type};base64,{b64_image}"

        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            stream=True,
        )

        chunks: list[str] = []
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)

        return "".join(chunks).strip()

    async def test_connection(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[bool, str, int]:
        """
        Test connection to the OCR endpoint.
        Returns: (success: bool, message: str, latency_ms: int)
        """
        start_time = datetime.now(timezone.utc)
        try:
            client = self._get_client(base_url=base_url, api_key=api_key)
            target_model = model or settings.ocr_model

            # Try listing models or pinging endpoint
            def _check():
                try:
                    client.models.list()
                    return True, "Kết nối thành công tới endpoint OCR."
                except Exception as list_err:
                    logger.debug(f"models.list() failed ({list_err}), trying completion probe...")
                    try:
                        client.chat.completions.create(
                            model=target_model,
                            messages=[{"role": "user", "content": "ping"}],
                            max_tokens=1,
                            stream=False,
                        )
                        return True, f"Kết nối thành công tới OCR model '{target_model}'."
                    except Exception as comp_err:
                        raise comp_err

            success, msg = await asyncio.to_thread(_check)
            latency_ms = max(1, int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000))
            return success, msg, latency_ms

        except Exception as e:
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.warning(f"OCR test_connection failed: {e}")
            return False, f"Không thể kết nối tới OCR service: {str(e)}", latency_ms

    async def ocr_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        prompt: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Run OCR on image bytes using the configured OpenAI-compatible OCR model.
        Returns extracted text, or None if not configured or on failure.
        """
        effective_base_url = base_url
        effective_api_key = api_key
        effective_model = model
        effective_prompt = prompt

        if db is not None:
            try:
                from app.services.config_service import ConfigService

                cfg = ConfigService(db)
                if not effective_base_url:
                    effective_base_url = await cfg.get("ocr_base_url")
                if not effective_api_key:
                    effective_api_key = await cfg.get("ocr_api_key")
                if not effective_model:
                    effective_model = await cfg.get("ocr_model")
                if not effective_prompt:
                    effective_prompt = await cfg.get("ocr_prompt")
            except Exception as e:
                logger.warning(f"Error fetching dynamic OCR config from DB: {e}")

        effective_base_url = effective_base_url or settings.effective_ocr_base_url
        effective_api_key = effective_api_key or settings.ocr_api_key
        effective_model = effective_model or settings.ocr_model

        if not self.is_configured(base_url=effective_base_url, api_key=effective_api_key):
            return None

        ocr_prompt = effective_prompt or (
            "Trích xuất TOÀN BỘ văn bản từ hình ảnh trang tài liệu này một cách chính xác tuyệt đối.\n"
            "Yêu cầu nghiêm ngặt:\n"
            "1. Giữ nguyên số hiệu văn bản, tiêu đề, dấu câu, ngày tháng, các cụm từ viết tắt ngành (CAND, CSGT, PCCC, ANTT, QĐ, NĐ, TT...).\n"
            "2. Tái tạo chính xác cấu trúc bảng biểu dạng Markdown Table (| Cột 1 | Cột 2 |).\n"
            "3. Tái tạo cấu trúc thứ bậc đề mục: Phần, Chương, Mục, Điều, Khoản, Điểm.\n"
            "4. Tuyệt đối không thêm lời bình, không tóm tắt hay tự ý suy diễn từ ngữ."
        )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        start_time = datetime.now(timezone.utc)

        try:
            out_text = await asyncio.to_thread(
                self._call_ocr_stream_sync,
                b64_image,
                mime_type,
                ocr_prompt,
                effective_base_url,
                effective_api_key,
                effective_model,
            )

            try:
                from app.ai.tracing import record_generation

                record_generation(
                    name="dedicated_ocr.stream",
                    model=effective_model,
                    input_data={
                        "prompt": ocr_prompt,
                        "mime_type": mime_type,
                        "image_size_bytes": len(image_bytes),
                    },
                    output_data=out_text,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                )
            except Exception:
                pass

            if out_text and out_text.strip():
                return out_text.strip()
            return None

        except Exception as e:
            logger.warning(f"Dedicated OCR failed: {e}")
            try:
                from app.ai.tracing import record_generation

                record_generation(
                    name="dedicated_ocr.stream",
                    model=effective_model,
                    input_data={
                        "prompt": ocr_prompt,
                        "mime_type": mime_type,
                        "image_size_bytes": len(image_bytes),
                    },
                    output_data=None,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    level="ERROR",
                    status_message=str(e),
                )
            except Exception:
                pass
            return None


ocr_service = OCRService()


OCR_REFINE_PROMPT = (
    "Bạn là chuyên gia hiệu đính văn bản hành chính, pháp luật tiếng Việt.\n"
    "Dưới đây là bản OCR của trang tài liệu trong ảnh đính kèm. Đối chiếu từng dòng với ảnh và sửa:\n"
    "- Lỗi nhận dạng ký tự, dấu tiếng Việt, chữ bị dính hoặc tách sai.\n"
    "- Số hiệu văn bản, ngày tháng, con số, tên riêng, từ viết tắt ngành (CAND, CSGT, PCCC, ANTT, QĐ, NĐ, TT...).\n"
    "- Cấu trúc bảng (Markdown Table) và đề mục (Phần, Chương, Mục, Điều, Khoản, Điểm).\n"
    "- Bổ sung phần chữ có trong ảnh nhưng bản OCR bỏ sót.\n"
    "Quy tắc: chỉ trả về TOÀN BỘ văn bản đã hiệu đính dạng Markdown, không lời bình, không tóm tắt, "
    "không bọc trong ```; giữ nguyên nội dung đúng, không tự suy diễn.\n\n"
    "=== BẢN OCR ===\n{draft}\n=== HẾT BẢN OCR ==="
)

# A refined page much shorter than the OCR draft is most likely truncated.
_MIN_REFINE_RATIO = 0.5


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


async def refine_ocr_with_llm(
    vision_provider: Any,
    image_bytes: bytes,
    mime_type: str,
    draft: str,
) -> Optional[str]:
    """Have the Vision LLM proofread an OCR draft against the page image.

    Returns the corrected text, or None (keep the draft) on failure or when
    the answer looks truncated.
    """
    if vision_provider is None or not draft.strip():
        return None
    try:
        out = await vision_provider.analyze_image(
            image_bytes,
            mime_type=mime_type,
            prompt=OCR_REFINE_PROMPT.format(draft=draft.strip()),
        )
    except Exception as e:
        logger.warning(f"OCR LLM refine failed: {e}")
        return None
    refined = _strip_fences(out or "")
    if len(refined) < len(draft.strip()) * _MIN_REFINE_RATIO:
        logger.warning("OCR LLM refine output looks truncated; keeping OCR draft")
        return None
    return refined
