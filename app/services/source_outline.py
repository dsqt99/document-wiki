"""Full-text assembly, page offsets and heading outline for ingested sources."""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

PAGE_JOIN_SEPARATOR = "\n\n"

_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_TRUNCATED_SUFFIX = "\n\n[…truncated…]"


def _page_content(page: Any) -> str:
    if isinstance(page, dict):
        return str(page.get("content") or "")
    return str(page or "")


def assemble_full_text(pages: Iterable[Any]) -> tuple[str, list[int]]:
    """Normalize each page and join them; return the text and per-page start offsets."""
    from app.core.text_normalizer import normalize_text

    parts: list[str] = []
    offsets: list[int] = []
    cursor = 0
    for i, page in enumerate(pages or []):
        if i > 0:
            cursor += len(PAGE_JOIN_SEPARATOR)
        content = normalize_text(_page_content(page))
        offsets.append(cursor)
        parts.append(content)
        cursor += len(content)
    return PAGE_JOIN_SEPARATOR.join(parts), offsets


def _page_bounds(full_text: str, page_offsets: list[int], idx: int) -> tuple[int, int]:
    start = int(page_offsets[idx])
    if idx + 1 < len(page_offsets):
        end = int(page_offsets[idx + 1]) - len(PAGE_JOIN_SEPARATOR)
    else:
        end = len(full_text)
    start = max(0, min(start, len(full_text)))
    end = max(start, min(end, len(full_text)))
    return start, end


def slice_pages_by_range(full_text: str, page_offsets: list[int], page_numbers: Iterable[int]) -> list[dict]:
    full_text = full_text or ""
    offsets = list(page_offsets or [])
    out: list[dict] = []
    for p in page_numbers or []:
        try:
            p = int(p)
        except (TypeError, ValueError):
            continue
        if p < 1 or p > len(offsets):
            continue
        start, end = _page_bounds(full_text, offsets, p - 1)
        out.append({"page": p, "content": full_text[start:end]})
    return out


def parse_page_range(spec: Optional[str]) -> list[int]:
    pages: set[int] = set()
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s.strip()), int(hi_s.strip())
            except ValueError:
                continue
            if lo < 1 or hi < lo:
                continue
            pages.update(range(lo, hi + 1))
        else:
            try:
                n = int(part)
            except ValueError:
                continue
            if n >= 1:
                pages.add(n)
    return sorted(pages)


def build_outline(pages: Iterable[Any]) -> list[dict]:
    """Build a heading tree from ATX headings in the raw page contents."""
    flat: list[dict] = []
    cursor = 0
    page_list = list(pages or [])
    for i, page in enumerate(page_list):
        if i > 0:
            cursor += len(PAGE_JOIN_SEPARATOR)
        content = _page_content(page)
        page_no = page.get("page_number") if isinstance(page, dict) else None
        if not page_no:
            page_no = i + 1
        line_pos = 0
        for line in content.split("\n"):
            m = _ATX_HEADING.match(line.strip())
            if m:
                title = m.group(2).strip()
                if title:
                    flat.append(
                        {
                            "title": title,
                            "level": len(m.group(1)),
                            "page": page_no,
                            "char_start": cursor + line_pos,
                            "char_end": None,
                            "children": [],
                        }
                    )
            line_pos += len(line) + 1
        cursor += len(content)
    if not flat:
        return []
    total = cursor
    for idx, node in enumerate(flat):
        node["char_end"] = flat[idx + 1]["char_start"] if idx + 1 < len(flat) else total

    roots: list[dict] = []
    stack: list[dict] = []
    for node in flat:
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def slice_by_outline_node(full_text: str, start: int, end: int, max_chars: Optional[int] = None) -> str:
    text = (full_text or "")[max(0, int(start or 0)) : max(0, int(end or 0))]
    if max_chars is not None and max_chars >= 0 and len(text) > max_chars:
        text = text[:max_chars] + _TRUNCATED_SUFFIX
    return text


def _flat_entry(node: dict) -> dict:
    return {
        "title": node.get("title"),
        "level": node.get("level"),
        "page": node.get("page"),
        "char_start": node.get("char_start"),
        "char_end": node.get("char_end"),
    }


def flatten_outline(nodes: Optional[list[dict]]) -> list[dict]:
    out: list[dict] = []
    for node in nodes or []:
        out.append(_flat_entry(node))
        out.extend(flatten_outline(node.get("children") or []))
    return out


def flatten_outline_with_depth(nodes: Optional[list[dict]], depth: int = 0) -> list[dict]:
    out: list[dict] = []
    for node in nodes or []:
        entry = _flat_entry(node)
        entry["_depth"] = depth
        out.append(entry)
        out.extend(flatten_outline_with_depth(node.get("children") or [], depth + 1))
    return out


def find_smallest_node_containing(flat: Optional[list[dict]], offset: int) -> Optional[dict]:
    best: Optional[dict] = None
    best_span: Optional[int] = None
    for node in flat or []:
        try:
            s, e = int(node.get("char_start")), int(node.get("char_end"))
        except (TypeError, ValueError):
            continue
        if s <= offset < e or (s == offset == e):
            span = e - s
            if best_span is None or span < best_span:
                best, best_span = node, span
    return best
