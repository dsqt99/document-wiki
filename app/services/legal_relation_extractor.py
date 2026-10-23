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
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LegalRelation, LegalRelationType, LegalUnit, LegalUnitType
from app.utils.text import clip_around, clip_text


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

# Generic Vietnamese doc number, with or without year: 2777/QĐ-BTC,
# 31/QĐ-HĐTV, 145/2026/TT-BTC. Case-sensitive suffix keeps prose like
# "1/3 số" or "và/hoặc" from matching.
RE_DOC_NUMBER_ANY = re.compile(
    r"(?<![\w/])(\d+(?:/\d{4})?/[A-ZĐ]{1,8}\d*(?:\-[A-ZĐ]{1,8}\d*){0,3})(?![\w/])"
)

_SEPARATORS = str.maketrans({c: "-" for c in "‐‑‒–—−"} | {"／": "/"})


def normalize_doc_number(value: str) -> str:
    """Canonical exact identifier; never remove meaningful digits or suffixes."""
    return re.sub(r"\s+", "", (value or "").translate(_SEPARATORS)).upper()


def normalized_doc_column(column):
    """SQL equivalent for stored identifiers, portable to PostgreSQL and SQLite."""
    for char in "‐‑‒–—−":
        column = func.replace(column, char, "-")
    column = func.replace(column, "／", "/")
    for char in " \t\r\n\u00a0":
        column = func.replace(column, char, "")
    return func.upper(func.replace(column, "đ", "Đ"))


def find_doc_numbers(text: str) -> list[str]:
    """All doc numbers in `text`, specific pattern first, deduplicated in order."""
    text = re.sub(r"\s*([/-])\s*", r"\1", text.translate(_SEPARATORS))
    seen: dict[str, None] = {}
    for m in RE_DOC_NUMBER.finditer(text):
        seen.setdefault(m.group(1).upper(), None)
    for m in RE_DOC_NUMBER_ANY.finditer(text):
        seen.setdefault(m.group(1).upper(), None)
    return list(seen)

# Whole-document lifecycle: "... thay thế Quyết định số 3453/QĐ-BTC ...",
# "bãi bỏ Thông tư số 12/2020/TT-BTC", "Quyết định số X ... hết hiệu lực".
RE_DOC_REPLACE = re.compile(r"\bthay\s+thế\s+(?!(?:khoản|điểm|Điều)\b)", re.IGNORECASE)
RE_DOC_REPEAL = re.compile(r"\bbãi\s+bỏ\s+(?!(?:khoản|điểm|Điều)\b)", re.IGNORECASE)
RE_DOC_EXPIRE = re.compile(r"\bhết\s+hiệu\s+lực\b", re.IGNORECASE)

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
RE_THAY_THE_CLAUSE = re.compile(RE_BAI_BO_CLAUSE.pattern.replace(r"bãi\s+bỏ", r"thay\s+thế"), re.IGNORECASE)

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
        text_doc_numbers = [dn for dn in find_doc_numbers(text)
                            if dn != normalize_doc_number(default_doc_number or "")]
        fallback_target_doc = text_doc_numbers[0] if len(text_doc_numbers) == 1 else None

        def target_document(context):
            docs = find_doc_numbers(context)
            return docs[0] if len(docs) == 1 else (fallback_target_doc if not docs else None)

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # 1. Check for Sửa đổi / Bổ sung
            for m in RE_SUA_DOI.finditer(line_str):
                art_num = m.group(1).lower()
                context = m.group(2) or ""
                target_doc = target_document(context)

                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.SUA_DOI,
                        target_doc_number=target_doc,
                        target_article_number=art_num,
                        quote_context=clip_around(line_str, m.start(), m.end()),
                    )
                )

            # Check pure Bổ sung (when not combined with sửa đổi)
            if "sửa đổi" not in line_str.lower():
                for m in RE_BO_SUNG.finditer(line_str):
                    art_num = m.group(1).lower()
                    context = m.group(2) or ""
                    target_doc = target_document(context)

                    relations.append(
                        ExtractedRelation(
                            relation_type=LegalRelationType.BO_SUNG,
                            target_doc_number=target_doc,
                            target_article_number=art_num,
                            quote_context=clip_around(line_str, m.start(), m.end()),
                        )
                    )

            # 2. Check for Bãi bỏ
            for m in list(RE_BAI_BO_CLAUSE.finditer(line_str)) + list(RE_THAY_THE_CLAUSE.finditer(line_str)):
                point_num = m.group(1)
                clause_num = m.group(2)
                art_num = m.group(3).lower() if m.group(3) else None
                context = m.group(4) or ""
                target_doc = target_document(context)

                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.THAY_THE if m.re is RE_THAY_THE_CLAUSE else LegalRelationType.BAI_BO,
                        target_doc_number=target_doc,
                        target_article_number=art_num,
                        target_clause_number=clause_num,
                        quote_context=clip_around(line_str, m.start(), m.end()),
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
                                quote_context=clip_around(line_str, m.start(), m.end()),
                            )
                        )

            # 4. Whole-document replacement / repeal / expiry
            relations.extend(self._extract_doc_lifecycle(line_str, default_doc_number))

        return relations

    def _extract_doc_lifecycle(
        self, line: str, default_doc_number: Optional[str]
    ) -> List[ExtractedRelation]:
        """Doc-level THAY_THE / BAI_BO targets named on a single line.

        Only doc numbers that appear *after* the trigger phrase count for
        "thay thế"/"bãi bỏ"; for "hết hiệu lực" the doc named *before* it does
        ("Quyết định số X ... hết hiệu lực"). Article-level repeals are handled
        by RE_BAI_BO_CLAUSE.
        """
        own = normalize_doc_number(default_doc_number or "")
        out: List[ExtractedRelation] = []
        seen: set[tuple[LegalRelationType, str]] = set()

        def add(rel_type: LegalRelationType, doc: str, start: int, end: int) -> None:
            if doc == own or (rel_type, doc) in seen:
                return
            seen.add((rel_type, doc))
            out.append(ExtractedRelation(
                relation_type=rel_type, target_doc_number=doc, quote_context=clip_around(line, start, end),
            ))

        for pattern, rel_type in ((RE_DOC_REPLACE, LegalRelationType.THAY_THE), (RE_DOC_REPEAL, LegalRelationType.BAI_BO)):
            m = pattern.search(line)
            if m:
                tail = line[m.end():m.end() + 160]
                docs = find_doc_numbers(tail)
                if docs:
                    at = tail.upper().find(docs[0])
                    add(rel_type, docs[0], m.start(), m.end() + (at + len(docs[0]) if at >= 0 else len(tail)))

        m = RE_DOC_EXPIRE.search(line)
        if m:
            docs = find_doc_numbers(line[:m.start()])
            if docs:
                at = line[:m.start()].upper().rfind(docs[-1])
                add(LegalRelationType.BAI_BO, docs[-1], at if at >= 0 else m.start(), m.end())
        return out

    def extract_preamble_basis(self, preamble_text: str) -> List[ExtractedRelation]:
        """Extract legal basis (Căn cứ) from preamble lines."""
        relations: List[ExtractedRelation] = []
        if not preamble_text:
            return relations

        for line in preamble_text.splitlines():
            line_s = line.strip()
            if not line_s.lower().startswith("căn cứ"):
                continue

            law_numbers = RE_LAW_NUMBER.findall(line_s)
            all_doc_numbers = list(dict.fromkeys(
                find_doc_numbers(line_s) + [dn.upper() for dn in law_numbers]
            ))

            for dn in all_doc_numbers:
                relations.append(
                    ExtractedRelation(
                        relation_type=LegalRelationType.CAN_CU,
                        target_doc_number=dn,
                        quote_context=clip_text(line_s, 500),
                    )
                )

        return relations


async def relink_legal_relations(
    session: AsyncSession,
    source_id: Optional[uuid.UUID] = None,
    *, limit: Optional[int] = None, after_id: Optional[uuid.UUID] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve exact unique targets, including incoming and whole-document changes.

    Dry-run neither adds roots nor mutates relations. Bounded maintenance callers
    can page by relation UUID; unresolved/ambiguous records remain unresolved.
    """
    query = select(LegalRelation).where(
        LegalRelation.target_unit_id.is_(None),
        LegalRelation.target_doc_number.is_not(None),
    )
    if source_id:
        source_units = select(LegalUnit.id).where(LegalUnit.source_id == source_id)
        source_docs = select(normalized_doc_column(LegalUnit.doc_number)).where(LegalUnit.source_id == source_id)
        query = query.where(or_(LegalRelation.source_unit_id.in_(source_units),
                                normalized_doc_column(LegalRelation.target_doc_number).in_(source_docs)))
    if after_id:
        query = query.where(LegalRelation.id > after_id)
    query = query.order_by(LegalRelation.id)
    if limit is not None:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        query = query.limit(limit)

    res = await session.execute(query)
    unlinked_relations = res.scalars().all()

    linked_count = unresolved_count = ambiguous_count = roots_created = 0
    planned_roots: dict[tuple[uuid.UUID, str], LegalUnit] = {}

    for rel in unlinked_relations:
        target_doc = normalize_doc_number(rel.target_doc_number)
        target_art = (rel.target_article_number or "").lower()
        target_unit_query = select(LegalUnit).where(
            normalized_doc_column(LegalUnit.doc_number) == target_doc,
            LegalUnit.unit_type == (LegalUnitType.ARTICLE if target_art else LegalUnitType.DOCUMENT),
        )
        if target_art:
            target_unit_query = target_unit_query.where(func.lower(LegalUnit.unit_number) == target_art)
        unit_res = await session.execute(target_unit_query.limit(2))
        candidates = list(unit_res.scalars().all())
        if not target_art:
            # Legacy graphs lack roots. Inspect all matching source identities as
            # well as roots, so an existing root cannot mask a duplicate source.
            source_res = await session.execute(select(LegalUnit.source_id).where(
                normalized_doc_column(LegalUnit.doc_number) == target_doc).distinct().limit(2))
            source_ids = list(source_res.scalars().all())
            if len(source_ids) > 1:
                ambiguous_count += 1
                unresolved_count += 1
                continue
            if not candidates and len(source_ids) == 1:
                key = (source_ids[0], target_doc)
                root = planned_roots.get(key)
                if root is None:
                    root = LegalUnit(id=uuid.uuid4(), source_id=source_ids[0],
                                     unit_type=LegalUnitType.DOCUMENT, doc_number=target_doc,
                                     full_path=target_doc, content="")
                    planned_roots[key] = root
                    roots_created += 1
                    if not dry_run:
                        session.add(root)
                        await session.flush()
                candidates = [root]
        if len(candidates) != 1:
            ambiguous_count += int(len(candidates) > 1)
            unresolved_count += 1
            continue
        target_unit = candidates[0]
        if rel.target_clause_number:
            clause_res = await session.execute(select(LegalUnit).where(
                LegalUnit.parent_unit_id == target_unit.id,
                LegalUnit.unit_type == LegalUnitType.CLAUSE,
                LegalUnit.unit_number == rel.target_clause_number).limit(2))
            clauses = list(clause_res.scalars().all())
            if len(clauses) != 1:
                ambiguous_count += int(len(clauses) > 1)
                unresolved_count += 1
                continue
            target_unit = clauses[0]
        if not dry_run:
            rel.target_unit_id = target_unit.id
        linked_count += 1

    if linked_count > 0 and not dry_run:
        await session.commit()
        logger.info(f"Relinked {linked_count} legal relations to target legal units.")

    return {"linked_count": linked_count, "unresolved_count": unresolved_count,
            "ambiguous_count": ambiguous_count, "roots_created": roots_created,
            "scanned_count": len(unlinked_relations), "dry_run": dry_run,
            "next_after_id": str(unlinked_relations[-1].id) if unlinked_relations else None}
