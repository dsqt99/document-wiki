"""Exact Route Service — high-priority routing for exact document citations.

Detects queries that cite an official document number (e.g. "13/2023/NĐ-CP",
"123/QĐ-UBND", "số 50/2024") — optionally with an article/clause
("Điều 5 khoản 2", "khoản 2 Điều 5") — and resolves the exact unit from the
structured-unit table, with validity warnings. Applies to any document that
carries an official number, not only legal normative documents.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.vi_tokenizer import DASHES, DOC_NUMBER_RE, strip_accents
from app.database.models import LegalUnit, LegalUnitType
from app.services.legal_service import (
    format_legal_validity_warning_callout,
    get_legal_unit_validity_warnings,
)


@dataclass
class LegalQueryIntent:
    doc_number: Optional[str] = None          # as written (upper-cased)
    doc_number_norm: Optional[str] = None     # normalize_doc_number(doc_number)
    article_number: Optional[str] = None
    clause_number: Optional[str] = None
    is_exact_legal_lookup: bool = False       # article + document both present
    doc_numbers: list[str] = field(default_factory=list)  # every number found (normalized)


RE_DOC_NUMBER = DOC_NUMBER_RE
RE_ARTICLE = re.compile(r"\bdieu\s+(\d+[a-z]?)\b")
RE_CLAUSE = re.compile(r"\bkhoan\s+(\d+)\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    for d in DASHES:
        text = text.replace(d, "-")
    return strip_accents(text).lower()


def normalize_doc_number(doc: str) -> str:
    """Canonical form for comparison: accent-folded (Đ→D), upper, no spaces, plain dashes."""
    return re.sub(r"\s+", "", _fold(doc)).upper()


def find_doc_numbers(query: str) -> list[str]:
    """Every document number in `query`, normalized, in order, de-duplicated."""
    out: list[str] = []
    for m in RE_DOC_NUMBER.finditer(_fold(query)):
        n = normalize_doc_number(m.group(1))
        if n not in out:
            out.append(n)
    return out


def parse_legal_query_intent(query: str) -> Optional[LegalQueryIntent]:
    """Detect a document-number citation, optionally narrowed to an article/clause."""
    if not query or not query.strip():
        return None

    folded = _fold(query)
    docs = find_doc_numbers(query)
    art_m = RE_ARTICLE.search(folded)
    clause_m = RE_CLAUSE.search(folded)

    if not docs:
        return None

    doc = docs[0]
    return LegalQueryIntent(
        doc_number=doc,
        doc_number_norm=doc,
        article_number=art_m.group(1).lower() if art_m else None,
        clause_number=clause_m.group(1) if (clause_m and art_m) else None,
        is_exact_legal_lookup=bool(art_m),
        doc_numbers=docs,
    )


def _norm_doc_sql(col):
    """SQL twin of normalize_doc_number (accents via f_unaccent, upper, no spaces)."""
    return func.upper(func.replace(func.f_unaccent(col), " ", ""))


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def route_exact_legal_query(
    session: AsyncSession,
    query: str,
    allowed_source_ids: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Resolve "Điều X [khoản Y] <số hiệu>" directly from the unit table.

    Matching order on the normalized document number: exact → prefix
    ("13/2023" → "13/2023/ND-CP") → substring. `allowed_source_ids` (None =
    unrestricted) keeps units of out-of-scope sources from leaking.
    """
    intent = parse_legal_query_intent(query)
    if not intent or not intent.is_exact_legal_lookup:
        return None

    doc = intent.doc_number_norm or ""
    pat = _like_escape(doc)
    norm_col = _norm_doc_sql(LegalUnit.doc_number)
    rank = case((norm_col == doc, 0), (norm_col.like(f"{pat}%", escape="\\"), 1), else_=2)

    unit_query = select(LegalUnit).where(
        norm_col.like(f"%{pat}%", escape="\\"),
        LegalUnit.unit_type == LegalUnitType.ARTICLE,
        func.lower(LegalUnit.unit_number) == intent.article_number,
    )
    if allowed_source_ids is not None:
        import uuid as _uuid
        if not allowed_source_ids:
            return None
        unit_query = unit_query.where(
            LegalUnit.source_id.in_([_uuid.UUID(s) for s in allowed_source_ids])
        )
    unit_query = unit_query.order_by(rank, LegalUnit.doc_number).limit(1)
    unit = (await session.execute(unit_query)).scalars().first()
    if not unit:
        return None

    target_unit = unit
    if intent.clause_number:
        clause_query = select(LegalUnit).where(
            LegalUnit.parent_unit_id == unit.id,
            LegalUnit.unit_type == LegalUnitType.CLAUSE,
            LegalUnit.unit_number == intent.clause_number,
        ).limit(1)
        clause_unit = (await session.execute(clause_query)).scalars().first()
        if clause_unit:
            target_unit = clause_unit
        else:
            logger.debug(f"exact route: clause {intent.clause_number} not found under {unit.id}")

    warnings = await get_legal_unit_validity_warnings(session, unit.id)
    warning_callout = format_legal_validity_warning_callout(warnings)

    return {
        "found": True,
        "unit_id": str(target_unit.id),
        "unit_number": target_unit.unit_number,
        "unit_type": target_unit.unit_type.value if hasattr(target_unit.unit_type, "value") else str(target_unit.unit_type),
        "title": target_unit.title or unit.title,
        "full_path": target_unit.full_path,
        "content": target_unit.content,
        "doc_number": target_unit.doc_number or unit.doc_number,
        "warnings": warnings,
        "warning_callout": warning_callout,
        "wiki_page_id": str(unit.wiki_page_id) if unit.wiki_page_id else None,
    }
