"""Conservative recognition of Vietnamese legal headings, without altering text."""

import re
import unicodedata
from typing import Optional


_ARTICLE = re.compile(r"^Điều\s+\d+[a-z]?(?!\w)(.*)$", re.IGNORECASE)
_EXPLICIT_DOCUMENT_REFERENCE = re.compile(
    r"^(?:Nghị định|Luật|Bộ luật|Thông tư|Quyết định|Pháp lệnh)\s+(?:này|số|năm|của|và)\b",
    re.IGNORECASE,
)
_STRUCTURES = (
    (re.compile(r"^PHẦN\s+THỨ\s+[A-ZÀ-Ỹ0-9]+(?!\w)(.*)$", re.IGNORECASE), 1),
    (re.compile(r"^CHƯƠNG\s+[IVXLCDM0-9]+[A-Z]?(?!\w)(.*)$", re.IGNORECASE), 2),
    (re.compile(r"^(?:TIỂU\s+)?MỤC\s+\d+(?!\w)(.*)$", re.IGNORECASE), 3),
    (re.compile(r"^PHỤ\s+LỤC(?:\s+[A-Z0-9]+)?(?!\w)(.*)$", re.IGNORECASE), 2),
)


def _heading_tail(tail: str, *, article: bool = False) -> bool:
    tail = tail.strip()
    if not tail:
        return True
    if tail[0] in ",;":
        return False
    punctuated = tail[0] in ".:"
    if article and not punctuated and _EXPLICIT_DOCUMENT_REFERENCE.match(tail):
        return False
    if punctuated:
        tail = tail[1:].lstrip()
    if not tail:
        return punctuated
    # A wrapped citation starts with "của", "tại", etc.; an unpunctuated
    # title starts with a capital. Explicit article punctuation also permits
    # titles whose initial was printed in lower case.
    first_letter = next((ch for ch in tail if ch.isalpha()), "")
    return bool(first_letter) and (first_letter.isupper() or (article and punctuated))


def _plain_heading_text(text: str) -> str:
    plain = unicodedata.normalize("NFC", text or "")
    plain = re.sub(r"<sup\b[^>]*>.*?</sup>", "", plain, flags=re.IGNORECASE)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = re.sub(r"^\s*#{1,6}\s+", "", plain)
    return plain.replace("**", "").replace("__", "").strip(" *_`\t\r\n")


def is_legal_structure_candidate(text: str) -> bool:
    """Whether a line starts with a legal structure label and its identifier."""
    plain = _plain_heading_text(text)
    return bool(_ARTICLE.match(plain) or any(pattern.match(plain) for pattern, _ in _STRUCTURES))


def is_bare_article_continuation(text: str, previous_body_line: str) -> bool:
    """Identify a bare article identifier continuing an explicit citation list."""
    if re.match(r"^\s*#{1,6}\s+", previous_body_line or ""):
        return False
    previous = _plain_heading_text(previous_body_line)
    plain = _plain_heading_text(text)
    return bool(
        re.fullmatch(r"Điều\s+\d+[a-z]?\.?", plain, flags=re.IGNORECASE)
        and previous.endswith((",", ";"))
        and re.search(r"\bĐiều\s+\d+[a-z]?(?!\w)", previous, flags=re.IGNORECASE)
    )


def legal_heading_level(text: str) -> Optional[int]:
    """Return Markdown level only for a structural heading, not an inline citation.

    Styling and footnote markers are ignored for recognition only; callers
    retain the original text when rendering the result.
    """
    plain = _plain_heading_text(text)
    match = _ARTICLE.match(plain)
    if match:
        return 3 if _heading_tail(match.group(1), article=True) else None
    for pattern, level in _STRUCTURES:
        match = pattern.match(plain)
        if match:
            return level if _heading_tail(match.group(1)) else None
    return None
