"""VERIFY phase: coverage, contradictions, maturity status and citations (05a §5.6)."""

from __future__ import annotations

import asyncio
import re
import unicodedata
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


def factual_publication_blockers(content_md: str, source_text: str) -> list[str]:
    """Block objectively broken evidence; lexical similarity and maturity stay advisory."""
    from app.services.citation_verifier import extract_footnotes

    blockers = []
    if not (source_text or "").strip():
        blockers.append("empty_source")
    if not (content_md or "").strip():
        blockers.append("empty_page")
    factual_text = re.sub(r"```.*?```", "", content_md or "", flags=re.DOTALL)
    definitions = {fn["id"]: fn["text"] for fn in extract_footnotes(factual_text)}
    body = re.sub(r"^\s*\[\^[\w-]+\]:.*$", "", factual_text, flags=re.MULTILINE)
    references = set(re.findall(r"\[\^([\w-]+)\]", body))
    if references - definitions.keys():
        blockers.append("undefined_footnote")
    if any(not definitions[key].strip() for key in references & definitions.keys()):
        blockers.append("empty_footnote")
    # Compare canonical identifiers, not fuzzy claim scores. Related-page
    # links and advisory callouts may legitimately refer to other documents.
    factual_text = re.sub(r"\[\[.*?\]\]", "", factual_text)
    factual_text = re.sub(r"^\s*>.*$", "", factual_text, flags=re.MULTILINE)

    def identifiers(text):
        canonical = unicodedata.normalize("NFKC", text).casefold()
        canonical = canonical.translate(str.maketrans({ch: "-" for ch in "‐‑‒–—−"}))
        canonical = re.sub(r"[ \t]*([/-])[ \t]*", r"\1", canonical)
        articles = set(re.findall(r"\bđiều\s*(\d+[a-z]?)\b", canonical))
        # A legal instrument identifier has an alphabetic authority suffix;
        # fractions (1/2), dates and numeric ratios are not document citations.
        documents = set(re.findall(r"(?<!\w)\d+(?:/\d{4})?/[a-zđ][a-z0-9đ/-]*", canonical))
        return articles, documents

    claimed_articles, claimed_docs = identifiers(factual_text)
    source_articles, source_docs = identifiers(source_text or "")
    if claimed_articles - source_articles or claimed_docs - source_docs:
        blockers.append("missing_source_reference")
    return blockers


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
        r.publication_blockers = factual_publication_blockers(r.content_md, full_text or "")
        try:
            report = verifier.verify_page(r.slug, r.content_md, full_text or "")
            if report.has_hallucinations:
                r.content_md = apply_citation_callout(r.content_md, report)
        except Exception as e:
            logger.debug(f"verify[{r.slug}]: citation check failed: {e}")
    return page_results
