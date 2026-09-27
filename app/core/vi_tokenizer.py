"""Vietnamese Word Segmentation & Tokenization for Full-Text Search.

Uses pyvi (Vietnamese NLP Toolkit) to tokenize compound words (e.g. 'phòng_cháy', 'chữa_cháy')
and provides dual accented / unaccented representations to maximize FTS precision and recall.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

try:
    from pyvi import ViTokenizer
    _PYVI_AVAILABLE = True
except ImportError:
    _PYVI_AVAILABLE = False


VI_CHAR_MAP = {
    "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ằ": "a", "ắ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ầ": "a", "ấ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ề": "e", "ế": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ồ": "o", "ố": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ờ": "o", "ớ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ừ": "u", "ứ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "đ": "d",
    "À": "A", "Á": "A", "Ả": "A", "Ã": "A", "Ạ": "A",
    "Ă": "A", "Ằ": "A", "Ắ": "A", "Ẳ": "A", "Ẵ": "A", "Ặ": "A",
    "Â": "A", "Ầ": "A", "Ấ": "A", "Ẩ": "A", "Ẫ": "A", "Ậ": "A",
    "È": "E", "É": "E", "Ẻ": "E", "Ẽ": "E", "Ẹ": "E",
    "Ê": "E", "Ề": "E", "Ế": "E", "Ể": "E", "Ễ": "E", "Ệ": "E",
    "Ì": "I", "Í": "I", "Ỉ": "I", "Ĩ": "I", "Ị": "I",
    "Ò": "O", "Ó": "O", "Ỏ": "O", "Õ": "O", "Ọ": "O",
    "Ô": "O", "Ồ": "O", "Ố": "O", "Ổ": "O", "Ỗ": "O", "Ộ": "O",
    "Ơ": "O", "Ờ": "O", "Ớ": "O", "Ở": "O", "Ỡ": "O", "Ợ": "O",
    "Ù": "U", "Ú": "U", "Ủ": "U", "Ũ": "U", "Ụ": "U",
    "Ư": "U", "Ừ": "U", "Ứ": "U", "Ử": "U", "Ữ": "U", "Ự": "U",
    "Ỳ": "Y", "Ý": "Y", "Ỷ": "Y", "Ỹ": "Y", "Ỵ": "Y",
    "Đ": "D",
}


LEGAL_COMPOUNDS = [
    "phòng cháy chữa cháy",
    "phòng cháy",
    "chữa cháy",
    "cứu nạn cứu hộ",
    "cứu nạn",
    "cứu hộ",
    "an toàn",
    "cơ sở",
    "phương tiện",
    "kiểm định",
    "nghiệm thu",
    "nghị định",
    "thông tư",
    "quyết định",
    "văn bản",
    "quy định",
    "biện pháp",
    "trách nhiệm",
    "điều kiện",
    "đối tượng",
    "thẩm duyệt",
    "thi công",
]


def _join_legal_compounds(text: str) -> str:
    """Pre-join key legal & PCCC compound phrases."""
    res = text
    for phrase in sorted(LEGAL_COMPOUNDS, key=len, reverse=True):
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b"
        replacement = phrase.replace(" ", "_")
        res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
    return res


def strip_accents(text: str) -> str:
    """Remove Vietnamese diacritics / tone marks while preserving casing and structure."""
    if not text:
        return ""
    # Direct mapping for Vietnamese characters
    res = "".join(VI_CHAR_MAP.get(c, c) for c in text)
    # Decompose any remaining unicode combining marks
    nfd = unicodedata.normalize("NFD", res)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def tokenize_vi(text: str) -> str:
    """Segment Vietnamese compound words using pyvi and domain dictionary (e.g. 'phòng_cháy', 'chữa_cháy')."""
    if not text:
        return ""
    
    # 1. Pre-join legal domain compounds
    text = _join_legal_compounds(text)

    # 2. Pyvi segmentation for general vocabulary
    if _PYVI_AVAILABLE:
        try:
            text = ViTokenizer.tokenize(text)
        except Exception:
            pass

    return text


def tokenize_vi_words(text: str) -> List[str]:
    """Tokenize text into a list of words / compound tokens."""
    tokenized = tokenize_vi(text)
    return tokenized.split()


def tokenize_vi_dual(text: str) -> Tuple[str, str]:
    """Return both accented and unaccented compound-tokenized strings."""
    accented = tokenize_vi(text)
    unaccented = strip_accents(accented)
    return accented, unaccented


def build_vietnamese_fts_query_terms(query: str) -> List[str]:
    """Build expanded list of terms for FTS query including compound and unaccented tokens."""
    if not query:
        return []

    accented, unaccented = tokenize_vi_dual(query)
    tokens_acc = accented.split()
    tokens_unacc = unaccented.split()

    terms = []
    seen = set()

    for t in tokens_acc + tokens_unacc:
        # Strip trailing punctuation
        clean_t = re.sub(r"^[^\w]+|[^\w]+$", "", t)
        if clean_t and clean_t not in seen:
            seen.add(clean_t)
            terms.append(clean_t)

    return terms
