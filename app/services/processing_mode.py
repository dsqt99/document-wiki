"""Unified processing: LLM Wiki + source embeddings, with legal article extraction.

Legacy request values remain parseable for older clients but never disable a
pipeline branch. Personal visibility changes access only, not processing.
"""

from __future__ import annotations

from typing import Any, NamedTuple, Optional

MODES = ("auto", "articles", "verbatim_page", "verbatim")
KEY = "processing_mode"
# Wiki attempt for which the article pages were already built (``auto`` on legal sources),
# so the LLM leg of the same attempt does not parse them again.
ARTICLES_ATTEMPT_KEY = "legal_articles_attempt"


class Plan(NamedTuple):
    articles: bool
    llm: bool
    verbatim_page: bool


def normalize(value: Any) -> Optional[str]:
    """Return a known mode, ``None`` for empty input; raise ``ValueError`` otherwise."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text not in MODES:
        raise ValueError(f"processing_mode must be one of {', '.join(MODES)}")
    return text


def _meta(source) -> dict:
    md = getattr(source, "metadata_", None)
    return md if isinstance(md, dict) else {}


def mode_of(source) -> str:
    return "auto"


def set_mode(source, mode: str) -> None:
    source.metadata_ = {**_meta(source), KEY: "auto"}
    source.preserve_verbatim = False


def mark_articles_done(source) -> None:
    attempt = getattr(source, "wiki_attempt_id", None)
    source.metadata_ = {**_meta(source), ARTICLES_ATTEMPT_KEY: str(attempt) if attempt else None}


def articles_done(source, attempt_id_str: Optional[str]) -> bool:
    done = _meta(source).get(ARTICLES_ATTEMPT_KEY)
    return bool(done) and bool(attempt_id_str) and done == str(attempt_id_str)


async def plan_for(session, source) -> Plan:
    from app.services import legal_service

    is_legal = await legal_service.is_legal_source(session, source)
    return Plan(bool(is_legal), True, False)
