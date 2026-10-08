"""Legal Relation Extractor — Automatic extraction and resolution of legal relationships.

Detects and extracts:
- Amendment (sua_doi, bo_sung): "Sửa đổi, bổ sung Điều X của Nghị định Y..."
- Repeal (bai_bo): "Bãi bỏ khoản X Điều Y của Nghị định Y..."
- Replacement (thay_the): "thay thế Điều X của Nghị định Y..."
- Legal basis (can_cu): "Căn cứ Luật X số Y..."
- Reference citation (dan_chieu): "theo quy định tại Điều X Nghị định Y..."
- Guidance (huong_dan): "Quy định chi tiết / hướng dẫn thi hành Điều X của Luật Y..."

Provides graph relinking utilities to connect relations to existing LegalUnit entities in the database.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LegalRelation, LegalRelationType, LegalUnit, LegalUnitType


@dataclass
class ExtractedRelation:
    relation_type: LegalRelationType
    target_doc_number: Optional[str] = None
    target_article_number: Optional[str] = None
    target_clause_number: Optional[str] = None
    quote_context: Optional[str] = None


# Regex patterns for Vietnamese document numbers and legal structures
RE_DOC_NUMBER = re.compile(
    r"\b(\d+/\d{4}/(?:NĐ\-CP|TT\-BCA|TT\-BTC|TT\-BTP|TT\-BXD|QĐ\-TTg|QH\d+|UBTVQH\d+|QĐ\-BCA|TTLT|NQ\-CP|CT\-TTg))\b",
    re.IGNORECASE,
)

RE_LAW_NUMBER = re.compile(
    r"(?:Luật|Bộ luật)[^;\n\.,]+?số\s+(\d+/\d{4}/QH\d+)",
    re.IGNORECASE,
)

# Amendment & Supplement patterns
RE_SUA_DOI = re.compile(
    r"(?:sửa\s+đổi(?:,\s*bổ\s+sung)?)\s+Điều\s+(\d+[a-z]?)(?:\s+(?:của|tại)\s+([^;\n\.]+))?",
    re.IGNORECASE,
)

RE_BO_SUNG = re.compile(
    r"(?:bổ\s+sung)\s+Điều\s+(\d+[a-z]?)(?:\s+(?:vào|của|tại)\s+([^;\n\.]+))?",
    re.IGNORECASE,
)

# Repeal patterns
RE_BAI_BO_CLAUSE = re.compile(
    r"bãi\s+bỏ\s+(?:điểm\s+([a-zđ])\s+)?(?:khoản\s+(\d+)\s+)?Điều\s+(\d+[a-z]?)(?:\s+(?:của|tại)\s+([^;\n\.]+))?",
    re.IGNORECASE,
)

# Reference / Citation patterns
RE_DAN_CHIEU = re.compile(
    r"(?:theo\s+quy\s+định\s+tại|quy\s+định\s+tại|hướng\s+dẫn\s+tại)\s+(?:khoản\s+(\d+)\s+)?Điều\s+(\d+[a-z]?)(?:\s+(?:của|tại)?\s*(?:Nghị\s+định|Thông\s+tư|Luật|Quyết\s+định)?\s*(?:số)?\s*([0-9a-z\/\-_]+))?",
    re.IGNORECASE,
)


class LegalRelationExtractor:
    """Extracts explicit and implicit legal relationships from Vietnamese legal texts."""

    def extract_from_text(
        self,
        text: str,
        default_doc_number: Optional[str] = None,
    ) -> List[ExtractedRelation]:
        """Extract all legal relationships found within the text lines."""
        relations: List[ExtractedRelation] = []
        if not text or not text.strip():
            return relations

        lines = text.split("\n")

        # Global doc numbers found in the text for fallback resolution
        text_doc_numbers = RE_DOC_NUMBER.findall(text)
        fallback_target_doc = None
        for dn in text_doc_numbers:
            if not default_doc_number or dn.upper() != default_doc_number.upper():
                fallback_target_doc = dn.upper()
                break

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # 1. Check for Sửa đổi / Bổ sung
            for m in RE_SUA_DOI.finditer(line_str):
                art_num = m.group(1).lower()
                context = m.group(2) or ""
                doc_m = RE_DOC_NUMBER.search(context)
                target_doc = doc_m.group(1).upper() if doc_m else fallback_target_doc

                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.SUA_DOI,
                        target_doc_number=target_doc,
                        target_article_number=art_num,
                        quote_context=line_str[:250],
                    )
                )

            # Check pure Bổ sung (when not combined with sửa đổi)
            if "sửa đổi" not in line_str.lower():
                for m in RE_BO_SUNG.finditer(line_str):
                    art_num = m.group(1).lower()
                    context = m.group(2) or ""
                    doc_m = RE_DOC_NUMBER.search(context)
                    target_doc = doc_m.group(1).upper() if doc_m else fallback_target_doc

                    relations.append(
                        ExtractedRelation(
                            relation_type=LegalRelationType.BO_SUNG,
                            target_doc_number=target_doc,
                            target_article_number=art_num,
                            quote_context=line_str[:250],
                        )
                    )

            # 2. Check for Bãi bỏ
            for m in RE_BAI_BO_CLAUSE.finditer(line_str):
                point_num = m.group(1)
                clause_num = m.group(2)
                art_num = m.group(3).lower() if m.group(3) else None
                context = m.group(4) or ""
                doc_m = RE_DOC_NUMBER.search(context)
                target_doc = doc_m.group(1).upper() if doc_m else fallback_target_doc

                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.BAI_BO,
                        target_doc_number=target_doc,
                        target_article_number=art_num,
                        target_clause_number=clause_num,
                        quote_context=line_str[:250],
                    )
                )

            # 3. Check for Dẫn chiếu (Citation / Reference)
            for m in RE_DAN_CHIEU.finditer(line_str):
                clause_num = m.group(1)
                art_num = m.group(2).lower() if m.group(2) else None
                doc_ref_raw = m.group(3) or ""
                doc_m = RE_DOC_NUMBER.search(doc_ref_raw) or RE_DOC_NUMBER.search(line_str)
                target_doc = doc_m.group(1).upper() if doc_m else None

                # Only register reference if target doc is distinct or explicit
                if target_doc and (not default_doc_number or target_doc != default_doc_number.upper()):
                    # Avoid duplicate if already matched as amendment/repeal
                    if not any(
                        r.target_article_number == art_num and r.target_doc_number == target_doc
                        for r in relations
                    ):
                        relations.append(
                            ExtractedRelation(
                                relation_type=LegalRelationType.DAN_CHIEU,
                                target_doc_number=target_doc,
                                target_article_number=art_num,
                                target_clause_number=clause_num,
                                quote_context=line_str[:250],
                            )
                        )

        return relations

    def extract_preamble_basis(self, preamble_text: str) -> List[ExtractedRelation]:
        """Extract legal basis (Căn cứ) from preamble lines."""
        relations: List[ExtractedRelation] = []
        if not preamble_text:
            return relations

        for line in preamble_text.splitlines():
            line_s = line.strip()
            if not line_s.lower().startswith("căn cứ"):
                continue

            doc_numbers = RE_DOC_NUMBER.findall(line_s)
            law_numbers = RE_LAW_NUMBER.findall(line_s)
            all_doc_numbers = list(set([dn.upper() for dn in (doc_numbers + law_numbers)]))

            for dn in all_doc_numbers:
                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.CAN_CU,
                        target_doc_number=dn,
                        quote_context=line_s[:250],
                    )
                )

        return relations


async def relink_legal_relations(
    session: AsyncSession,
    source_id: Optional[uuid.UUID] = None,
) -> dict[str, int]:
    """Relink unlinked LegalRelation records to their corresponding LegalUnit targets.

    Searches for LegalUnit matching (target_doc_number, unit_type='article', unit_number=target_article_number).
    If target_clause_number is present, attempts to link to the specific clause unit if available.
    """
    query = select(LegalRelation).where(
        LegalRelation.target_unit_id.is_(None),
        LegalRelation.target_doc_number.is_not(None),
        LegalRelation.target_article_number.is_not(None),
    )
    if source_id:
        # Filter relations originating from this source's units
        query = query.join(LegalUnit, LegalRelation.source_unit_id == LegalUnit.id).where(
            LegalUnit.source_id == source_id
        )

    res = await session.execute(query)
    unlinked_relations = res.scalars().all()

    linked_count = 0
    unresolved_count = 0

    for rel in unlinked_relations:
        target_doc = rel.target_doc_number
        target_art = (rel.target_article_number or "").lower()

        # Find candidate article unit
        target_unit_query = select(LegalUnit).where(
            LegalUnit.doc_number.ilike(target_doc),
            LegalUnit.unit_type == LegalUnitType.ARTICLE,
            LegalUnit.unit_number.ilike(target_art),
        )
        unit_res = await session.execute(target_unit_query)
        target_unit = unit_res.scalar_one_or_none()

        if target_unit:
            # If target clause is specified, see if child clause unit exists
            if rel.target_clause_number:
                clause_query = select(LegalUnit).where(
                    LegalUnit.parent_unit_id == target_unit.id,
                    LegalUnit.unit_type == LegalUnitType.CLAUSE,
                    LegalUnit.unit_number == rel.target_clause_number,
                )
                clause_res = await session.execute(clause_query)
                clause_unit = clause_res.scalar_one_or_none()
                if clause_unit:
                    target_unit = clause_unit

            rel.target_unit_id = target_unit.id
            linked_count += 1
        else:
            unresolved_count += 1

    if linked_count > 0:
        await session.commit()
        logger.info(f"Relinked {linked_count} legal relations to target legal units.")

    return {"linked_count": linked_count, "unresolved_count": unresolved_count}
