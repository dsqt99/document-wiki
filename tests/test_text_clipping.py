"""Summaries, article titles and relation quotes are shortened at word/sentence boundaries."""

from app.database.models import LegalRelationType
from app.services.legal_relation_extractor import LegalRelationExtractor
from app.services.legal_service import article_summary, is_body_sentence, split_legal_text_by_articles
from app.utils.text import ELLIPSIS, clip_around, clip_text


def test_clip_text_short_text_unchanged():
    assert clip_text("  Phạm vi   điều chỉnh  ", 50) == "Phạm vi điều chỉnh"
    assert clip_text("", 10) == ""
    assert clip_text(None, 10) == ""


def test_clip_text_never_cuts_a_word():
    text = "Quyết định này quy định về chế độ báo cáo thống kê của ngành Công an nhân dân"
    out = clip_text(text, 40)
    assert out.endswith(ELLIPSIS)
    assert len(out) <= 40
    assert text.startswith(out[:-1])
    assert out[:-1].split()[-1] in text.split()


def test_clip_text_prefers_sentence_end():
    text = "Câu thứ nhất khá dài để vượt ngưỡng sáu mươi phần trăm cửa sổ. Câu thứ hai bị bỏ đi phần lớn"
    out = clip_text(text, 80)
    assert out == "Câu thứ nhất khá dài để vượt ngưỡng sáu mươi phần trăm cửa sổ. " + ELLIPSIS


def test_clip_around_keeps_match_and_marks_cuts():
    line = "a " * 300 + "sửa đổi Điều 5 Thông tư số 12/2020/TT-BCA" + " b" * 300
    start = line.index("sửa đổi")
    end = start + len("sửa đổi Điều 5")
    out = clip_around(line, start, end)
    assert "sửa đổi Điều 5 Thông tư số 12/2020/TT-BCA" in out
    assert out.startswith(ELLIPSIS) and out.endswith(ELLIPSIS)
    assert clip_around("ngắn gọn", 0, 3) == "ngắn gọn"


def test_is_body_sentence():
    assert not is_body_sentence("Phạm vi điều chỉnh")
    assert not is_body_sentence("Sửa đổi, bổ sung một số điều của Luật Công an nhân dân")
    assert not is_body_sentence(None)
    assert not is_body_sentence("7 . Đấu giá biển số xe")
    assert not is_body_sentence(
        "Yêu cầu về phòng cháy và chữa cháy khi lập quy hoạch xây dựng hoặc điều chỉnh quy hoạch xây dựng "
        "đô thị, khu kinh tế, khu công nghiệp, cụm công nghiệp, khu chế xuất, khu công nghệ cao và các khu "
        "chức năng khác theo Luật Quy hoạch"
    )
    assert is_body_sentence(
        "Quyết định này có hiệu lực thi hành kể từ ngày ký. Quyết định này bãi bỏ và thay thế:"
    )
    assert is_body_sentence("Quyết định này có hiệu lực thi hành kể từ ngày ký và thay thế các văn bản sau:")


def test_article_summary_uses_body_without_stray_bullets():
    content = (
        "> **Căn cứ pháp lý**: Điều 2 — Quyết định 1\n\n"
        "### Điều 2. Quyết định này có hiệu lực thi hành kể từ ngày ký. Quyết định này bãi bỏ và thay thế:\n"
        "- Quyết định số 97/QĐ-BCA ngày 01/01/2020;\n"
        "- Quyết định số 98/QĐ-BCA ngày 02/01/2020.\n"
    )
    lead = "Quyết định này có hiệu lực thi hành kể từ ngày ký. Quyết định này bãi bỏ và thay thế:"
    out = article_summary("2", None, lead, content)
    assert out.startswith("Điều 2 — Quyết định này có hiệu lực")
    assert "— -" not in out and "Căn cứ pháp lý" not in out
    assert "Quyết định số 98/QĐ-BCA" in out
    assert len(out) <= 400

    long_body = "1. " + "Nội dung khoản dài " * 60
    out = article_summary("3", "Hiệu lực thi hành", None, long_body)
    assert out.startswith("Điều 3: Hiệu lực thi hành — 1. Nội dung khoản dài")
    assert len(out) <= 400 and out.endswith(ELLIPSIS)


def test_splitter_moves_body_sentence_out_of_title_and_keeps_slug():
    text = (
        "QUYẾT ĐỊNH\n"
        "Điều 1. Phạm vi điều chỉnh\nQuyết định này quy định việc A.\n"
        "Điều 2. Quyết định này có hiệu lực thi hành kể từ ngày ký. Quyết định này bãi bỏ và thay thế:\n"
        "- Quyết định số 97/QĐ-BCA.\n"
    )
    arts = split_legal_text_by_articles(text, "Quyết định 1", doc_slug="doc-abc")["articles"]
    assert [a["slug"] for a in arts] == ["dieu-1-doc-abc", "dieu-2-doc-abc"]
    assert arts[0]["title"] == "Phạm vi điều chỉnh" and arts[0]["lead"] is None
    assert arts[1]["title"] is None
    assert arts[1]["lead"].startswith("Quyết định này có hiệu lực")


def test_quote_context_reaches_target_doc_past_250_chars():
    filler = "nội dung mở đầu rất dài " * 15
    line = filler + "Quyết định này thay thế Quyết định số 3453/QĐ-BCA ngày 01/01/2020 của Bộ trưởng."
    assert line.index("3453/QĐ-BCA") > 250
    rels = LegalRelationExtractor().extract_from_text(line, default_doc_number="1/QĐ-BCA")
    replace = [r for r in rels if r.relation_type == LegalRelationType.THAY_THE]
    assert replace and "3453/QĐ-BCA" in replace[0].quote_context
    assert replace[0].quote_context.startswith(ELLIPSIS)


def test_glued_heading_split_is_fast_on_form_blanks():
    import time

    from app.services.legal_hierarchy_parser import _split_glued_headings

    text = ("Họ tên: " + "_" * 40 + " Ngày sinh: " + "_" * 30 + "\n") * 200 + "x **Điều 2. Hiệu lực**"
    t = time.time()
    out = _split_glued_headings(text)
    assert time.time() - t < 1
    assert out.endswith("x\n**Điều 2. Hiệu lực**")
