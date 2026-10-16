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


# ---------------------------------------------------------------------------
# Keyword extraction for the lexical search arm
# ---------------------------------------------------------------------------

# Question / filler phrases removed before tokenizing (matched accent-folded).
VI_QUESTION_PHRASES = [
    "nhu the nao", "the nao", "ra sao", "la gi", "bao nhieu", "bao gio",
    "o dau", "co phai", "duoc khong", "hay khong", "co khong", "phai khong",
    "cho biet", "cho toi", "cho minh", "xin hoi", "vui long", "tra cuu",
    "tim kiem", "gom nhung gi", "gom nhung", "nhung gi", "nhu vay",
]

# Single tokens dropped from keyword terms. Compared on the ACCENTED lower-case
# token so "tội" (crime) is never confused with "tôi" (I).
VI_STOPWORDS = frozenset({
    "là", "gì", "của", "và", "các", "những", "cho", "với", "về", "theo",
    "trong", "tại", "thì", "mà", "nào", "không", "có", "được", "bị", "sẽ",
    "đã", "đang", "này", "đó", "để", "khi", "nếu", "từ", "đến", "một", "như",
    "thế", "sao", "hay", "hoặc", "tôi", "bạn", "mình", "hỏi", "xin", "ạ",
    "nhé", "à", "ơi", "nhỉ", "gồm", "nên", "phải", "cần", "hãy", "biết",
    "ra", "đâu", "ai", "vậy", "ở", "thì", "rằng", "nhưng", "cũng", "lại",
    "quy_định", "như_thế_nào", "thế_nào", "là_gì", "bao_nhiêu", "bao_giờ",
    "ở_đâu", "cho_biết", "tra_cứu", "vui_lòng", "xin_hỏi", "những_gì",
    "hiện_nay", "hiện_hành", "the", "of", "and", "what", "is", "how",
})

# Official document numbers, matched on accent-folded lower-case text:
#   13/2023/nd-cp · 13/2023 · 123/qd-ubnd · 01/2024/tt-bca
# The look-behind rejects the tail of a date ("15/03/2023" → not "03/2023").
DOC_NUMBER_RE = re.compile(
    r"(?<![\w/])"
    r"(\d{1,5}\s*/\s*(?:\d{4}(?:\s*/\s*[a-z][a-z0-9]*(?:\s*-\s*[a-z0-9]+)*)?"
    r"|[a-z][a-z0-9]*(?:\s*-\s*[a-z0-9]+)+))"
    r"(?![\w/])"
)
DASHES = "‐‑‒–—―−"

_RE_QUOTED = re.compile(r"[\"“”«»]([^\"“”«»]{2,200})[\"“”«»]")


def quoted_phrases(query: str) -> List[str]:
    """Phrases the user put in quotes — matched verbatim (accent-folded, lower)."""
    return [strip_accents(m.strip()).lower() for m in _RE_QUOTED.findall(query or "") if m.strip()]


def keyword_terms(query: str) -> List[str]:
    """Content terms of `query`: accent-folded, compound-joined ("phong_chay"),
    question phrases, document numbers and stopwords removed, de-duplicated,
    in order. Falls back to all tokens when every token is a stopword.
    """
    if not query or not query.strip():
        return []
    text = unicodedata.normalize("NFC", query).lower()
    for d in DASHES:
        text = text.replace(d, "-")
    folded = strip_accents(text)
    if len(folded) == len(text):  # 1:1 fold → blank spans in place
        chars = list(text)
        spans = [m.span() for m in DOC_NUMBER_RE.finditer(folded)]
        for ph in VI_QUESTION_PHRASES:
            spans += [m.span() for m in re.finditer(r"\b" + re.escape(ph) + r"\b", folded)]
        for a, b in spans:
            chars[a:b] = " " * (b - a)
        text = "".join(chars)

    raw = []
    for tok in tokenize_vi(text).split():
        tok = re.sub(r"^[^\w]+|[^\w]+$", "", tok)
        if tok:
            raw.append(tok)

    def _collect(tokens, use_stop: bool) -> List[str]:
        out: List[str] = []
        for tok in tokens:
            if use_stop and tok in VI_STOPWORDS:
                continue
            t = strip_accents(tok)
            if t and t not in out:
                out.append(t)
        return out

    return _collect(raw, True) or _collect(raw, False)


def _ts_term(term: str) -> str:
    """One websearch_to_tsquery operand: compounds become quoted phrases."""
    words = [w for w in re.split(r"[^\w]+|_", term) if w]
    if not words:
        return ""
    return words[0] if len(words) == 1 else '"' + " ".join(words) + '"'


def websearch_all(terms: List[str]) -> str:
    """websearch_to_tsquery input requiring every term (AND)."""
    return " ".join(t for t in (_ts_term(x) for x in terms) if t)


def websearch_any(terms: List[str]) -> str:
    """websearch_to_tsquery input matching any term (OR)."""
    return " or ".join(t for t in (_ts_term(x) for x in terms) if t)


def term_coverage(terms: List[str], text: str) -> float:
    """Fraction of `terms` present in `text` (accent-folded substring match)."""
    if not terms:
        return 0.0
    hay = " " + re.sub(r"\s+", " ", strip_accents((text or "").lower())) + " "
    hits = 0
    for t in terms:
        needle = " ".join(w for w in re.split(r"[^\w]+|_", t) if w)
        if needle and re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", hay):
            hits += 1
    return hits / len(terms)
