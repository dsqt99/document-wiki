"""VERIFY phase: coverage, contradictions, maturity status and citations (05a §5.6)."""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from loguru import logger

from app.services.wiki_write_guard import is_failure_stub
from app.utils.text import parse_json_loose, strip_code_fence

CONFLICT_SIM = 0.80
CONFLICT_TOP_K = 3
CONFLICT_TEXT_CHARS = 1500
CONFLICT_EMBED_CHARS = 3000
CONFLICT_TIMEOUT_S = 60
COVERAGE_MIN_MENTIONS = 3

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

_RESERVED = {"_index", "_log", "_hot"}


def assess_page_status(content_md: str, slug: Optional[str] = None) -> str:
    if slug and slug.startswith("source/"):
        return "evergreen"
    text = content_md or ""
    n = len(text)
    links = len(_WIKILINK_RE.findall(text))
    if n < 600 or links < 1:
        return "seed"
    if n < 2000 or links < 3:
        return "developing"
    if n < 4000 or links < 5:
        return "mature"
    return "evergreen"


def _contradiction_callout(other_slug: str, other_title: str, description: str) -> str:
    return (
        "> [!contradiction] Có thể mâu thuẫn với trang hiện có\n"
        f"> Nội dung trang này có thể mâu thuẫn với [[{other_slug}|{other_title}]]: {description}\n\n"
    )


async def check_conflicts(session, page_results, llm, embedding_provider) -> int:
    """Prepend a contradiction callout to pages that contradict similar KB pages."""
    from app.services import wiki_service

    if llm is None or embedding_provider is None:
        return 0
    flagged = 0
    for r in page_results:
        slug = r.slug or ""
        if slug in _RESERVED or slug.startswith("source/") or is_failure_stub(r.content_md):
            continue
        try:
            vec = await embedding_provider.embed(
                f"{r.title}\n{r.summary}\n{(r.content_md or '')[:CONFLICT_EMBED_CHARS]}"
            )
            hits = await wiki_service.search_pages_semantic(session, vec, top_k=CONFLICT_TOP_K)
        except Exception as e:
            logger.debug(f"verify[{slug}]: conflict search failed: {e}")
            continue
        for page, score in hits or []:
            if score < CONFLICT_SIM or page.slug == slug:
                continue
            prompt = (
                "Do these two wiki texts contradict each other on any fact? Return only JSON "
                '{"contradicts": true|false, "description": "short explanation in Vietnamese"}.\n\n'
                f"=== TEXT A ({slug}) ===\n{(r.content_md or '')[:CONFLICT_TEXT_CHARS]}\n\n"
                f"=== TEXT B ({page.slug}) ===\n{(page.content_md or '')[:CONFLICT_TEXT_CHARS]}"
            )
            try:
                raw = await asyncio.wait_for(llm.generate(prompt, temperature=0.0), timeout=CONFLICT_TIMEOUT_S)
                data = parse_json_loose(strip_code_fence(raw or ""))
            except Exception as e:
                logger.debug(f"verify[{slug}]: conflict check failed: {e}")
                continue
            if isinstance(data, dict) and data.get("contradicts"):
                r.content_md = _contradiction_callout(
                    page.slug, page.title or page.slug, str(data.get("description") or "")
                ) + (r.content_md or "")
                flagged += 1
                break
    return flagged


def _concept_names(chunk_extracts) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in chunk_extracts or []:
        data = row.get("extract_json") if isinstance(row, dict) else getattr(row, "extract_json", None)
        for c in (data or {}).get("concepts") or []:
            term = (c.get("term") or "").strip() if isinstance(c, dict) else ""
            if term:
                counts[term] = counts.get(term, 0) + 1
    return counts


async def run_verify_phase(session, source, page_results, chunk_extracts, full_text, llm,
                           embedding_provider, tracker):
    from app.services.citation_verifier import CitationVerifier, apply_citation_callout

    async def _progress(p, msg):
        if tracker is not None:
            try:
                await tracker.update(p, msg)
            except Exception:
                pass

    await _progress(88, "Checking coverage...")
    all_text = "\n".join((r.content_md or "").lower() for r in page_results)
    uncovered = [t for t, n in _concept_names(chunk_extracts).items()
                 if n >= COVERAGE_MIN_MENTIONS and t.lower() not in all_text]
    if uncovered:
        logger.info(f"verify[{getattr(source, 'id', '')}]: concepts not covered by any page: {uncovered[:20]}")

    await _progress(91, "Checking contradictions...")
    try:
        await check_conflicts(session, page_results, llm, embedding_provider)
    except Exception as e:
        logger.warning(f"verify: conflict check failed: {e}")

    for r in page_results:
        if is_failure_stub(r.content_md):
            continue
        r.status = assess_page_status(r.content_md, r.slug)  # type: ignore[attr-defined]

    await _progress(95, "Verifying citations...")
    verifier = CitationVerifier()
    for r in page_results:
        if is_failure_stub(r.content_md):
            continue
        try:
            report = verifier.verify_page(r.slug, r.content_md, full_text or "")
            if report.has_hallucinations:
                r.content_md = apply_citation_callout(r.content_md, report)
        except Exception as e:
            logger.debug(f"verify[{r.slug}]: citation check failed: {e}")
    return page_results
