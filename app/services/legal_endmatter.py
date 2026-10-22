"""Read-only boundaries for opaque notes/appendices following a legal text."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from app.core.legal_headings import legal_heading_level


@dataclass(frozen=True)
class EndSection:
    kind: str
    title: str
    number: Optional[str]
    start: int
    end: int


_APPENDIX = re.compile(r"^Phụ\s+lục(?:\s+([IVXLCDM]+[a-z]?|\d+[a-z]?|[A-Z]))?(?!\w)(.*)$", re.I)
_NOTES = re.compile(r"^(Ghi\s+chú|Chú\s+thích)(?:\s*[:.]\s*(.*))?$", re.I)
_REFERENCE = re.compile(r"^(?:của|tại|theo|này|được|quy\s+định|ban\s+hành|kèm\s+theo)\b", re.I)
_ARTICLE_NUMBER = re.compile(r"^Điều\s+(\d+)[a-z]?(?!\w)", re.I)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HTML_BLOCK = re.compile(r"<(\/?)(table|blockquote|pre|code)\b[^>]*>", re.I)


def _plain_label(line: str) -> str:
    plain = unicodedata.normalize("NFC", html.unescape(line))
    plain = re.sub(r"<sup\b[^>]*>.*?</sup>", "", plain, flags=re.I)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = re.sub(r"^\s*#{1,6}\s+", "", plain)
    return plain.replace("**", "").replace("__", "").strip(" *_`\t\r\n")


def _section_label(plain: str) -> Optional[tuple[str, str, Optional[str]]]:
    note = _NOTES.fullmatch(plain)
    if note:
        return "notes", plain, None
    match = _APPENDIX.fullmatch(plain)
    if not match:
        return None
    tail = match.group(2).strip()
    if tail and _REFERENCE.match(tail):
        return None
    if tail and tail[0] not in ".:–-(" and not tail[0].isupper():
        return None
    return "appendix", plain, match.group(1)


def find_end_sections(text: str) -> list[EndSection]:
    """Return exact raw offsets, excluding inline, quoted, table and code labels.

    Notes before the next sequential main article remain body text. After an
    appendix begins, article/chapter labels inside it never resume main parsing.
    """
    eligible_lines = []
    position = 0
    fence = None
    html_blocks: dict[str, int] = {}
    for line in (text or "").splitlines(keepends=True):
        start = position
        position += len(line)
        fence_match = _FENCE.match(line)
        if fence_match:
            run, info = fence_match.groups()
            if fence is None:
                fence = (run[0], len(run))
            elif run[0] == fence[0] and len(run) >= fence[1] and not info.strip():
                fence = None
            continue
        if fence is not None:
            continue
        block_matches = list(_HTML_BLOCK.finditer(line))
        in_html_block = any(html_blocks.values()) or bool(block_matches)
        for block in block_matches:
            tag = block.group(2).lower()
            html_blocks[tag] = max(0, html_blocks.get(tag, 0) + (-1 if block.group(1) else 1))
        if in_html_block or line.startswith(("    ", "\t")) or line.lstrip().startswith(("|", ">")):
            continue
        plain = _plain_label(line)
        if not plain:
            continue
        article = _ARTICLE_NUMBER.match(plain) if legal_heading_level(plain) == 3 else None
        eligible_lines.append((start, plain, int(article.group(1)) if article else None))

    records = []
    quoted = False
    last_main_article = None
    sequences = [number for _, _, number in eligible_lines]
    for index, (start, plain, article) in enumerate(eligible_lines):
        if quoted and article == (last_main_article or 0) + 1 and article not in sequences[index + 1:]:
            quoted = False
        label = _section_label(plain) if not quoted else None
        records.append((start, label, article if not quoted else None))
        if article is not None and not quoted:
            last_main_article = article
        for mark in plain:
            if mark == '“':
                quoted = True
            elif mark == '”':
                quoted = False
            elif mark == '"':
                quoted = not quoted

    starts = []
    last_article = None
    in_tail = False
    for index, (start, label, article) in enumerate(records):
        if not in_tail and article is not None:
            last_article = article
        if label is None:
            continue
        kind, title, number = label
        if not in_tail and kind == "appendix" and last_article is None and any(
            re.match(r"^(?:\d+[.)]|[-+*])\s+Phụ\s+lục\s+(?:[IVXLCDM]+|\d+|[A-Z])(?:\s*[:.]|\s*$)", later_plain, re.I)
            for _, later_plain, _ in eligible_lines[index + 1:index + 4]
        ) and any(number is not None for _, _, number in records[index + 1:]):
            # OCR can turn an entry in the opening appendix inventory into a
            # heading. Subsequent numbered appendix entries identify that list.
            continue
        if not in_tail and kind == "notes" and last_article is not None:
            next_main_article = False
            for _start, later_label, later_article in records[index + 1:]:
                if later_label and later_label[0] == "appendix":
                    break
                if later_article == last_article + 1:
                    next_main_article = True
                    break
            if next_main_article:
                continue
        in_tail = True
        starts.append((start, kind, title, number))
    return [EndSection(kind, title, number, start, starts[i + 1][0] if i + 1 < len(starts) else len(text))
            for i, (start, kind, title, number) in enumerate(starts)]
