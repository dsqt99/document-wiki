import unicodedata
import pytest

from app.core.text_normalizer import normalize_text


def test_normalize_unicode_nfd_to_nfc():
    # NFD: 'e' + combining circumflex + combining acute
    nfd_text = unicodedata.normalize("NFD", "Nghị định quy định chi tiết thi hành Luật Phòng cháy và chữa cháy")
    # Verify it was indeed NFD
    assert unicodedata.is_normalized("NFD", nfd_text)

    normalized = normalize_text(nfd_text)
    assert unicodedata.is_normalized("NFC", normalized)
    assert normalized == "Nghị định quy định chi tiết thi hành Luật Phòng cháy và chữa cháy"


def test_normalize_whitespace_and_nbsp():
    raw = "Điều  1.\u00a0\u00a0Phạm   vi   điều chỉnh  \r\n\r\n  Nội dung.  "
    normalized = normalize_text(raw)
    assert "\u00a0" not in normalized
    assert "\r" not in normalized
    assert "Điều 1. Phạm vi điều chỉnh" in normalized


def test_normalize_control_chars_preserves_newline_tab():
    raw = "Dòng 1\x00\x08\x0b\x0c\nDòng 2\tDòng 3"
    normalized = normalize_text(raw)
    assert "\x00" not in normalized
    assert "\x08" not in normalized
    assert "Dòng 1\nDòng 2\tDòng 3" == normalized
