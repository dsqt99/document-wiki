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
