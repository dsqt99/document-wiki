import pytest
from app.core.vi_tokenizer import (
    tokenize_vi,
    tokenize_vi_words,
    strip_accents,
    tokenize_vi_dual,
    build_vietnamese_fts_query_terms,
)


def test_tokenize_vi_compound_words():
    """Verify compound words are joined with underscores."""
    text = "Điều kiện an toàn phòng cháy và chữa cháy đối với cơ sở"
    tokenized = tokenize_vi(text)

    # In Vietnamese, 'phòng cháy' and 'chữa cháy' and 'cơ sở' are recognized compound words
    assert "phòng_cháy" in tokenized
    assert "chữa_cháy" in tokenized
    assert "cơ_sở" in tokenized


def test_strip_accents():
    """Verify removing accents while preserving compound word underscores."""
    assert strip_accents("phòng_cháy chữa_cháy") == "phong_chay chua_chay"
    assert strip_accents("Nghị định số 136/2020/NĐ-CP") == "Nghi dinh so 136/2020/ND-CP"


def test_tokenize_vi_dual():
    """Verify returning both accented and unaccented compound representations."""
    text = "kiểm định phương tiện"
    accented, unaccented = tokenize_vi_dual(text)

    assert accented == "kiểm_định phương_tiện"
    assert unaccented == "kiem_dinh phuong_tien"


def test_build_vietnamese_fts_query_terms():
    """Verify query expansion produces both compound and individual terms."""
    query = "phòng cháy cơ sở"
    terms = build_vietnamese_fts_query_terms(query)

    # Should include compound terms and accentless versions
    assert "phòng_cháy" in terms
    assert "phong_chay" in terms
    assert "cơ_sở" in terms
    assert "co_so" in terms
