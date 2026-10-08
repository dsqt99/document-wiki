"""Synthesizer utilities for markdown generation and lightweight footnote citations."""

from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from app.services.citation_verifier import (
    CitationVerifier,
    PageCitationReport,
    extract_footnotes,
    format_footnote_citations,
    apply_citation_callout,
)


def synthesize_footnotes(
    content_md: str,
    footnotes: List[Dict[str, str]],
) -> str:
    """Format and attach lightweight [^sN] footnote references to wiki page content."""
    return format_footnote_citations(content_md, footnotes)


def verify_and_polish_citations(
    content_md: str,
    source_text: str,
    page_slug: str = "",
    verifier: Optional[CitationVerifier] = None,
) -> Tuple[str, PageCitationReport]:
    """Verify factual claims in wiki markdown and inject citation warnings if unverified."""
    active_verifier = verifier or CitationVerifier()
    report = active_verifier.verify_page(
        page_slug=page_slug,
        content_md=content_md,
        source_text=source_text,
    )

    polished_md = content_md
    if report.has_hallucinations:
        polished_md = apply_citation_callout(content_md, report)

    return polished_md, report
