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
