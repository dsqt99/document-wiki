"""OCR output validation: reject empty / no-text / looping / truncated output."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.ocr_service import OCRService, refine_ocr_with_llm, validate_ocr_text

VN_PAGE = (
    "BỘ CÔNG AN\nCÔNG AN TỈNH HƯNG YÊN\n\n"
    "Số: 123/QĐ-CAT-PV01\n\n"
    "QUYẾT ĐỊNH\nVề việc ban hành quy chế làm việc\n\n"
    "Điều 1. Phạm vi điều chỉnh\n"
    "Nghị định này quy định về cư trú, đăng ký thường trú, tạm trú.\n\n"
    "| STT | Họ và tên | Chức vụ |\n| --- | --- | --- |\n| 1 | Nguyễn Văn A | Trưởng phòng |\n"
)


# --- validate_ocr_text ------------------------------------------------------


def test_normal_vietnamese_text_accepted():
    text, reason = validate_ocr_text(VN_PAGE)
    assert reason is None
    assert text == VN_PAGE.strip()


@pytest.mark.parametrize("short", ["A", "3", "±", "Điều 1.", "Chương I\n" * 5])
def test_short_real_content_accepted(short):
    text, reason = validate_ocr_text(short)
    assert reason is None
    assert text == short.strip()


@pytest.mark.parametrize(
    "reply",
    [
        "No text content.",
        "no text",
        "```\nNo text content.\n```",
        "<p>No text content.</p>",
        "**Không có văn bản.**",
        "Không có nội dung",
        "không tìm thấy văn bản",
    ],
)
def test_no_text_replies_rejected(reply):
    assert validate_ocr_text(reply) == ("", "no_text")


def test_sentence_mentioning_no_text_phrase_is_kept():
    s = "Trường hợp không có văn bản đề nghị thì cơ quan đăng ký cư trú từ chối."
    assert validate_ocr_text(s) == (s, None)


@pytest.mark.parametrize("blank", ["", "   \n\t ", None])
def test_empty_rejected(blank):
    assert validate_ocr_text(blank) == ("", "empty_content")


def test_no_readable_content_rejected():
    assert validate_ocr_text("| --- | --- |\n| | |")[1] == "no_readable_content"


@pytest.mark.parametrize(
    "loop",
    [
        "Điều 1. " * 200,
        "Cộng hòa xã hội\nchủ nghĩa Việt Nam\n" * 100,
        "Điều 1\n" + "|  " * 2500,
        "|  " * 1250 + "Điều 1\n" + "|  " * 1250,  # split loop
        "| " * 600 + "Điều 1\n" + "Hủy bỏ quyết định " * 120,  # different periods
    ],
)
def test_repetition_loop_rejected(loop):
    assert validate_ocr_text(loop) == ("", "repetitive_content")


def test_trailing_loop_trimmed_when_page_has_real_content():
    body = VN_PAGE * 6  # ~1.7k chars of real text
    text, reason = validate_ocr_text(body + "Điều 2. " * 80)
    assert reason is None
    assert text.startswith(body.strip())
    assert text.count("Điều 2.") == 1


def test_short_legitimate_repetition_kept():
    # Dot leaders / table separators shorter than 512 chars are not loops.
    toc = "Chương I " + "." * 200 + " 5\nChương II " + "." * 200 + " 9"
    assert validate_ocr_text(toc) == (toc, None)


def test_truncated_flagged():
    text, reason = validate_ocr_text(VN_PAGE, truncated=True)
    assert reason == "truncated"
    assert text == VN_PAGE.strip()


# --- dedicated OCR call ------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_image_rejects_loop_and_truncation():
    svc = OCRService()
    kw = dict(image_bytes=b"img", base_url="https://ocr/v1", api_key="k", model="m")

    with patch.object(svc, "_call_ocr_sync", return_value=("Điều 1. " * 200, "stop")):
        assert await svc.ocr_image(**kw) is None
    with patch.object(svc, "_call_ocr_sync", return_value=(VN_PAGE, "length")):
        assert await svc.ocr_image(**kw) is None
    with patch.object(svc, "_call_ocr_sync", return_value=("No text content.", "stop")):
        assert await svc.ocr_image(**kw) is None
    with patch.object(svc, "_call_ocr_sync", return_value=(VN_PAGE, "stop")):
        assert await svc.ocr_image(**kw) == VN_PAGE.strip()


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
def test_nonstream_reads_message_content_and_finish_reason(finish_reason):
    svc = OCRService()
    def create(**request):
        assert request["stream"] is False
        assert request["model"] == "m"
        assert request["messages"][0]["content"][1]["image_url"]["url"] == "data:image/png;base64,b64"
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="  Điều 1. Phạm vi  "), finish_reason=finish_reason,
        )])
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    with patch.object(svc, "_get_client", return_value=client):
        assert svc._call_ocr_sync("b64", "image/png", "p", "u", "k", "m") == "Điều 1. Phạm vi"
    with patch.object(svc, "_get_client", return_value=client):
        assert svc._call_ocr_sync(
            "b64", "image/png", "p", "u", "k", "m", with_finish_reason=True
        ) == ("Điều 1. Phạm vi", finish_reason)


@pytest.mark.parametrize("choices", [[], [SimpleNamespace(message=SimpleNamespace(content=None), finish_reason="stop")]])
def test_nonstream_empty_response_stays_empty(choices):
    svc = OCRService()
    def create(**request):
        assert request["stream"] is False
        return SimpleNamespace(choices=choices)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(svc, "_get_client", return_value=client):
        assert svc._call_ocr_sync("b64", "image/png", "p", "u", "k", "m") == ""


# --- LLM proofreading --------------------------------------------------------


class FakeVision:
    def __init__(self, answer):
        self.answer = answer

    async def analyze_image(self, image_data, mime_type="image/jpeg", prompt=None):
        return self.answer


@pytest.mark.asyncio
async def test_refine_falls_back_to_draft_when_refined_output_loops():
    draft = "Điều 1. Pham vi điều chinh\nNghi đinh này quy đinh về cư trú."
    looping = "Điều 1. Phạm vi điều chỉnh\n" + "Nghị định này quy định về cư trú. " * 60
    assert len(looping) > len(draft)  # passes the length-ratio check
    assert await refine_ocr_with_llm(FakeVision(looping), b"img", "image/jpeg", draft) is None


@pytest.mark.asyncio
async def test_refine_rejects_no_text_answer():
    draft = "Điều 1. Pham vi"
    assert await refine_ocr_with_llm(FakeVision("No text content."), b"img", "image/jpeg", draft) is None
