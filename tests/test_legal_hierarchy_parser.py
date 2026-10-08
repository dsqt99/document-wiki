from app.services.legal_hierarchy_parser import (
    LegalHierarchyParser,
    LegalArticle,
    LegalClause,
    LegalPoint,
    LegalChapter,
    LegalDocumentTree,
)


SAMPLE_STANDARD_LAW = """
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc

NGHỊ ĐỊNH
Quy định chi tiết một số điều của Luật Phòng cháy và chữa cháy

Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;
Căn cứ Luật Phòng cháy và chữa cháy...

CHƯƠNG I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Nghị định này quy định chi tiết về phòng cháy và chữa cháy.
a) Phòng cháy đối với cơ sở;
b) Phòng cháy đối với khu dân cư.
2. Áp dụng đối với mọi cơ quan, tổ chức.

Điều 2. Đối tượng áp dụng
Nghị định này áp dụng đối với cơ quan, tổ chức, hộ gia đình và cá nhân.

CHƯƠNG II
BIỆN PHÁP PHÒNG CHÁY

Điều 3. Trách nhiệm phòng cháy
Người đứng đầu cơ sở có trách nhiệm tổ chức thực hiện.
"""


SAMPLE_AMENDING_LAW = """
NGHỊ ĐỊNH
Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP

Điều 1. Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP
1. Sửa đổi, bổ sung Điều 5 như sau:
"Điều 5. Điều kiện an toàn về phòng cháy và chữa cháy đối với cơ sở
1. Cơ sở thuộc danh mục quy định tại Phụ lục III phải bảo đảm các điều kiện sau:
a) Có nội quy, biển cấm, biển báo;
b) Có lực lượng phòng cháy và chữa cháy cơ sở.
2. Trách nhiệm tổ chức thực hiện do người đứng đầu chịu trách nhiệm."

2. Bổ sung Điều 5a như sau:
"Điều 5a. Điều kiện phòng cháy đối với phương tiện giao thông
1. Phương tiện giao thông cơ giới phải có thiết bị chữa cháy.
2. Kiểm định theo quy định."

Điều 2. Hiệu lực thi hành
Nghị định này có hiệu lực thi hành từ ngày 15 tháng 5 năm 2024.
"""


def test_standard_law_hierarchy_parsing():
    """Verify parsing standard legal text into Part -> Chapter -> Section -> Article -> Clause -> Point."""
    parser = LegalHierarchyParser()
    doc_tree = parser.parse(SAMPLE_STANDARD_LAW, doc_number="136/2020/NĐ-CP")

    assert len(doc_tree.chapters) == 2
    ch1 = doc_tree.chapters[0]
    assert ch1.number == "I"
    assert "QUY ĐỊNH CHUNG" in ch1.title
    assert len(ch1.articles) == 2

    # Verify Article 1
    art1 = ch1.articles[0]
    assert art1.number == "1"
    assert "Phạm vi điều chỉnh" in art1.title
    assert len(art1.clauses) == 2

    # Verify Clauses and Points of Article 1
    cl1 = art1.clauses[0]
    assert cl1.number == "1"
    assert len(cl1.points) == 2
    assert cl1.points[0].letter == "a"
    assert "Phòng cháy đối với cơ sở" in cl1.points[0].content
    assert cl1.points[1].letter == "b"

    # Verify Article 3 under Chapter II
    ch2 = doc_tree.chapters[1]
    assert ch2.number == "II"
    assert len(ch2.articles) == 1
    assert ch2.articles[0].number == "3"


def test_amending_law_quoted_text_boundary():
    """Verify quoted articles inside an amending article do NOT create top-level articles."""
    parser = LegalHierarchyParser()
    doc_tree = parser.parse(SAMPLE_AMENDING_LAW, doc_number="50/2024/NĐ-CP")

    # In Decree 50/2024, there are only 2 main articles: Điều 1 and Điều 2!
    # "Điều 5" and "Điều 5a" are inside quotes modifying Decree 136, not articles of Decree 50.
    article_numbers = [art.number for art in doc_tree.get_all_articles()]
    assert article_numbers == ["1", "2"]

    # Verify Article 1 contains the quoted modifications
    art1 = doc_tree.get_all_articles()[0]
    assert art1.is_amending is True
    assert "Điều 5. Điều kiện an toàn" in art1.content
    assert "Điều 5a. Điều kiện phòng cháy" in art1.content
