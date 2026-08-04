"""Unit tests for app/services/wiki_chunk_service.py chunking.

Pure text-splitting logic — no DB, no embedding provider.
"""

from app.services.wiki_chunk_service import (
    CHUNK_TARGET_CHARS,
    MIN_CHUNK_CHARS,
    build_wiki_chunks,
)


def test_empty_content():
    assert build_wiki_chunks("") == []
    assert build_wiki_chunks("   \n\n  ") == []


def test_single_section_no_heading():
    body = "This is a plain paragraph with enough text to clear the minimum."
    chunks = build_wiki_chunks(body)
    assert len(chunks) == 1
    assert chunks[0].heading_path == ""
    assert chunks[0].text.strip() == body


def test_heading_path_breadcrumb():
    md = (
        "# Chương 1\n\n"
        "Nội dung mở đầu của chương một, đủ dài để vượt ngưỡng tối thiểu.\n\n"
        "## Điều 1\n\n"
        "Nội dung điều một, cũng đủ dài để tạo thành một chunk riêng biệt.\n\n"
        "### Khoản a\n\n"
        "Chi tiết khoản a với nội dung dài đủ để không bị bỏ qua khi chunk.\n"
    )
    chunks = build_wiki_chunks(md)
    paths = [c.heading_path for c in chunks]
    assert "Chương 1" in paths
    assert "Chương 1 > Điều 1" in paths
    assert "Chương 1 > Điều 1 > Khoản a" in paths


def test_deeper_heading_resets_siblings():
    md = (
        "# A\n\nNội dung phần A đủ dài để tạo một chunk hợp lệ ở đây.\n\n"
        "## A1\n\nNội dung phần A1 đủ dài để tạo một chunk hợp lệ ở đây.\n\n"
        "# B\n\nNội dung phần B đủ dài để tạo một chunk hợp lệ ở đây.\n"
    )
    chunks = build_wiki_chunks(md)
    paths = [c.heading_path for c in chunks]
    # After H1 "B", the H2 "A1" must not leak into B's breadcrumb.
    assert "B" in paths
    assert all(not p.startswith("B >") for p in paths)


def test_long_section_subsplit_with_overlap():
    long_body = "x" * (CHUNK_TARGET_CHARS * 2 + 500)
    md = f"# Big\n\n{long_body}\n"
    chunks = build_wiki_chunks(md)
    assert len(chunks) >= 2
    # Every sub-chunk keeps the section heading.
    assert all(c.heading_path == "Big" for c in chunks)
    # No chunk exceeds the target window.
    assert all(len(c.text) <= CHUNK_TARGET_CHARS for c in chunks)


def test_indices_are_sequential():
    md = (
        "# One\n\nĐoạn nội dung số một đủ dài để tạo chunk riêng biệt ở đây.\n\n"
        "# Two\n\nĐoạn nội dung số hai đủ dài để tạo chunk riêng biệt ở đây.\n"
    )
    chunks = build_wiki_chunks(md)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_tiny_section_skipped():
    md = "# H\n\nshort\n\n# H2\n\n" + ("y" * (MIN_CHUNK_CHARS + 20))
    chunks = build_wiki_chunks(md)
    # The "short" section is below MIN_CHUNK_CHARS and dropped.
    assert all(len(c.text.strip()) >= MIN_CHUNK_CHARS for c in chunks)
    assert all(c.text.strip() != "short" for c in chunks)
