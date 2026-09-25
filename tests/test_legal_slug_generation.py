import pytest
import uuid

from app.services.legal_service import build_legal_doc_slug, split_legal_text_by_articles


def test_build_legal_doc_slug_with_doc_number():
    slug1 = build_legal_doc_slug(
        doc_title="Nghị định quy định chi tiết một số điều và biện pháp thi hành Luật Phòng cháy và chữa cháy",
        doc_number="136/2020/NĐ-CP",
    )
    slug2 = build_legal_doc_slug(
        doc_title="Nghị định quy định chi tiết một số điều và biện pháp thi hành Luật An toàn thông tin mạng",
        doc_number="85/2016/NĐ-CP",
    )

    assert slug1 != slug2
    assert "136" in slug1
    assert "85" in slug2


def test_build_legal_doc_slug_without_doc_number_uses_source_id_or_hash():
    title = "Nghị định quy định chi tiết một số điều và biện pháp thi hành Luật Rất Dài Có Tiền Tố Giống Nhau"
    sid1 = uuid.uuid4()
    sid2 = uuid.uuid4()

    slug1 = build_legal_doc_slug(doc_title=title, source_id=sid1)
    slug2 = build_legal_doc_slug(doc_title=title, source_id=sid2)

    assert slug1 != slug2
    assert str(sid1).replace("-", "")[:8] in slug1
    assert str(sid2).replace("-", "")[:8] in slug2


def test_split_legal_text_by_articles_avoids_slug_collision():
    text = "Điều 1. Phạm vi điều chỉnh\nĐiều 2. Đối tượng áp dụng"
    
    slug_doc1 = build_legal_doc_slug("Nghị định ABC rất dài", doc_number="136/2020/NĐ-CP")
    slug_doc2 = build_legal_doc_slug("Nghị định ABC rất dài", doc_number="50/2024/NĐ-CP")

    parsed1 = split_legal_text_by_articles(text, "Nghị định ABC rất dài", doc_slug=slug_doc1)
    parsed2 = split_legal_text_by_articles(text, "Nghị định ABC rất dài", doc_slug=slug_doc2)

    slugs1 = [a["slug"] for a in parsed1["articles"]]
    slugs2 = [a["slug"] for a in parsed2["articles"]]

    # Ensure no intersection between article slugs of the two documents
    assert not set(slugs1).intersection(set(slugs2))
