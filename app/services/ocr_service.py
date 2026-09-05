"""
Dedicated OCR service using OpenAI-compatible vision/OCR endpoint (e.g. GLM-OCR).
"""

import asyncio
import base64
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.config import settings


class OCRService:
    """Service for running dedicated OCR on document page images."""

    def __init__(self):
        self._client = None

    @property
    def is_configured(self) -> bool:
        """Check if dedicated OCR base URL and API key are configured."""
        return bool(settings.effective_ocr_base_url and settings.ocr_api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=settings.effective_ocr_base_url,
                api_key=settings.ocr_api_key,
                default_headers={"User-Agent": "curl/8.5.0"},
                timeout=120.0,
            )
        return self._client

    def _call_ocr_stream_sync(
        self,
        b64_image: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        """Synchronous helper executed in thread pool for streaming completion."""
        client = self._get_client()
        data_url = f"data:{mime_type};base64,{b64_image}"

        response = client.chat.completions.create(
            model=settings.ocr_model,
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

    async def ocr_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        prompt: Optional[str] = None,
    ) -> Optional[str]:
        """
        Run OCR on image bytes using the configured OpenAI-compatible OCR model.
        Returns extracted text, or None if not configured or on failure.
        """
        if not self.is_configured:
            return None

        ocr_prompt = prompt or (
            "Extract ALL text from this document page exactly as written. "
            "Preserve the original layout, headings, tables, and formatting "
            "as closely as possible using markdown. If the page contains a "
            "table, reproduce it as a markdown table. If there is no text "
            "at all, respond with an empty string."
        )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        start_time = datetime.now(timezone.utc)

        try:
            out_text = await asyncio.to_thread(
                self._call_ocr_stream_sync,
                b64_image,
                mime_type,
                ocr_prompt,
            )

            try:
                from app.ai.tracing import record_generation

                record_generation(
                    name="dedicated_ocr.stream",
                    model=settings.ocr_model,
                    input_data={"prompt": ocr_prompt, "mime_type": mime_type, "image_size_bytes": len(image_bytes)},
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
                    model=settings.ocr_model,
                    input_data={"prompt": ocr_prompt, "mime_type": mime_type, "image_size_bytes": len(image_bytes)},
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
