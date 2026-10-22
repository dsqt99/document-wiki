"""Chia chunk theo token: chunk nằm trong 1.000–2.000 token, gối đầu có kiểm soát, không mất nội dung."""

import pytest

from app.services import chunk_budget as cb
from app.services.verbatim_service import build_source_chunks
from app.services.wiki_chunk_service import build_wiki_chunks

SENTENCE = "Công an tỉnh Hưng Yên thực hiện quy định về phòng cháy chữa cháy và cứu nạn cứu hộ theo đúng thẩm quyền. "


def long_text(tokens: int) -> str:
    per = cb.estimate_tokens(SENTENCE)
    return SENTENCE * (tokens // per + 1)


def test_target_is_clamped_to_1000_2000():
    assert cb.MIN_TARGET_TOKENS == 1000 and cb.MAX_TARGET_TOKENS == 2000
    assert 1000 <= cb.CHUNK_TARGET_TOKENS <= 2000
    assert 0 <= cb.CHUNK_OVERLAP_TOKENS <= cb.CHUNK_TARGET_TOKENS // 4


def test_estimate_tokens_counts_words_and_punctuation():
    assert cb.estimate_tokens("") == 0 and cb.estimate_tokens(None) == 0
    assert cb.estimate_tokens("Điều 5.") == 3  # "Điều"=1, "5"=1, "."=1
    assert cb.estimate_tokens("phòng") == 2  # 5 ký tự -> 2 token
    assert cb.estimate_tokens("a" * 40) == 10


def test_end_for_tokens_stops_near_budget_and_respects_limit():
    text = long_text(5000)
    end = cb.end_for_tokens(text, 0, len(text), 1500)
    got = cb.estimate_tokens(text[:end])
    assert 1500 <= got <= 1500 + 20
    assert cb.end_for_tokens(text, 0, 50, 1500) == 50


def test_source_chunks_fall_in_the_token_window_and_cover_the_text():
    text = long_text(6000)
    chunks = build_source_chunks(text, page_offsets=[])
    assert len(chunks) >= 3
    for c in chunks[:-1]:
        t = cb.estimate_tokens(c.text)
        # Cắt ranh giới có thể lùi tối đa 200 ký tự (~60 token) để không bẻ đôi đoạn văn.
        assert cb.MIN_TARGET_TOKENS <= t <= cb.MAX_TARGET_TOKENS, t
    # Không mất nội dung: mọi vị trí được ít nhất một chunk phủ; chunk liền kề gối nhau.
    assert chunks[0].start_char == 0 and chunks[-1].end_char == len(text)
    for a, b in zip(chunks, chunks[1:]):
        assert b.start_char < a.end_char <= b.end_char


def test_short_text_stays_one_chunk():
    chunks = build_source_chunks(SENTENCE * 5, page_offsets=[])
    assert len(chunks) == 1


def test_legal_source_chunks_keep_articles_separate_and_join_across_pdf_pages():
    text = "PHẦN MỞ ĐẦU\n\n**Điều 1. Phạm vi**\nÁp dụng cho tất cả cán bộ.\n\nTiếp nội dung qua trang.\n\nĐiều 2. Hiệu lực\nCó hiệu lực từ ngày ký."
    chunks = build_source_chunks(text,page_offsets=[0,text.index("Tiếp nội dung")],is_legal=True)
    first = next(chunk for chunk in chunks if "Điều 1." in chunk.text)
    second = next(chunk for chunk in chunks if "Điều 2." in chunk.text)
    assert "Tiếp nội dung" in first.text and "Điều 2." not in first.text
    assert "Điều 1." not in second.text and "Có hiệu lực" in second.text
    assert text[first.start_char:first.end_char] == first.text
    assert first.heading_path.endswith("Điều 1. Phạm vi")


def test_long_legal_article_splits_within_it_without_mixing_the_next_article():
    text = "Điều 1. Quy định dài\n"+long_text(4500)+"\nĐiều 2. Nghĩa vụ\nCán bộ phải báo cáo."
    chunks = build_source_chunks(text,is_legal=True)
    assert len(chunks) >= 4
    assert all(not ("Điều 2." in chunk.text and "Điều 1" in chunk.heading_path) for chunk in chunks)
    assert chunks[-1].text.endswith("Cán bộ phải báo cáo.")


def test_wiki_chunks_split_long_sections_by_tokens():
    md = "# Tiêu đề\n\n" + long_text(5000)
    chunks = build_wiki_chunks(md)
    assert len(chunks) >= 3
    for c in chunks[:-1]:
        assert cb.MIN_TARGET_TOKENS <= cb.estimate_tokens(c.text) <= cb.MAX_TARGET_TOKENS + 20
    assert all(c.heading_path == "Tiêu đề" for c in chunks)


def test_long_table_is_split_by_rows_within_budget_and_keeps_header():
    header = "| STT | Họ tên | Địa chỉ |\n| --- | --- | --- |\n"
    rows = "\n".join(f"| {i} | Nguyễn Văn {i} | Phường {i}, Hưng Yên |" for i in range(900))
    text = f"## Bảng\n\n{header}{rows}\n"
    chunks = [c for c in build_source_chunks(text, page_offsets=[]) if "| STT |" in c.text]
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith(header)
        assert cb.estimate_tokens(c.text) <= cb.CHUNK_TARGET_TOKENS + 40



def test_source_heading_paths_ignore_raw_and_marked_inline_legal_references():
    from app.services.verbatim_service import _find_headings
    text = """# Handbook
## Chương I
### Điều 1. Phạm vi
Áp dụng tại Điều 2,
Điều 3.
cho các cơ quan liên quan.
Điều 5 Nghị định số 136/2020/NĐ-CP
Chương II của Nghị định này
### Điều 6 của Luật này
### Điều 2. Hiệu lực
Nội dung thực hiện.
"""
    titles = [title for _position, _level, title in _find_headings(text)]
    assert titles == ["Handbook", "Chương I", "Điều 1. Phạm vi", "Điều 2. Hiệu lực"]
    chunks = build_source_chunks(text, is_legal=True)
    first = next(chunk for chunk in chunks if "Áp dụng tại" in chunk.text)
    assert "Điều 3." in first.text
    assert "Điều 5 Nghị định số" in first.text
    assert first.heading_path.endswith("Điều 1. Phạm vi")
    assert all(text[chunk.start_char:chunk.end_char] == chunk.text for chunk in chunks)


def test_source_footnote_markup_only_removed_from_heading_paths():
    from app.services.verbatim_service import _find_headings
    text = '### Điều 1.<sup class="footnote">46</sup> Phạm vi\nNội dung áp dụng đầy đủ.\nĐiều 2. Hiệu lực\nCó hiệu lực.'
    titles = [title for _position, _level, title in _find_headings(text)]
    assert titles == ["Điều 1. Phạm vi", "Điều 2. Hiệu lực"]
    chunks = build_source_chunks(text, is_legal=True)
    assert any('<sup class="footnote">46</sup>' in chunk.text for chunk in chunks)
    assert all("46" not in chunk.heading_path and "<sup" not in chunk.heading_path for chunk in chunks)


def test_source_paths_do_not_use_quoted_amendment_articles_as_headings():
    from app.services.verbatim_service import _find_headings
    text = """Điều 1. Sửa đổi
Bổ sung nội dung như sau:
“Điều 40. Điều được sửa
Nội dung được thay đổi.
Điều 41. Điều được bổ sung
Nội dung bổ sung.”
Điều 2. Hiệu lực
Có hiệu lực từ ngày ký.
"""
    titles = [title for _position, _level, title in _find_headings(text)]
    assert titles == ["Điều 1. Sửa đổi", "Điều 2. Hiệu lực"]



def test_source_paths_do_not_treat_marked_quote_as_generic_markdown_heading():
    from app.services.verbatim_service import _find_headings
    text = 'Điều 1. Sửa đổi\n### “Điều 40. Điều được sửa\nNội dung được thay thế.”\nĐiều 2. Hiệu lực\nNội dung thực hiện.'
    assert [title for _position, _level, title in _find_headings(text)] == ["Điều 1. Sửa đổi", "Điều 2. Hiệu lực"]


def test_source_marked_bare_article_reference_does_not_start_a_chunk():
    text = '### Điều 1. Phạm vi\nÁp dụng tại Điều 2,\n### Điều 3.\ncho các cơ quan.\n### Điều 2. Hiệu lực\nCó hiệu lực.'
    chunks = build_source_chunks(text, is_legal=True)
    assert len(chunks) == 2
    assert "### Điều 3." in chunks[0].text
    assert chunks[0].heading_path == "Điều 1. Phạm vi"



def test_source_generic_technical_headings_keep_visible_superscript_digits():
    from app.services.verbatim_service import _find_headings
    text = "## Diện tích (m<sup>2</sup>)\nNội dung diện tích.\n## Diện tích (m<sup>3</sup>)\nNội dung thể tích."
    titles = [title for _position, _level, title in _find_headings(text)]
    assert titles == ["Diện tích (m2)", "Diện tích (m3)"]
    assert titles[0] != titles[1]


def test_end_sections_detect_styled_headings_with_original_offsets():
    from app.services.legal_endmatter import find_end_sections

    text = "Điều 1. Hiệu lực\nNội dung chính.\n\n## **Phụ lục I: Danh mục**\nChương I\nĐiều 1. Nội dung mẫu\n\n<strong>Ghi chú:</strong>\nĐiều 85 của Luật này."
    sections = find_end_sections(text)
    assert [(s.kind, s.title, s.number) for s in sections] == [("appendix", "Phụ lục I: Danh mục", "I"), ("notes", "Ghi chú:", None)]
    assert [s.start for s in sections] == [text.index("## **Phụ lục"), text.index("<strong>Ghi chú")]
    assert sections[0].end == sections[1].start and sections[1].end == len(text)


def test_end_section_labels_inside_prose_quotes_fences_and_tables_are_not_boundaries():
    from app.services.legal_endmatter import find_end_sections

    text = '''Điều 1. Phạm vi
Áp dụng tại Phụ lục I của Nghị định này.
Phụ lục III của Nghị định này quy định danh mục.
“Phụ lục IV
Nội dung được trích dẫn.”
```md
PHỤ LỤC V
GHI CHÚ
```
| Ghi chú | Nội dung |
> PHỤ LỤC VI
Điều 2. Hiệu lực
Nội dung thực hiện.
'''
    assert find_end_sections(text) == []


def test_notes_between_main_articles_do_not_end_the_document():
    from app.services.legal_endmatter import find_end_sections

    text = "Điều 1. Phạm vi\nNội dung.\nGhi chú:\nChỉ áp dụng trong năm nay.\nĐiều 2. Hiệu lực\nNội dung thực hiện.\nChú thích:\nĐiều 1. Tên điều được dẫn lại\nNội dung cuối."
    sections = find_end_sections(text)
    assert len(sections) == 1 and sections[0].start == text.index("Chú thích:")


def test_legal_source_chunks_isolate_end_sections_and_ignore_their_internal_headings():
    text = "Chương I\nĐiều 1. Phạm vi\nNội dung chính.\nĐiều 2. Hiệu lực\nNội dung thi hành.\n\nPHỤ LỤC I\nChương II\nĐiều 1. Quy tắc trong phụ lục\nNội dung biểu mẫu.\n\nPHỤ LỤC II\nĐiều 2. Tên trong biểu mẫu\nNội dung bổ sung.\n\nGHI CHÚ\nĐiều 85 của Luật này quy định nội dung được dẫn chiếu."
    offsets = [0, text.index("Nội dung biểu mẫu.")]
    chunks = build_source_chunks(text, page_offsets=offsets, is_legal=True)
    appendix = next(c for c in chunks if c.text.startswith("PHỤ LỤC I"))
    assert "Điều 1. Quy tắc trong phụ lục" in appendix.text and "Nội dung biểu mẫu." in appendix.text
    assert appendix.heading_path == "PHỤ LỤC I" and appendix.page_number == 1
    tail = [c for c in chunks if c.start_char >= text.index("PHỤ LỤC I")]
    assert [c.heading_path for c in tail] == ["PHỤ LỤC I", "PHỤ LỤC II", "GHI CHÚ"]
    assert all("PHỤ LỤC" not in c.text and "GHI CHÚ" not in c.text for c in chunks if c.start_char < appendix.start_char)
    assert all(text[c.start_char:c.end_char] == c.text for c in chunks)
    assert chunks[0].start_char == 0 and chunks[-1].end_char == len(text)


def test_long_end_sections_use_token_windows_without_chapter_article_paths():
    text = "Điều 1. Hiệu lực\nNội dung chính.\nPHỤ LỤC I\nChương I\nĐiều 1. Mẫu quy định\n" + long_text(5000)
    chunks = build_source_chunks(text, is_legal=True)
    tail = [c for c in chunks if c.start_char >= text.index("PHỤ LỤC I")]
    assert len(tail) >= 3 and all(c.heading_path == "PHỤ LỤC I" for c in tail)
    assert all(cb.estimate_tokens(c.text) <= cb.MAX_TARGET_TOKENS + 20 for c in tail)
    assert tail[0].start_char == text.index("PHỤ LỤC I") and tail[-1].end_char == len(text)
    assert all(a.end_char >= b.start_char for a, b in zip(tail, tail[1:]))


def test_end_sections_keep_crlf_nfd_offsets_and_ignore_code_html_blocks():
    import unicodedata
    from app.services.legal_endmatter import find_end_sections

    text = unicodedata.normalize("NFD", "Điều 1. Nội dung\r\n````md\r\n```\r\nPhụ lục I\r\n````\r\n    Phụ lục II\r\n<table><tr><td>Phụ lục III</td></tr></table>\r\n<blockquote>\r\nGhi chú\r\n</blockquote>\r\n**Ghi chú**\r\nNội dung.\r\nĐiều 2. Hiệu lực\r\nPhụ lục IV\r\nNội dung mẫu.")
    sections = find_end_sections(text)
    assert len(sections) == 1 and sections[0].title == "Phụ lục IV"
    assert text[sections[0].start:].startswith(unicodedata.normalize("NFD", "Phụ lục IV"))
    assert sections[0].end == len(text)


def test_notes_before_appendix_do_not_count_its_articles_as_main_continuation():
    from app.services.legal_endmatter import find_end_sections
    text = "Điều 1. Hiệu lực\nNội dung.\nGhi chú\nNội dung ghi chú.\nPhụ lục I\nĐiều 2. Mẫu\nNội dung mẫu."
    assert [s.kind for s in find_end_sections(text)] == ["notes", "appendix"]


def test_generic_source_heading_paths_after_notes_remain_available():
    from app.services.verbatim_service import _find_headings
    text = "# Hướng dẫn\nNội dung mở đầu.\n## Ghi chú\nThông tin cần nhớ.\n## Các bước tiếp theo\nNội dung tiếp theo."
    assert [title for _, _, title in _find_headings(text)] == ["Hướng dẫn", "Ghi chú", "Các bước tiếp theo"]


def test_end_section_detection_recovers_from_lost_ocr_closing_quote():
    from app.services.legal_endmatter import find_end_sections
    text = "Điều 1. Sửa đổi\nNội dung như sau: “\nĐiều 40. Quy định sửa đổi\nNội dung trích dẫn.\nĐiều 2. Hiệu lực\nNội dung thi hành.\nPhụ lục I\nNội dung mẫu."
    sections = find_end_sections(text)
    assert len(sections) == 1 and sections[0].start == text.index("Phụ lục I")


def test_appendix_reference_index_before_main_articles_is_not_end_matter():
    from app.services.legal_endmatter import find_end_sections
    text = "NGHỊ ĐỊNH\nDanh mục phụ lục kèm theo:\n## phụ lục II: Danh mục cơ sở có nguy hiểm về cháy, nổ.\n3. phụ lục III: Danh mục cơ sở.\n4. Phụ lục IV: Danh mục khác.\nChương II\nĐiều 4. Cơ sở thuộc diện quản lý\nNội dung chính.\nPHỤ LỤC I\nNội dung mẫu."
    sections = find_end_sections(text)
    assert len(sections) == 1 and sections[0].start == text.index("PHỤ LỤC I")


def test_appendix_only_numbered_instructions_are_not_an_appendix_inventory():
    from app.services.legal_endmatter import find_end_sections
    text = "PHỤ LỤC I\nHƯỚNG DẪN LẬP BIỂU MẪU\n1. Phụ lục phải ghi đầy đủ tên cơ sở.\n2. Người lập biểu ký tên."
    assert [s.title for s in find_end_sections(text)] == ["PHỤ LỤC I"]
