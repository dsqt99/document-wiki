"""
Document metadata — the "thông tin văn bản" block behind the legal wiki UI.

Every Source (legal or internal regulation) gets a normalized metadata dict
stored at `Source.metadata_["doc"]`:

    doc_type, doc_number, issuing_authority, official_title,
    issued_date, effective_date, expiry_date   (ISO "YYYY-MM-DD" or None)
    field          one of FIELDS
    article_count  number of distinct "Điều"
    doc_slug       slug of the legal overview wiki page (legal sources only)
    method         "regex" | "regex+llm"
    extracted_at   ISO timestamp

Regex (`parse_legal_metadata`) runs first; one low-temperature LLM call fills
what regex cannot see (effective/expiry dates, field) and gaps. The LLM step is
best-effort — any failure keeps the regex result.

Validity ("tình trạng hiệu lực") is *derived at read time* by
`compute_validity`, because it depends on today's date and on relations other
documents create later (a newer doc replacing this one).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LegalRelation, LegalRelationType, LegalUnit, Source

METADATA_KEY = "doc"

# Closed taxonomy for "Lĩnh vực" — keeps facet counts meaningful.
FIELDS = [
    "Chứng khoán",
    "Doanh nghiệp",
    "Thuế - Phí - Lệ phí",
    "Tiền tệ - Ngân hàng",
    "Đầu tư",
    "Tài chính nhà nước",
    "Kế toán - Kiểm toán",
    "Bảo hiểm",
    "Lao động - Tiền lương",
    "Bộ máy hành chính",
    "Vi phạm hành chính",
    "An ninh - Trật tự",
    "Giao thông - Vận tải",
    "Đất đai - Xây dựng",
    "Tài nguyên - Môi trường",
    "Y tế",
    "Giáo dục",
    "Công nghệ thông tin",
    "Thương mại",
    "Dân sự",
    "Hình sự",
    "Khác",
]

VALIDITY_ACTIVE = "con_hieu_luc"
VALIDITY_PENDING = "chua_co_hieu_luc"
VALIDITY_REPLACED = "bi_thay_the"
VALIDITY_EXPIRED = "het_hieu_luc"
VALIDITY_UNKNOWN = "khong_xac_dinh"

_VI_DATE_RE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)
_NUM_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")

_EFFECTIVE_RE = re.compile(
    r"có\s+hiệu\s+lực(?:\s+thi\s+hành)?(?:\s+kể)?\s+từ\s+(ngày\s+(?:ký|ban\s+hành)"
    r"|ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|ngày\s+\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
    re.IGNORECASE,
)
_ARTICLE_NUM_RE = re.compile(r"(?:^|\n)[ \t>#*_“\"]*Điều\s+(\d+[a-z]?)\s*[\.:\-–]", re.IGNORECASE)

LLM_SYSTEM = (
    "Bạn trích xuất thông tin văn bản pháp luật / văn bản nội bộ tiếng Việt. "
    "Chỉ trả về một đối tượng JSON, không giải thích."
)

LLM_PROMPT = """Trích xuất thông tin của văn bản dưới đây.

Thông tin đã nhận diện bằng regex (có thể thiếu hoặc sai):
{regex_meta}

Trả về JSON với đúng các khóa:
{{
  "doc_type": "Luật | Bộ luật | Nghị định | Nghị quyết | Thông tư | Thông tư liên tịch | Quyết định | Văn bản hợp nhất | Chỉ thị | Công văn | Quy chế | Quy định | Khác",
  "doc_number": "số hiệu, ví dụ 2777/QĐ-BTC, hoặc null",
  "issuing_authority": "cơ quan ban hành, ví dụ Bộ Tài chính, hoặc null",
  "official_title": "trích yếu ngắn gọn, hoặc null",
  "issued_date": "YYYY-MM-DD hoặc null",
  "effective_date": "YYYY-MM-DD hoặc null (nếu 'có hiệu lực kể từ ngày ký' thì bằng issued_date)",
  "expiry_date": "YYYY-MM-DD hoặc null (chỉ khi văn bản ghi rõ thời điểm hết hiệu lực)",
  "field": "đúng một giá trị trong: {fields}"
}}

--- PHẦN ĐẦU VĂN BẢN ---
{head}

--- ĐOẠN VỀ HIỆU LỰC THI HÀNH ---
{effect}
"""


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def to_iso_date(value: Any) -> Optional[str]:
    """Normalize 'dd/mm/yyyy', 'ngày d tháng m năm y' or ISO to 'YYYY-MM-DD'."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    for rx, order in ((_ISO_DATE_RE, "ymd"), (_VI_DATE_RE, "dmy"), (_NUM_DATE_RE, "dmy")):
        m = rx.search(s)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def count_articles(full_text: str) -> int:
    return len({n.lower() for n in _ARTICLE_NUM_RE.findall(full_text or "")})


def _effect_excerpt(full_text: str, limit: int = 2500) -> str:
    """Text around the last 'hiệu lực' mention — where effective dates live."""
    idx = full_text.lower().rfind("hiệu lực")
    if idx == -1:
        return full_text[-limit:]
    start = max(0, idx - limit // 2)
    return full_text[start:start + limit]


def regex_effective_date(full_text: str, issued_iso: Optional[str]) -> Optional[str]:
    m = None
    for m in _EFFECTIVE_RE.finditer(full_text or ""):
        pass  # last match: the "Hiệu lực thi hành" article is near the end
    if not m:
        return None
    phrase = m.group(1).lower()
    if "ký" in phrase or "ban hành" in phrase:
        return issued_iso
    return to_iso_date(phrase)


def _clean_str(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v if v and v.lower() not in ("null", "none", "-", "—") else None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

async def _llm_extract(session: AsyncSession, full_text: str, regex_meta: dict) -> dict:
    from app.ai.registry import ProviderRegistry
    from app.utils.text import parse_json_loose

    llm = await ProviderRegistry(session).get_llm()
    shown = {k: regex_meta.get(k) for k in (
        "doc_type", "doc_number", "issuing_authority", "issued_date", "official_title",
    )}
    prompt = LLM_PROMPT.format(
        regex_meta=shown,
        fields=", ".join(FIELDS),
        head=full_text[:5000],
        effect=_effect_excerpt(full_text),
    )
    raw = await llm.generate(prompt=prompt, system=LLM_SYSTEM, max_tokens=600, temperature=0.0)
    result = parse_json_loose(raw)
    return result if isinstance(result, dict) else {}


async def extract_document_metadata(
    session: AsyncSession,
    source: Source,
    *,
    use_llm: bool = True,
    regex_meta: Optional[dict] = None,
) -> dict[str, Any]:
    """Build the normalized metadata dict for `source` (does not persist it)."""
    from app.services.legal_service import parse_legal_metadata

    full_text = source.full_text or ""
    base = regex_meta or parse_legal_metadata(full_text, source.file_name or "")
    issued = to_iso_date(base.get("issued_date"))

    meta: dict[str, Any] = {
        "doc_type": base.get("doc_type"),
        "doc_number": base.get("doc_number"),
        "issuing_authority": base.get("issuing_authority"),
        "official_title": base.get("official_title"),
        "issued_date": issued,
        "effective_date": regex_effective_date(full_text, issued),
        "expiry_date": None,
        "field": None,
        "article_count": count_articles(full_text),
        "method": "regex",
    }

    if use_llm and full_text.strip():
        try:
            llm = await _llm_extract(session, full_text, base)
            # Regex wins for identifiers it found; LLM fills the gaps.
            for key in ("doc_type", "doc_number", "issuing_authority", "official_title"):
                if not meta[key]:
                    meta[key] = _clean_str(llm.get(key))
            for key in ("issued_date", "effective_date", "expiry_date"):
                if not meta[key]:
                    meta[key] = to_iso_date(_clean_str(llm.get(key)))
            field = _clean_str(llm.get("field"))
            meta["field"] = field if field in FIELDS else ("Khác" if field else None)
            meta["method"] = "regex+llm"
        except Exception as e:
            logger.warning(f"doc metadata: LLM step failed for source {source.id}: {e}")

    return meta


async def store_document_metadata(
    session: AsyncSession,
    source: Source,
    *,
    use_llm: bool = True,
    regex_meta: Optional[dict] = None,
    article_count: Optional[int] = None,
    doc_slug: Optional[str] = None,
) -> dict[str, Any]:
    """Extract and write `Source.metadata_["doc"]`. Caller commits."""
    meta = await extract_document_metadata(session, source, use_llm=use_llm, regex_meta=regex_meta)
    prev = (source.metadata_ or {}).get(METADATA_KEY) or {}
    if article_count is not None:
        meta["article_count"] = article_count
    if doc_slug:
        meta["doc_slug"] = doc_slug
    elif prev.get("doc_slug"):
        meta["doc_slug"] = prev["doc_slug"]
    # Values a user corrected by hand survive re-extraction.
    manual = [k for k in prev.get("manual_fields") or [] if k in EDITABLE_META_KEYS]
    for key in manual:
        meta[key] = prev.get(key)
    if manual:
        meta["manual_fields"] = manual
    meta["extracted_at"] = datetime.now(timezone.utc).isoformat()
    # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
    source.metadata_ = {**(source.metadata_ or {}), METADATA_KEY: meta}
    return meta


def get_doc_meta(source: Source) -> dict[str, Any]:
    return dict((source.metadata_ or {}).get(METADATA_KEY) or {})


EDITABLE_META_KEYS = (
    "doc_type", "doc_number", "issuing_authority", "official_title",
    "issued_date", "effective_date", "expiry_date", "field",
)
_META_DATE_KEYS = ("issued_date", "effective_date", "expiry_date")


def apply_manual_doc_meta(source: Source, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge user-edited metadata into `Source.metadata_["doc"]`. Caller commits.

    Empty strings clear a value; dates accept dd/mm/yyyy or ISO. Edited keys are
    remembered in `manual_fields` so a later re-extraction keeps them.
    """
    meta = get_doc_meta(source)
    manual = set(meta.get("manual_fields") or [])
    for key, raw in updates.items():
        if key not in EDITABLE_META_KEYS:
            continue
        value = _clean_str(raw) if raw is not None else None
        if value and key in _META_DATE_KEYS:
            iso = to_iso_date(value)
            if not iso:
                raise ValueError(f"Ngày không hợp lệ cho '{key}': {raw}")
            value = iso
        meta[key] = value
        manual.add(key)
    meta["manual_fields"] = sorted(manual)
    source.metadata_ = {**(source.metadata_ or {}), METADATA_KEY: meta}
    return meta


# ---------------------------------------------------------------------------
# Validity & document-level relations
# ---------------------------------------------------------------------------

def compute_validity(meta: dict, lifecycle: Optional[dict] = None, today: Optional[date] = None) -> str:
    """Derive tình trạng hiệu lực from dates and incoming doc-level relations."""
    today = today or date.today()
    lifecycle = lifecycle or {}
    if lifecycle.get("replaced_by"):
        return VALIDITY_REPLACED
    if lifecycle.get("repealed_by"):
        return VALIDITY_EXPIRED
    expiry = meta.get("expiry_date")
    if expiry and expiry < today.isoformat():
        return VALIDITY_EXPIRED
    effective = meta.get("effective_date") or meta.get("issued_date")
    if not effective:
        return VALIDITY_UNKNOWN
    if effective > today.isoformat():
        return VALIDITY_PENDING
    return VALIDITY_ACTIVE


def _norm_doc_number(n: Optional[str]) -> str:
    return (n or "").strip().upper()


async def load_lifecycle(session: AsyncSession, doc_numbers: list[str]) -> dict[str, dict]:
    """Map doc_number → {"replaced_by": [...], "repealed_by": [...]} (doc numbers).

    One query for any number of documents: doc-level THAY_THE/BAI_BO relations
    (no target article) whose target is one of `doc_numbers`.
    """
    wanted = {_norm_doc_number(n) for n in doc_numbers if n}
    if not wanted:
        return {}
    from sqlalchemy import func

    stmt = (
        select(LegalRelation.relation_type, LegalRelation.target_doc_number, LegalUnit.doc_number)
        .join(LegalUnit, LegalRelation.source_unit_id == LegalUnit.id)
        .where(
            func.upper(LegalRelation.target_doc_number).in_(wanted),
            LegalRelation.target_article_number.is_(None),
            LegalRelation.is_effective.is_(True),
            LegalRelation.relation_type.in_([LegalRelationType.THAY_THE, LegalRelationType.BAI_BO]),
        )
    )
    out: dict[str, dict] = {}
    for rel_type, target, by_doc in (await session.execute(stmt)).all():
        key = "replaced_by" if rel_type == LegalRelationType.THAY_THE else "repealed_by"
        entry = out.setdefault(_norm_doc_number(target), {"replaced_by": [], "repealed_by": []})
        by = by_doc or "?"
        if by not in entry[key]:
            entry[key].append(by)
    return out


def lifecycle_for(lifecycles: dict[str, dict], doc_number: Optional[str]) -> dict:
    return lifecycles.get(_norm_doc_number(doc_number), {}) if doc_number else {}


async def load_doc_relations(
    session: AsyncSession, source_id: uuid.UUID, doc_number: Optional[str]
) -> dict[str, list[dict]]:
    """Outgoing + incoming relations of one document, for the "Lược đồ" tab.

    Returns {"outgoing": [...], "incoming": [...]}; each item:
    {relation_type, doc_number, article, clause, from_article, quote}.
    """
    from sqlalchemy import func

    outgoing_stmt = (
        select(LegalRelation, LegalUnit.unit_number)
        .join(LegalUnit, LegalRelation.source_unit_id == LegalUnit.id)
        .where(LegalUnit.source_id == source_id)
    )
    outgoing = [
        {
            "relation_type": _rel_value(rel.relation_type),
            "doc_number": rel.target_doc_number,
            "article": rel.target_article_number,
            "clause": rel.target_clause_number,
            "from_article": from_art,
            "quote": rel.quote_context,
        }
        for rel, from_art in (await session.execute(outgoing_stmt)).all()
    ]

    incoming: list[dict] = []
    if doc_number:
        incoming_stmt = (
            select(LegalRelation, LegalUnit.doc_number, LegalUnit.unit_number)
            .join(LegalUnit, LegalRelation.source_unit_id == LegalUnit.id)
            .where(
                func.upper(LegalRelation.target_doc_number) == _norm_doc_number(doc_number),
                LegalUnit.source_id != source_id,
            )
        )
        incoming = [
            {
                "relation_type": _rel_value(rel.relation_type),
                "doc_number": by_doc,
                "article": rel.target_article_number,
                "clause": rel.target_clause_number,
                "from_article": from_art,
                "quote": rel.quote_context,
            }
            for rel, by_doc, from_art in (await session.execute(incoming_stmt)).all()
        ]
    return {"outgoing": outgoing, "incoming": incoming}


def _rel_value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


# ---------------------------------------------------------------------------
# Backfill (sources ingested before metadata existed)
# ---------------------------------------------------------------------------

async def reextract_article_relations(session: AsyncSession, source_id: uuid.UUID) -> int:
    """Re-run the relation extractor over a legal source's stored article units.

    Replaces article-derived relations (everything except preamble CAN_CU, whose
    preamble text is not stored) so improved extractor rules apply without a
    full re-ingest. Caller commits.
    """
    from sqlalchemy import delete

    from app.database.models import LegalUnitType
    from app.services.legal_relation_extractor import LegalRelationExtractor

    units = (await session.execute(
        select(LegalUnit).where(
            LegalUnit.source_id == source_id,
            LegalUnit.unit_type == LegalUnitType.ARTICLE,
        )
    )).scalars().all()
    if not units:
        return 0

    await session.execute(
        delete(LegalRelation).where(
            LegalRelation.source_unit_id.in_([u.id for u in units]),
            LegalRelation.relation_type != LegalRelationType.CAN_CU,
        )
    )
    extractor = LegalRelationExtractor()
    count = 0
    for unit in units:
        for rel in extractor.extract_from_text(unit.content or "", default_doc_number=unit.doc_number):
            session.add(LegalRelation(
                id=uuid.uuid4(),
                source_unit_id=unit.id,
                target_doc_number=rel.target_doc_number,
                target_article_number=rel.target_article_number,
                target_clause_number=rel.target_clause_number,
                relation_type=rel.relation_type,
                quote_context=rel.quote_context,
                is_effective=True,
            ))
            count += 1
    return count


async def _find_overview_slug(session: AsyncSession, source_id: uuid.UUID) -> Optional[str]:
    """Slug of the legal overview page: a page of this source not bound to an article unit."""
    from app.database.models import WikiPage

    article_page_ids = select(LegalUnit.wiki_page_id).where(
        LegalUnit.source_id == source_id, LegalUnit.wiki_page_id.is_not(None)
    )
    slugs = (await session.execute(
        select(WikiPage.slug).where(
            WikiPage.source_ids.contains([source_id]),
            WikiPage.id.not_in(article_page_ids),
        )
    )).scalars().all()
    return min(slugs, key=len) if slugs else None


async def backfill_document_metadata(
    session: AsyncSession,
    *,
    only_missing: bool = True,
    use_llm: bool = True,
    limit: int = 1000,
) -> dict[str, int]:
    """Fill `metadata_["doc"]` for ready sources; refresh legal relations."""
    from app.services.legal_service import (
        build_legal_doc_slug,
        is_legal_source,
        parse_legal_metadata,
    )
    from app.services.legal_relation_extractor import relink_legal_relations

    ids = (await session.execute(
        select(Source.id).where(Source.full_text.is_not(None)).order_by(Source.created_at.desc()).limit(limit)
    )).scalars().all()

    done = skipped = failed = relations = 0
    for sid in ids:
        source = await session.get(Source, sid)
        if source is None:
            continue
        if only_missing and get_doc_meta(source).get("extracted_at"):
            skipped += 1
            continue
        try:
            regex_meta = parse_legal_metadata(source.full_text or "", source.file_name or "")
            doc_slug = None
            if await is_legal_source(session, source):
                # Prefer the overview page that ingest actually created: the
                # title-based slug fallback can drift once the title was renamed.
                doc_slug = await _find_overview_slug(session, source.id)
                if not doc_slug:
                    doc_slug = build_legal_doc_slug(
                        source.title or source.file_name or "",
                        doc_number=regex_meta.get("doc_number"),
                        source_id=source.id,
                    )
                relations += await reextract_article_relations(session, source.id)
            await store_document_metadata(
                session, source, use_llm=use_llm, regex_meta=regex_meta, doc_slug=doc_slug,
            )
            await session.commit()
            done += 1
        except Exception as e:
            await session.rollback()
            failed += 1
            logger.warning(f"backfill doc metadata failed for source {sid}: {e}")

    if relations:
        await relink_legal_relations(session)
    return {"updated": done, "skipped": skipped, "failed": failed, "relations": relations}
