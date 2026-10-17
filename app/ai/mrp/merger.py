"""Merge freshly written page content into an existing wiki page (05a §5.7)."""

from __future__ import annotations

import asyncio
import re

from loguru import logger

from app.services.wiki_write_guard import missing_row_identities, table_row_identities
from app.utils.text import strip_code_fence

BODY_SHRINK_RATIO = 0.7
MERGE_TIMEOUT_S = 120
MAX_ROW_LOSS = 0.2
MIN_EXISTING_CHARS = 50
APPEND_FALLBACK_HEADING = "## Bổ sung từ nguồn mới"

_LEADING_H1_RE = re.compile(r"^\s*#\s+[^\n]*\n?")

MERGE_SYSTEM_PROMPT = (
    "You maintain an internal knowledge wiki. You combine two versions of the same "
    "wiki page into one coherent page. Output Markdown only, without commentary."
)

_MERGE_PROMPT = """Combine the two versions of the wiki page `{slug}` below into one page.

Rules:
- Keep every fact, figure, rule, table row and example from BOTH versions; drop only true duplicates.
- Organise the result under H2 sections, keeping a single H1 title.
- Keep all [[wikilinks]] and every image marker (image://...) exactly as written.
- Write in the same language as the inputs.
- Return only the merged Markdown.

=== EXISTING PAGE ===
{existing}

=== NEW CONTENT ===
{incoming}
"""


def _drop_leading_h1(md: str) -> str:
    return _LEADING_H1_RE.sub("", md or "", count=1).strip()


def append_fallback(existing: str, incoming: str) -> str:
    body = _drop_leading_h1(incoming)
    if not body:
        return existing
    return f"{(existing or '').rstrip()}\n\n---\n\n{APPEND_FALLBACK_HEADING}\n\n{body}\n"


def _row_loss_ratio(old: str, new: str) -> float:
    before = table_row_identities(old)
    if not before:
        return 0.0
    return len(missing_row_identities(old, new)) / len(before)


async def merge_page_content(llm, existing_content: str, new_content: str, slug: str) -> str:
    existing = existing_content or ""
    incoming = new_content or ""
    if len(existing.strip()) < MIN_EXISTING_CHARS or existing.strip() == incoming.strip():
        return incoming

    try:
        prompt = _MERGE_PROMPT.format(slug=slug, existing=existing, incoming=incoming)
        raw = await asyncio.wait_for(
            llm.generate(prompt, system=MERGE_SYSTEM_PROMPT, temperature=0.1),
            timeout=MERGE_TIMEOUT_S,
        )
    except Exception as e:
        logger.warning(f"merge_page_content[{slug}]: LLM merge failed ({type(e).__name__}: {e}); appending")
        return append_fallback(existing, incoming)

    merged = strip_code_fence(raw or "").strip()
    longest = max(len(existing), len(incoming))
    if len(merged) < BODY_SHRINK_RATIO * longest:
        logger.warning(f"merge_page_content[{slug}]: merged result too short ({len(merged)}/{longest}); appending")
        return append_fallback(existing, incoming)
    if _row_loss_ratio(existing, merged) > MAX_ROW_LOSS:
        logger.warning(f"merge_page_content[{slug}]: merged result drops table rows; appending")
        return append_fallback(existing, incoming)
    return merged
