"""Legal Exact Route Service — High-priority routing for exact legal citations.

Detects user queries that explicitly target an Article, Clause, and Document
(e.g., "Điều 5 Nghị định 136/2020", "Khoản 2 Điều 15 Luật Phòng cháy và chữa cháy"),
and retrieves the exact LegalUnit directly from the database with legal validity warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LegalUnit, LegalUnitType
from app.services.legal_service import (
    get_legal_unit_validity_warnings,
    format_legal_validity_warning_callout,
)


@dataclass
class LegalQueryIntent:
    doc_number: Optional[str] = None
    article_number: Optional[str] = None
    clause_number: Optional[str] = None
    is_exact_legal_lookup: bool = False


RE_ARTICLE_LOOKUP = re.compile(
    r"(?:khoản\s+(\d+)\s+)?(?:điều\s+(\d+[a-z]?))",
    re.IGNORECASE,
)

RE_DOC_NUMBER = re.compile(
    r"\b(\d+/\d{4}(?:/[a-zđ0-9\-]+)?)\b",
    re.IGNORECASE,
)

RE_DOC_KEYWORD = re.compile(
    r"(?:nghị\s+định|thông\s+tư|quyết\s+định|luật)\s+(?:số\s+)?(\d+/\d{4}(?:/[a-zđ0-9\-]+)?)",
    re.IGNORECASE,
)


def parse_legal_query_intent(query: str) -> Optional[LegalQueryIntent]:
    """Inspect query to determine if it is an exact legal lookup (Article + Document)."""
    if not query or not query.strip():
        return None

    art_m = RE_ARTICLE_LOOKUP.search(query)
    doc_m = RE_DOC_KEYWORD.search(query) or RE_DOC_NUMBER.search(query)

    if art_m and doc_m:
        clause_num = art_m.group(1)
        art_num = art_m.group(2).lower()
        doc_num = doc_m.group(1).upper()

        return LegalQueryIntent(
            doc_number=doc_num,
            article_number=art_num,
            clause_number=clause_num,
            is_exact_legal_lookup=True,
        )

    return None


async def route_exact_legal_query(
    session: AsyncSession,
    query: str,
) -> Optional[dict[str, Any]]:
    """Directly query LegalUnit table when an exact legal lookup intent is detected."""
    intent = parse_legal_query_intent(query)
    if not intent or not intent.is_exact_legal_lookup:
        return None

    # Search for matching LegalUnit
    unit_query = select(LegalUnit).where(
        LegalUnit.doc_number.ilike(f"%{intent.doc_number}%"),
        LegalUnit.unit_type == LegalUnitType.ARTICLE,
        LegalUnit.unit_number.ilike(intent.article_number),
    )
    res = await session.execute(unit_query)
    unit = res.scalar_one_or_none()

    if not unit:
        return None

    # If clause is specified, attempt to resolve child clause
    target_unit = unit
    if intent.clause_number:
        clause_query = select(LegalUnit).where(
            LegalUnit.parent_unit_id == unit.id,
            LegalUnit.unit_type == LegalUnitType.CLAUSE,
            LegalUnit.unit_number == intent.clause_number,
        )
        clause_res = await session.execute(clause_query)
        clause_unit = clause_res.scalar_one_or_none()
        if clause_unit:
            target_unit = clause_unit

    # Check legal validity warnings
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
