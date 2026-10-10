"""OCR + LLM mode: the Vision model proofreads the OCR draft."""

import pytest

from app.services.ocr_service import refine_ocr_with_llm

DRAFT = "Điều 1. Pham vi điều chinh\nNghi đinh này quy đinh về cư trú."


class FakeVision:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.prompt = None

    async def analyze_image(self, image_data, mime_type="image/jpeg", prompt=None):
        self.prompt = prompt
        if self.error:
            raise self.error
        return self.answer


@pytest.mark.asyncio
async def test_refine_returns_corrected_text_and_sends_draft():
    fixed = "Điều 1. Phạm vi điều chỉnh\nNghị định này quy định về cư trú."
    vision = FakeVision("```markdown\n" + fixed + "\n```")
    assert await refine_ocr_with_llm(vision, b"img", "image/jpeg", DRAFT) == fixed
    assert DRAFT in vision.prompt


@pytest.mark.asyncio
async def test_refine_keeps_draft_on_truncated_or_failed_answer():
    assert await refine_ocr_with_llm(FakeVision("Điều 1."), b"img", "image/jpeg", DRAFT) is None
    assert await refine_ocr_with_llm(FakeVision(error=RuntimeError("429")), b"img", "image/jpeg", DRAFT) is None
    assert await refine_ocr_with_llm(None, b"img", "image/jpeg", DRAFT) is None
    assert await refine_ocr_with_llm(FakeVision("x"), b"img", "image/jpeg", "  ") is None
