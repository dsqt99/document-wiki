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


SAMPLE_MARKDOWN_LAW = """
**Điều 1. Phạm vi điều chỉnh**

Luật này quy định về đường sắt.

**Điều 2. Phân loại**

<mark>a) Đường sắt tốc độ cao; b) Đường sắt thường.</mark> **Điều 3. Khổ đường sắt**

1. Khổ đường tiêu chuẩn là 1435 mm.

**QUY ĐỊNH CHUNG VỀ ĐẦU TƯ XÂY DỰNG ĐƯỜNG SẮT Điều 4. Quy hoạch đường sắt**

Nội dung quy hoạch.

### Điều 51 của Luật Đầu tư số 143/2025/QH15 quy định như sau:

“ **_Điều 51. Hiệu lực thi hành_**

_1. Luật này có hiệu lực thi hành từ ngày 01 tháng 03 năm 2026._

## **Điều 5. Hiệu lực thi hành**

Luật này có hiệu lực từ ngày 01 tháng 7 năm 2026.
"""


def test_markdown_glued_headings_and_lost_closing_quote():
    tree = LegalHierarchyParser().parse(SAMPLE_MARKDOWN_LAW)
    arts = tree.get_all_articles()
    assert [a.number for a in arts] == ["1", "2", "3", "4", "5"]
    assert arts[2].title == "Khổ đường sắt"
    assert arts[3].title == "Quy hoạch đường sắt"
    # The in-text reference and its quoted footnote stay inside Điều 4.
    assert "Luật Đầu tư" in arts[3].content
    assert arts[4].title == "Hiệu lực thi hành"


def test_quoted_next_article_is_not_closed_when_number_repeats_later():
    text = """
Điều 1. Sửa đổi Nghị định số 136/2020/NĐ-CP
1. Sửa đổi Điều 2 như sau:
“
Điều 2. Giải thích từ ngữ
Nội dung mới.
”
Điều 2. Hiệu lực thi hành
Nghị định này có hiệu lực từ ngày ký.
"""
    arts = LegalHierarchyParser().parse(text).get_all_articles()
    assert [a.number for a in arts] == ["1", "2"]
    assert "Điều 2. Giải thích từ ngữ" in arts[0].content
    assert arts[1].title == "Hiệu lực thi hành"


def test_unclosed_quote_in_preamble_footnote_does_not_swallow_first_articles():
    # Consolidated text: a preamble footnote quotes a title and loses its closing mark.
    text = """
NGHỊ ĐỊNH
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường thủy nội địa

> 1 Nghị định số 80/2026/NĐ-CP sửa đổi, bổ sung “Nghị định quy định xử phạt vi phạm hành chính

# **Chương I NHỮNG QUY ĐỊNH CHUNG**

# **Điều 1. Phạm vi điều chỉnh**
Nghị định này quy định về hành vi vi phạm hành chính.

**Điều 2. Đối tượng áp dụng**
Cá nhân, tổ chức có hành vi vi phạm.
Ghi chú: hướng dẫn tại văn bản số 12” của Bộ.

**Điều 3. Giải thích từ ngữ**
Nội dung.
"""
    tree = LegalHierarchyParser().parse(text)
    arts = tree.get_all_articles()
    assert [a.number for a in arts] == ["1", "2", "3"]
    assert tree.chapters[0].number == "I"
    assert [a.number for a in tree.chapters[0].articles] == ["1", "2", "3"]


def test_wrapped_reference_lists_are_not_article_headings():
    text = """
**Điều 42. Phân định thẩm quyền xử phạt**
1. Công an có thẩm quyền xử phạt đối với hành vi quy định tại:
<mark>Điều 5; Điều 6; khoản 1, khoản 2 Điều 7; Điều 8;</mark> Điều 9; Điều 10.
<mark>i) Điều 33; Điều 34; Điều 40;</mark> Điều 41.
9. Chi cục trưởng có thẩm quyền xử phạt.

**Điều 43. Thẩm quyền lập biên bản**
Nội dung.
"""
    arts = LegalHierarchyParser().parse(text).get_all_articles()
    assert [a.number for a in arts] == ["42", "43"]
    assert "Điều 41." in arts[0].content and "9. Chi cục trưởng" in arts[0].content


def test_wrapped_chapter_reference_keeps_the_rest_of_the_current_article():
    text = """
CHƯƠNG I
NHỮNG QUY ĐỊNH CHUNG
Điều 4. Hình thức xử phạt
5. Mức phạt tiền đối với mỗi hành vi vi phạm hành chính quy định tại
## Chương II của Nghị định này là mức phạt tiền đối với cá nhân; trường hợp có
cùng một hành vi vi phạm hành chính thì mức phạt tiền đối với tổ chức bằng 02
lần mức phạt tiền đối với cá nhân.
Điều 4a. Thi hành các hình thức xử phạt
1. Nội dung được thực hiện theo
### Điều 85 của Luật Xử lý vi phạm hành chính.
CHƯƠNG II
HÀNH VI VI PHẠM
Điều 5. Vi phạm quy định
1. Nội dung điều 5.
"""
    tree = LegalHierarchyParser().parse(text)
    assert [chapter.number for chapter in tree.chapters] == ["I", "II"]
    articles = tree.get_all_articles()
    assert [article.number for article in articles] == ["4", "4a", "5"]
    assert "Chương II của Nghị định này" in articles[0].content
    assert "lần mức phạt tiền đối với cá nhân." in articles[0].content
    assert "Điều 85 của Luật" in articles[1].content


def test_amended_chapter_suffix_is_preserved_and_not_treated_as_previous_chapter():
    tree = LegalHierarchyParser().parse("""
Chương III
QUY ĐỊNH CHUNG
Điều 20. Nội dung trước sửa đổi
1. Nội dung.
Chương IIIa
QUY ĐỊNH BỔ SUNG
Điều 20a. Nội dung bổ sung
1. Nội dung mới.
""")
    assert [chapter.number for chapter in tree.chapters] == ["III", "IIIa"]
    assert tree.get_all_articles()[1].chapter_num == "IIIa"


def test_extracted_source_outline_ignores_reference_headings_without_changing_offsets():
    from app.services.source_outline import build_outline, flatten_outline

    text = "## Chương I\n### Điều 4. Hình thức xử phạt\nNội dung quy định tại\n## Chương II của Nghị định này.\n### Điều 85 của Luật Xử lý vi phạm hành chính.\nĐiều 5; Điều 40;\n### Điều 41.\n### Điều 42 Nghị định này;\n### Điều 4a. Thi hành\nNội dung."
    nodes = flatten_outline(build_outline([{"page_number": 6, "content": text}]))
    assert [node["title"] for node in nodes] == ["Chương I", "Điều 4. Hình thức xử phạt", "Điều 4a. Thi hành"]
    assert nodes[-1]["char_start"] == text.index("### Điều 4a.")
    assert nodes[-1]["page"] == 6


def test_bare_article_and_document_references_do_not_split_current_article():
    text = """
Điều 42. Thẩm quyền xử phạt
1. Áp dụng các quy định sau: Điều 5; Điều 40;
### Điều 41.
Nội dung tiếp tục theo
### Điều 42 Nghị định này;
Điều 43. Thẩm quyền lập biên bản
1. Nội dung.
"""
    articles = LegalHierarchyParser().parse(text).get_all_articles()
    assert [article.number for article in articles] == ["42", "43"]
    assert "Điều 41." in articles[0].content
    assert "Điều 42 Nghị định này;" in articles[0].content


def test_extracted_outline_footnote_does_not_change_article_number_or_title():
    from app.services.source_outline import build_outline, flatten_outline

    text = "### Điều 46<sup>33</sup>. (được bãi bỏ)\n### Điều 48. Thẩm quyền<sup>35</sup>"
    nodes = flatten_outline(build_outline([{"page_number": 55, "content": text}]))
    assert [node["title"] for node in nodes] == ["Điều 46. (được bãi bỏ)", "Điều 48. Thẩm quyền"]
    assert nodes[1]["char_start"] == text.index("### Điều 48.")


def test_extracted_outline_preserves_technical_heading_exponents():
    from app.services.source_outline import build_outline, flatten_outline

    nodes = flatten_outline(build_outline(["## Diện tích (m<sup>2</sup>)\n## Thể tích (m<sup>3</sup>)"]))
    assert [node["title"] for node in nodes] == ["Diện tích (m<sup>2</sup>)", "Thể tích (m<sup>3</sup>)"]


def test_terminal_sections_are_opaque_to_main_legal_hierarchy():
    text = (
        "Căn cứ văn bản gốc.\nĐiều 1. Thi hành\n1. Nội dung chính.\n"
        "## CHÚ THÍCH\n1. Sửa đổi Điều 99 của Luật khác.\n"
        "## PHỤ LỤC I\n## Chương I\n### Điều 1. Mẫu áp dụng\nNội dung mẫu."
    )
    tree = LegalHierarchyParser().parse(text)
    assert [a.number for a in tree.get_all_articles()] == ["1"]
    assert tree.get_all_articles()[0].content == "Điều 1. Thi hành\n1. Nội dung chính."
    assert tree.chapters == []
    assert [s["kind"] for s in tree.end_sections] == ["notes", "appendix"]
    assert "Điều 99" in tree.end_sections[0]["content_md"]
    assert "### Điều 1. Mẫu áp dụng" in tree.appendices[0]["content_md"]
    assert tree.appendices == [tree.end_sections[1]]


def test_appendix_only_document_retains_content_without_inventing_articles():
    text = "## PHỤ LỤC I\n## Chương I\n### Điều 1. Biểu mẫu\nNội dung mẫu."
    tree = LegalHierarchyParser().parse(text)
    assert tree.get_all_articles() == []
    assert tree.preamble == ""
    assert tree.end_sections[0]["content_md"] == text


def test_endmatter_split_slugs_are_unique_stable_and_keep_legacy_fields():
    from app.services.legal_service import split_legal_text_by_articles

    text = "Điều 1. Thi hành\nNội dung.\nPHỤ LỤC I\nMẫu một.\nPHỤ LỤC I\nMẫu hai.\nCHÚ THÍCH\nGiải thích."
    parsed = split_legal_text_by_articles(text, "Luật A", "luat-a")
    assert len(parsed["articles"]) == 1
    assert parsed["preamble"] == ""
    sections = parsed["end_sections"]
    assert [s["kind"] for s in sections] == ["appendix", "appendix", "notes"]
    assert [s["number"] for s in sections[:2]] == ["I", "I"]
    assert len({s["slug"] for s in sections}) == 3
    assert sections == split_legal_text_by_articles(text, "Luật A", "luat-a")["end_sections"]
    assert "Mẫu hai." in sections[1]["content_md"]


def test_split_keeps_appendix_only_and_empty_legacy_shapes():
    from app.services.legal_service import split_legal_text_by_articles

    text = "PHỤ LỤC I\nĐiều 1. Mẫu\nNội dung mẫu."
    parsed = split_legal_text_by_articles(text, "Luật A", "luat-a")
    assert parsed["preamble"] == "" and parsed["articles"] == []
    assert parsed["end_sections"][0]["content_md"] == text
    assert split_legal_text_by_articles("", "Luật A") == {"preamble": "", "articles": [], "end_sections": []}
    parsed = split_legal_text_by_articles("Nội dung không có điều.", "Luật A")
    assert parsed == {"preamble": "Nội dung không có điều.", "articles": [], "end_sections": []}


def test_indented_appendix_label_does_not_hide_later_main_articles():
    text = "Điều 1. Thi hành\n    Phụ lục I\n    sample\nĐiều 2. Thực hiện\nNội dung."
    tree = LegalHierarchyParser().parse(text)
    assert [a.number for a in tree.get_all_articles()] == ["1", "2"]
    assert "Phụ lục I" in tree.get_all_articles()[0].content
    assert tree.end_sections == []
    assert tree.appendices == []
