"""Small text helpers shared by the AI pipelines."""

import json
import re
import unicodedata
from typing import Any

_FENCE_RE = re.compile(r"^```(?:json|JSON)?[ \t]*\r?\n(.*?)\r?\n?```$", re.DOTALL)


def strip_code_fence(raw: str) -> str:
    text = (raw or "").strip()
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1)
    return text.strip()


def parse_json_loose(raw: str) -> Any:
    text = strip_code_fence(raw)
    try:
        return json.loads(text)
    except (ValueError, TypeError) as original:
        cut = max(text.rfind("}"), text.rfind("]"))
        if cut < 0:
            raise original
        return json.loads(text[: cut + 1])


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    if not text:
        return ""
    value = text.lower().replace("đ", "d").replace("Đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = _NON_ALNUM.sub("-", value)
    return value.strip("-")


ELLIPSIS = "…"
_CLAUSE_END = re.compile(r"[.;:!?](?=\s|$)")


def clip_text(text: str, limit: int) -> str:
    """Collapse whitespace and shorten to ``limit`` chars without cutting a word in half.

    Prefers the last sentence/clause end in the back half of the window; a shortened
    result always ends with "…" so readers know the text goes on.
    """
    s = " ".join((text or "").split())
    if len(s) <= limit:
        return s
    window = s[: max(1, limit - 2)]
    ends = [m.end() for m in _CLAUSE_END.finditer(window)]
    if ends and ends[-1] >= limit * 0.6:
        return window[: ends[-1]] + " " + ELLIPSIS
    space = window.rfind(" ")
    if space >= limit * 0.5:
        window = window[:space]
    return window.rstrip(" ,;:-–—") + ELLIPSIS


def clip_around(text: str, start: int, end: int, before: int = 200, after: int = 300) -> str:
    """The part of ``text`` around ``text[start:end]``, widened to word boundaries, "…" where cut."""
    s = text or ""
    lo, hi = max(0, start - before), min(len(s), end + after)
    if lo > 0:
        space = s.find(" ", lo, start)
        lo = space + 1 if space >= 0 else lo
    if hi < len(s):
        space = s.rfind(" ", end, hi)
        hi = space if space >= 0 else hi
    out = " ".join(s[lo:hi].split())
    return (ELLIPSIS if lo > 0 else "") + out + (ELLIPSIS if hi < len(s) else "")
