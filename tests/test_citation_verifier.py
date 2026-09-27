"""Tests for CitationVerifier and lightweight [^sN] footnote verification."""

import pytest
from app.services.citation_verifier import (
    CitationVerifier,
    CitationVerificationResult,
    PageCitationReport,
    extract_footnotes,
    format_footnote_citations,
    apply_citation_callout,
)


def test_verify_claim_direct_match():
    """Verify that a claim with strong overlap in the source text is verified."""
    source_text = """
    Nghị định 136/2020/NĐ-CP quy định chi tiết một số điều và biện pháp thi hành
    Luật Phòng cháy và chữa cháy. Cơ sở thuộc diện quản lý về phòng cháy và chữa cháy
    phải lập hồ sơ theo dõi, quản lý hoạt động phòng cháy và chữa cháy theo quy định.
    """
    verifier = CitationVerifier()
    claim = "Cơ sở thuộc diện quản lý về phòng cháy và chữa cháy phải lập hồ sơ theo dõi, quản lý hoạt động PCCC."

    res = verifier.verify_claim(claim, source_text)
    assert isinstance(res, CitationVerificationResult)
    assert res.is_verified is True
    assert res.confidence >= 0.7
    assert res.matched_excerpt is not None


def test_verify_claim_hallucination_detected():
    """Verify that a fabricated claim with non-existent articles/numbers is marked unverified."""
    source_text = """
    Nghị định 136/2020/NĐ-CP quy định chi tiết một số điều của Luật Phòng cháy và chữa cháy.
    Thời hạn thẩm duyệt thiết kế về phòng cháy và chữa cháy là 10 ngày làm việc.
    """
    verifier = CitationVerifier()
    # Claim contains completely made up legal citation and facts
    hallucinated_claim = "Theo Điều 99 Nghị định 999/2024/NĐ-CP, mức phạt vi phạm giao thông đường thủy là 50 triệu đồng."

    res = verifier.verify_claim(hallucinated_claim, source_text)
    assert res.is_verified is False
    assert res.confidence < 0.5
    assert "chưa tìm thấy căn cứ" in res.reason.lower() or "không khớp" in res.reason.lower()


def test_extract_and_format_lightweight_footnotes():
    """Verify extraction and formatting of [^sN] footnotes."""
    markdown_text = """
    PCCC là trách nhiệm của toàn dân [^s1]. Người đứng đầu cơ quan tổ chức phải chịu trách nhiệm [^s2].
    
    [^s1]: Luật PCCC 2001, Điều 4.
    [^s2]: Nghị định 136/2020/NĐ-CP, Điều 5.
    """
    footnotes = extract_footnotes(markdown_text)
    assert len(footnotes) == 2
    assert footnotes[0]["id"] == "s1"
    assert footnotes[0]["text"] == "Luật PCCC 2001, Điều 4."
    assert footnotes[1]["id"] == "s2"
    assert footnotes[1]["text"] == "Nghị định 136/2020/NĐ-CP, Điều 5."

    # Test formatting
    new_footnotes = [
        {"id": "s1", "citation": "Nghị định 136/2020, Điều 5"},
        {"id": "s2", "citation": "Nghị định 50/2024, Điều 1"},
    ]
    formatted = format_footnote_citations("Nội dung bài viết [^s1] và [^s2].", new_footnotes)
    assert "[^s1]: Nghị định 136/2020, Điều 5" in formatted
    assert "[^s2]: Nghị định 50/2024, Điều 1" in formatted


def test_page_citation_report_and_warning_callout():
    """Verify PageCitationReport calculates correct metrics and generates Obsidian warning callout."""
    source_text = "Hồ sơ thiết kế PCCC được thẩm duyệt trong thời hạn 15 ngày."
    content_md = """
    Hồ sơ thiết kế PCCC được thẩm duyệt trong thời hạn 15 ngày [^s1].
    Mức phạt cho hành vi không lập hồ sơ là 500 triệu đồng và tước giấy phép vĩnh viễn [^s2].

    [^s1]: Nghị định 136/2020.
    [^s2]: Quy định xử phạt hành chính bịa đặt.
    """

    verifier = CitationVerifier()
    report = verifier.verify_page(
        page_slug="quy-dinh-pccc",
        content_md=content_md,
        source_text=source_text,
    )

    assert isinstance(report, PageCitationReport)
    assert report.total_claims >= 2
    assert len(report.unverified_claims) >= 1
    assert report.has_hallucinations is True
    assert report.score < 1.0

    # Test callout injection
    injected_md = apply_citation_callout(content_md, report)
    assert "> [!warning] **Cảnh báo trích dẫn:" in injected_md
    assert "Mức phạt cho hành vi không lập hồ sơ" in injected_md


def test_legal_citation_strict_article_match():
    """Verify that citing a non-existent Điều X inside source triggers unverified status."""
    source_text = """
    Điều 1. Phạm vi điều chỉnh
    Nghị định này quy định về hoạt động PCCC.
    
    Điều 2. Đối tượng áp dụng
    Áp dụng đối với cơ quan, tổ chức, hộ gia đình.
    """
    verifier = CitationVerifier()
    
    # Claim cites Điều 45 which does not exist in source text
    claim = "Theo Điều 45 của Nghị định này, mọi doanh nghiệp phải đóng quỹ PCCC bắt buộc."
    res = verifier.verify_claim(claim, source_text)
    assert res.is_verified is False
    assert "Điều 45" in res.reason or "không có" in res.reason.lower() or res.confidence < 0.5


def test_synthesizer_integration():
    """Verify synthesizer functions for lightweight footnote attachments and polishing."""
    from app.ai.mrp.synthesizer import synthesize_footnotes, verify_and_polish_citations

    raw_md = "Cơ quan công an chịu trách nhiệm quản lý PCCC trên địa bàn [^s1]."
    footnotes = [{"id": "s1", "citation": "Điều 15 Thông tư 149/2020/TT-BCA"}]

    synthesized = synthesize_footnotes(raw_md, footnotes)
    assert "[^s1]: Điều 15 Thông tư 149/2020/TT-BCA" in synthesized

    source_text = "Cơ quan công an chịu trách nhiệm quản lý PCCC trên địa bàn."
    polished_md, report = verify_and_polish_citations(
        content_md=synthesized,
        source_text=source_text,
        page_slug="quan-ly-pccc",
    )
    assert isinstance(report, PageCitationReport)
    assert report.total_claims >= 1
    assert report.verified_claims >= 1
    assert not report.has_hallucinations
    assert "> [!warning]" not in polished_md
