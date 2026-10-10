"""
Page merge logic for the MRP pipeline.

When an UPDATE targets a page that already has content from a different source,
the new content is LLM-merged with the existing content rather than overwriting.

Three layers of protection (inspired by LLM Wiki):
  1. Source IDs are always unioned — never lost.
  2. Body merge via LLM — produces a coherent unified page.
  3. Sanity check — reject if merged body is too short (truncation guard) or
     drops table rows present in either input (row identity guard, see
     app/services/wiki_write_guard.py).

Fallback: any LLM failure or sanity-check rejection KEEPS the existing page and
appends the incoming content under a separator section (append_fallback).
Previously the fallback returned the incoming content alone, which silently
discarded everything the existing page held from earlier sources. Appending is
the safest choice: nothing from either version is lost, and the duplication can
be cleaned up by a later merge or a human edit.
"""

import asyncio
import re

from loguru import logger

from app.ai.providers.base import LLMProvider
from app.services.wiki_write_guard import missing_row_identities, table_row_identities

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# If the LLM's merged body is shorter than this fraction of the longest input,
# reject the merge — the LLM almost certainly stripped content.
BODY_SHRINK_THRESHOLD = 0.7

MERGE_TIMEOUT = 120  # seconds

# A merge may drop at most this share of the distinct table row identities
# found in the two inputs (de-duplicating rows is allowed, losing them is not).
MERGE_MAX_ROW_LOSS = 0.2

# Heading of the section the fallback appends incoming content under.
APPEND_FALLBACK_HEADING = "## Bổ sung từ nguồn mới"

_LEADING_H1_RE = re.compile(r"\A\s*#\s+[^\n]*\n+")


def append_fallback(existing_content: str, new_content: str) -> str:
    """Keep the existing page and append incoming content under a separator section.

    The incoming page's leading H1 title is dropped (the existing page already
    has one) so the result keeps a single H1.
    """
    incoming = _LEADING_H1_RE.sub("", new_content.strip(), count=1).strip()
    if not incoming:
        return existing_content
    return (
        f"{existing_content.rstrip()}\n\n---\n\n"
        f"{APPEND_FALLBACK_HEADING}\n\n{incoming}\n"
    )

MERGE_SYSTEM = """\
You are a wiki page merger. You receive two versions of the same wiki page:
- EXISTING: the current version in the knowledge base (may contain content from earlier sources)
- INCOMING: a new version generated from a different source document

Your job is to produce a SINGLE unified page that preserves ALL factual content
from BOTH versions. Rules:

1. KEEP all facts, numbers, procedures, names from both versions.
2. REMOVE exact duplicates — if both versions state the same fact, keep it once.
3. ORGANIZE coherently — use clear H2 sections, opening paragraph, See also.
4. PRESERVE [[wikilinks]] from both versions.
5. PRESERVE image markers ![caption](image://<uuid>) from both versions.
6. Write in the SAME LANGUAGE as the existing content.
7. Do NOT summarize or condense — the merged page should be AT LEAST as long
   as the longer of the two inputs.
8. Do NOT add any facts not present in either version.

Return ONLY the merged markdown content, no other text.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def merge_page_content(
    llm: LLMProvider,
    existing_content: str,
    new_content: str,
    slug: str,
) -> str:
    """
    Merge new_content into existing_content using LLM.

    Returns merged content on success. On LLM failure or a rejected merge,
    returns the existing content with new_content appended under a separator
    section (see append_fallback) — the existing page is never discarded.
    """
    # Fast path: if existing is empty or very short, just use new content
    if not existing_content or len(existing_content.strip()) < 50:
        return new_content

    # Fast path: identical content
    if existing_content.strip() == new_content.strip():
        return new_content

    prompt = (
        f"Merge these two versions of wiki page `{slug}`:\n\n"
        f"## EXISTING VERSION\n\n{existing_content}\n\n"
        f"---\n\n"
        f"## INCOMING VERSION\n\n{new_content}\n\n"
        f"---\n\n"
        f"Produce the merged page now. Return ONLY the markdown content."
    )

    try:
        raw = await asyncio.wait_for(
            llm.generate(prompt, system=MERGE_SYSTEM, temperature=0.1),
            timeout=MERGE_TIMEOUT,
        )
        merged = raw.strip()

        # Sanity check: merged body must not be too short
        max_input_len = max(len(existing_content), len(new_content))
        min_acceptable = int(max_input_len * BODY_SHRINK_THRESHOLD)

        if len(merged) < min_acceptable:
            logger.warning(
                f"MRP MERGE rejected for '{slug}': merged={len(merged)} chars, "
                f"threshold={min_acceptable} (max input={max_input_len}). "
                f"Keeping existing page + appending new content."
            )
            return append_fallback(existing_content, new_content)

        # Row identity guard: the merge must keep the table rows of BOTH inputs.
        input_ids = table_row_identities(existing_content) | table_row_identities(new_content)
        if input_ids:
            missing = missing_row_identities(
                f"{existing_content}\n\n{new_content}", merged,
            )
            if missing and len(missing) / len(input_ids) > MERGE_MAX_ROW_LOSS:
                logger.warning(
                    f"MRP MERGE rejected for '{slug}': dropped {len(missing)} of "
                    f"{len(input_ids)} table row identities (e.g. {sorted(missing)[:5]}). "
                    f"Keeping existing page + appending new content."
                )
                return append_fallback(existing_content, new_content)

        logger.info(
            f"MRP MERGE success for '{slug}': "
            f"existing={len(existing_content)}, new={len(new_content)}, "
            f"merged={len(merged)} chars"
        )
        return merged

    except Exception as exc:
        logger.warning(
            f"MRP MERGE failed for '{slug}': {exc}. Keeping existing page + appending new content."
        )
        return append_fallback(existing_content, new_content)
