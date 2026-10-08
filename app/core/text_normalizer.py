"""
Text Normalization utilities for Vietnamese and multilingual text ingestion.
Ensures uniform Unicode NFC normalization, whitespace cleaning, and control character removal.
"""

import re
import unicodedata


# Control chars regex: retain \t (\x09) and \n (\x0a), remove all other ASCII control chars (0x00-0x08, 0x0b-0x1f, 0x7f)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_HORIZONTAL_SPACES_RE = re.compile(r"[^\S\r\n\t]+")


def normalize_text(text: str) -> str:
    """Normalize text into Unicode NFC form, clean whitespace and strip control characters.

    Args:
        text: Raw text string from parser or user query.

    Returns:
        Clean, NFC normalized string.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalization (crucial for Vietnamese accents)
    text = unicodedata.normalize("NFC", text)

    # 2. Normalize linebreaks (\r\n -> \n, \r -> \n)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Replace non-breaking spaces and zero-width spaces
    text = text.replace("\u00a0", " ").replace("\ufeff", "").replace("\u200b", "")

    # 4. Remove unwanted control characters
    text = _CONTROL_CHARS_RE.sub("", text)

    # 5. Collapse consecutive horizontal whitespace on each line
    lines = [_HORIZONTAL_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # 6. Collapse excessive blank lines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
