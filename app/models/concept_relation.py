"""Concept Relation model and extraction utilities with closed predicates."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models import Base


class ConceptPredicate(str, PyEnum):
    """Closed predicates for concept relations in knowledge graph."""
    LA_MOT = "la_mot"           # is-a (loại/dạng)
    THUOC = "thuoc"             # part-of (thành phần/thuộc về)
    QUY_DINH = "quy_dinh"       # regulates (quy định/điều chỉnh)
    AP_DUNG_CHO = "ap_dung_cho" # applies-to (áp dụng cho đối tượng/chủ thể)
    LIEN_QUAN = "lien_quan"     # relates-to (quan hệ liên quan chung)


PREDICATE_MAP: Dict[str, str] = {
    # la_mot
    "la_mot": "la_mot",
    "is_a": "la_mot",
    "is-a": "la_mot",
    "isa": "la_mot",
    "la": "la_mot",
    # thuoc
    "thuoc": "thuoc",
    "part_of": "thuoc",
    "part-of": "thuoc",
    "partof": "thuoc",
    "owns": "thuoc",
    "contains": "thuoc",
    # quy_dinh
    "quy_dinh": "quy_dinh",
    "regulates": "quy_dinh",
    "governs": "quy_dinh",
    "rules": "quy_dinh",
    # ap_dung_cho
    "ap_dung_cho": "ap_dung_cho",
    "applies_to": "ap_dung_cho",
    "applies-to": "ap_dung_cho",
    "targets": "ap_dung_cho",
    # lien_quan
    "lien_quan": "lien_quan",
    "relates_to": "lien_quan",
    "relates-to": "lien_quan",
    "related": "lien_quan",
    "uses": "lien_quan",
    "caused_by": "lien_quan",
    "located_in": "lien_quan",
    "other": "lien_quan",
}


def normalize_predicate(pred: Optional[str]) -> str:
    """Normalize any predicate string into the closed predicate set."""
    if not pred:
        return ConceptPredicate.LIEN_QUAN.value
    cleaned = pred.lower().strip().replace(" ", "_")
    return PREDICATE_MAP.get(cleaned, ConceptPredicate.LIEN_QUAN.value)


class ConceptRelation(Base):
    """Structured knowledge relation between two concepts in the knowledge graph."""
    __tablename__ = "concept_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_concept: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_concept: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    # Optional references to compiled WikiPage IDs
    source_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    target_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_concept_relations_pair", "source_concept", "target_concept"),
    )


def collect_concept_relations(chunk_extracts: list) -> List[Dict[str, Any]]:
    """Gather relations from all chunk extracts, deduplicate by (from, to, predicate)."""
    merged: Dict[tuple, Dict[str, Any]] = {}

    for row in chunk_extracts:
        extract = getattr(row, "extract_json", None) or {}
        raw_rels = extract.get("relations", [])
        for r in raw_rels:
            src = (r.get("from") or "").strip()
            tgt = (r.get("to") or "").strip()
            if not src or not tgt or src.lower() == tgt.lower():
                continue

            raw_pred = r.get("predicate") or r.get("type")
            pred = normalize_predicate(raw_pred)
            evidence = (r.get("evidence") or "").strip()

            key = (src.lower(), tgt.lower(), pred)
            if key not in merged:
                merged[key] = {
                    "source_concept": src,
                    "target_concept": tgt,
                    "predicate": pred,
                    "evidence": evidence,
                    "weight": 1.0,
                }
            else:
                merged[key]["weight"] += 1.0
                if len(evidence) > len(merged[key].get("evidence") or ""):
                    merged[key]["evidence"] = evidence

    return list(merged.values())


async def persist_concept_relations(
    session,
    source_id: uuid.UUID,
    raw_relations: List[Dict[str, Any]],
) -> List[ConceptRelation]:
    """Persist extracted concept relations to concept_relations table."""
    if not raw_relations:
        return []

    # Clean existing relations for source
    await session.execute(
        delete(ConceptRelation).where(ConceptRelation.source_id == source_id)
    )

    persisted: List[ConceptRelation] = []
    for r in raw_relations:
        rel = ConceptRelation(
            source_id=source_id,
            source_concept=r["source_concept"],
            target_concept=r["target_concept"],
            predicate=r["predicate"],
            evidence=r.get("evidence"),
            weight=r.get("weight", 1.0),
        )
        session.add(rel)
        persisted.append(rel)

    await session.commit()
    logger.info(f"persist_concept_relations: Saved {len(persisted)} relations for source {source_id}")
    return persisted


async def link_concept_relations_to_pages(session, source_id: uuid.UUID) -> int:
    """Link source_page_id and target_page_id on concept_relations by matching wiki page title or slug."""
    from app.database.models import WikiPage

    relations = (
        await session.execute(
            select(ConceptRelation).where(ConceptRelation.source_id == source_id)
        )
    ).scalars().all()

    if not relations:
        return 0

    pages = (
        await session.execute(
            select(WikiPage)
        )
    ).scalars().all()

    page_by_key = {}
    for p in pages:
        if p.title:
            page_by_key[p.title.lower().strip()] = p.id
        if p.slug:
            page_by_key[p.slug.lower().strip()] = p.id

    linked_count = 0
    for rel in relations:
        src_id = page_by_key.get(rel.source_concept.lower().strip())
        tgt_id = page_by_key.get(rel.target_concept.lower().strip())

        changed = False
        if src_id and rel.source_page_id != src_id:
            rel.source_page_id = src_id
            changed = True
        if tgt_id and rel.target_page_id != tgt_id:
            rel.target_page_id = tgt_id
            changed = True

        if changed:
            linked_count += 1

    if linked_count > 0:
        await session.commit()

    logger.info(f"link_concept_relations_to_pages: Linked {linked_count} relations to wiki pages.")
    return linked_count
