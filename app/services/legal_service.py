"""
Legal Service — Specialized extraction and ingestion for Vietnamese legal documents.

When a Source has KnowledgeType "Luật" (slugs: 'lut', 'luat', or name 'Luật'),
it bypasses the LLM-based MRP pipeline. Instead, it extracts the exact verbatim text
of each "Điều" (Article) into an individual WikiPage, preserving 100% legal accuracy.
Each page is indexed with both page-level and chunk-level vector embeddings
(PostgreSQL pgvector and Milvus).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import KnowledgeType, Source, WikiPage
from app.services import wiki_service
from app.utils.text import clip_text, slugify

# Regex to detect Vietnamese legal articles ("Điều X...").
# Matches markdown bold (**Điều 1**), headers (### Điều 1), quotes, etc.
#   group 1: Full heading, e.g. 'Điều 1. Phạm vi điều chỉnh'
#   group 2: Article number, e.g. '1', '18a', '104'
#   group 3: Article title after punctuation (optional), e.g. 'Phạm vi điều chỉnh'
ARTICLE_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:#{1,6}\s*)?(?:\*{1,3})?(?:“|\"|”)?\s*(Điều\s+(\d+[a-z]?)(?:[\.:\–\-\*]\s*([^\n\r]*)|$))',
    re.IGNORECASE,
)

# Mapping document number suffixes to issuing authorities and document types
AUTHORITY_SUFFIX_MAP = {
    r'NĐ\-CP': ('Nghị định', 'Chính phủ'),
    r'TT\-BCA': ('Thông tư', 'Bộ Công an'),
    r'QĐ\-BCA': ('Quyết định', 'Bộ Công an'),
    r'QĐ\-CA': ('Quyết định', 'Công an'),
    r'TT\-BTC': ('Thông tư', 'Bộ Tài chính'),
    r'TT\-BTP': ('Thông tư', 'Bộ Tư pháp'),
    r'TT\-BXD': ('Thông tư', 'Bộ Xây dựng'),
    r'TTLT': ('Thông tư liên tịch', None),
    r'QH\d+': ('Luật', 'Quốc hội'),
    r'VPQH': ('Văn bản hợp nhất', 'Văn phòng Quốc hội'),
    r'UBTVQH': ('Nghị quyết', 'Ủy ban Thường vụ Quốc hội'),
    r'TTg': ('Quyết định', 'Thủ tướng Chính phủ'),
}

FILENAME_TYPE_MAP = {
    r'nghi[\-_]?dinh': 'Nghị định',
    r'thong[\-_]?tu[\-_]?lien[\-_]?tich': 'Thông tư liên tịch',
    r'thong[\-_]?tu|tt[\-_]': 'Thông tư',
    r'luat': 'Luật',
    r'quyet[\-_]?dinh|qd[\-_]': 'Quyết định',
    r'vbhn|van[\-_]?ban[\-_]?hop[\-_]?nhat': 'Văn bản hợp nhất',
    r'nghi[\-_]?quyet': 'Nghị quyết',
}


def _is_auto_title(source: Source, canonical_name: str) -> bool:
    """True when the source title was never set by a user and may be regenerated.

    Covers empty/filename titles, the title written by a previous run (recorded in
    `metadata_["auto_title"]`), and over-long legacy auto titles without that
    marker (the whole preamble swallowed as trích yếu) that share the canonical
    prefix ("Văn bản hợp nhất số … của …").
    """
    title = (source.title or "").strip()
    if not title or title == source.file_name or title.endswith((".pdf", ".docx")):
        return True
    if title == (source.metadata_ or {}).get("auto_title"):
        return True
    prefix = canonical_name.split(" — ")[0].strip()
    return len(title) > 300 and bool(prefix) and title.startswith(prefix)


def parse_legal_metadata(text: str, file_name: str = "") -> dict[str, Any]:
    """Extract formal legal metadata (doc number, authority, date, doc type, title)

    from Vietnamese legal document preambles or filename fallbacks.
    """
    from app.services.legal_hierarchy_parser import strip_markup

    # Markdown/HTML from PDF extraction ('**LUẬT**', '_Căn cứ ..._') would defeat the header regexes.
    preamble = "\n".join(strip_markup(ln) for ln in text[:4000].splitlines()) if text else ""
    meta: dict[str, Any] = {
        "doc_type": None,
        "doc_number": None,
        "issuing_authority": None,
        "issued_date": None,
        "official_title": None,
        "canonical_name": None,
        "citation": None,
    }

    is_vbhn = bool(
        re.search(r'vbhn|văn[\s\._\-]*bản[\s\._\-]*hợp[\s\._\-]*nhất', file_name + " " + preamble[:500], re.I)
    )
    vbhn_fn_num_m = re.search(
        r'(?:hợp\s*nhất\s*(?:Luật\s+[^\n\d]+)?số|VBHN[_\s\-]*)\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',
        file_name,
        re.I,
    )

    # Strip Official Gazette (CÔNG BÁO) noise which has unrelated issue numbers
    clean_preamble = re.sub(r'CÔNG\s*BÁO[^\n]*\n?', '', preamble, flags=re.IGNORECASE)

    # Check filename first for clear legal code patterns (e.g. 136-2020-ND-CP, 55-2024-QH15)
    clean_fn = file_name
    for ext in (".docx", ".doc", ".pdf", ".txt", ".md"):
        if clean_fn.lower().endswith(ext):
            clean_fn = clean_fn[:-len(ext)]
    clean_fn = re.sub(r'^[0-9]+[\.\-_]\s*', '', clean_fn)
    clean_fn = re.sub(r'[_]+NGUON_CHINH_THUC.*$', '', clean_fn, flags=re.IGNORECASE)

    fn_num_m = re.search(r'(\d+[\-_]\d+[\-_][A-Za-z0-9\-]+)', clean_fn)
    if fn_num_m:
        raw = fn_num_m.group(1).replace("_", "/").replace("-", "/")
        raw = re.sub(r'ND/CP', 'NĐ-CP', raw, flags=re.I)
        raw = re.sub(r'TT/BCA', 'TT-BCA', raw, flags=re.I)
        raw = re.sub(r'TT/BTC', 'TT-BTC', raw, flags=re.I)
        raw = re.sub(r'QH(\d+)', r'QH\1', raw, flags=re.I)
        # Only use if not a VBHN file where the filename code is just the year
        if not is_vbhn:
            meta["doc_number"] = raw

    # 1. Document Number from text if not yet found
    if not meta["doc_number"]:
        # Pattern A: Standard colon or space: Số: 136/2020/NĐ-CP, Luật số: 107/2025/QH15, Số: 02VBHN-VPQH
        num_m = re.search(
            r'(?:Số|Luật số|Nghị định số|Thông tư số|Quyết định số|văn bản hợp nhất số|hợp nhất số)\s*[:\s]\s*([0-9]+[A-Za-z0-9\/\-\_ĐđÀ-ỹ]+)',
            clean_preamble,
            re.IGNORECASE,
        )
        # Pattern B: Law name then number: Luật Xử lý vi phạm hành chính số 15/2012/QH13
        if not num_m:
            num_m = re.search(
                r'(?:Luật|Nghị định|Thông tư|Quyết định|Văn bản hợp nhất)\s+[^\n\r]{1,80}?\s+số\s*[:\s]\s*([0-9]+(?:\/[0-9]{4})?\/[A-Za-z0-9\/\-\_ĐđÀ-ỹ]+)',
                clean_preamble,
                re.IGNORECASE,
            )
        # Pattern C: Annex / schedule header in the first 30,000 characters: *(Kèm theo Nghị định số 136/2020/NĐ-CP
        if not num_m and text:
            num_m = re.search(
                r'(?:Kèm theo\s+)?(Nghị định|Thông tư|Luật|Quyết định)\s+số\s*[:\s\*]*([0-9]+(?:\/[0-9]{4})?\/[A-Za-z0-9\/\-\_ĐđÀ-ỹ]+)',
                text[:30000],
                re.IGNORECASE,
            )
            if num_m:
                meta["doc_number"] = num_m.group(2).strip()
                if not meta["doc_type"]:
                    meta["doc_type"] = num_m.group(1).strip()

        if num_m and not meta["doc_number"]:
            raw_num = num_m.group(1).strip()
            if "VBHN" in raw_num and "/" not in raw_num:
                raw_num = re.sub(r'(\d+)(VBHN)', r'\1/\2', raw_num)
            meta["doc_number"] = raw_num

    # 2. Issued Date (... ngày 18 tháng 6 năm 2026)
    date_m = None
    if meta["doc_number"] and text:
        date_m = re.search(
            re.escape(meta["doc_number"]) + r'[\s\S]{0,120}?ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})',
            text,
            re.IGNORECASE,
        )
    if not date_m:
        date_m = re.search(r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', clean_preamble, re.IGNORECASE)
    if not date_m and text:
        date_m = re.search(r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})', text[:30000], re.IGNORECASE)
    if date_m:
        d, m, y = date_m.groups()
        meta["issued_date"] = f"{int(d):02d}/{int(m):02d}/{y}"

    # 3. Issuing Authority
    auth_patterns = [
        (r'CHÍNH\s+PHỦ', 'Chính phủ'),
        (r'ỦY\s+BAN\s+THƯỜNG\s+VỤ\s+QUỐC\s+HỘI', 'Ủy ban Thường vụ Quốc hội'),
        (r'QUỐC\s+HỘI', 'Quốc hội'),
        (r'VĂN\s+PHÒNG\s+QUỐC\s+HỘI', 'Văn phòng Quốc hội'),
        (r'THỦ\s+TƯỚNG\s+CHÍNH\s+PHỦ', 'Thủ tướng Chính phủ'),
        (r'BỘ\s+CÔNG\s+AN', 'Bộ Công an'),
        (r'BỘ\s+TƯ\s+PHÁP', 'Bộ Tư pháp'),
        (r'BỘ\s+TÀI\s+CHÍNH', 'Bộ Tài chính'),
        (r'BỘ\s+XÂY\s+DỰNG', 'Bộ Xây dựng'),
        (r'BỘ\s+GIAO\s+THÔNG\s+VẬN\s+TẢI', 'Bộ Giao thông vận tải'),
        (r'TÒA\s+ÁN\s+NHÂN\s+DÂN\s+TỐI\s+CAO', 'Tòa án nhân dân tối cao'),
        (r'VIỆN\s+KIỂM\s+SÁT\s+NHÂN\s+DÂN\s+TỐI\s+CAO', 'Viện kiểm sát nhân dân tối cao'),
    ]
    for pattern, canonical_name in auth_patterns:
        auth_m = re.search(r'(?:^|\n)\s*' + pattern + r'(?:[\-\s\n]|$)', preamble[:700], re.IGNORECASE)
        if auth_m:
            meta["issuing_authority"] = canonical_name
            break

    # 4. Document Type & Official Title
    # Header format: LUẬT \n XỬ LÝ VI PHẠM HÀNH CHÍNH
    law_title_m = re.search(r'(?:^|\n)\s*LUẬT\s*\n\s*([A-ZÀ-Ỹ\s,]{4,120})(?:\n|$)', preamble)
    if law_title_m:
        meta["official_title"] = " ".join(law_title_m.group(1).split())
        if not meta["doc_type"]:
            meta["doc_type"] = "Luật"

    type_patterns = [
        (r'THÔNG\s+TƯ\s+LIÊN\s+TỊCH', 'Thông tư liên tịch'),
        (r'THÔNG\s+TƯ', 'Thông tư'),
        (r'NGHỊ\s+ĐỊNH', 'Nghị định'),
        (r'NGHỊ\s+QUYẾT', 'Nghị quyết'),
        (r'QUYẾT\s+ĐỊNH', 'Quyết định'),
        (r'VĂN\s+BẢN\s+HỢP\s+NHẤT', 'Văn bản hợp nhất'),
        (r'PHÁP\s+LỆNH', 'Pháp lệnh'),
        (r'BỘ\s+LUẬT', 'Bộ luật'),
        (r'(?<!Luật\s)LUẬT(?![\s\:\-]+số)', 'Luật'),
        (r'LỆNH', 'Lệnh'),
    ]
    if not meta["doc_type"]:
        for pattern, type_name in type_patterns:
            type_m = re.search(r'(?:^|\n)\s*(?: |\s)*' + pattern + r'(?:\s*|\n|$)', preamble, re.IGNORECASE)
            if type_m:
                meta["doc_type"] = type_name
                if not meta["official_title"]:
                    after_type = preamble[type_m.end():]
                    can_cu_m = re.search(
                        r'(?:^|\n)\s*(?:Căn cứ|Theo đề nghị|Luật\s+[A-ZÀ-Ỹ\s]+số\s+\d+|Để thi hành|Quy định này)',
                        after_type,
                        re.IGNORECASE,
                    )
                    if can_cu_m:
                        raw_title_block = after_type[:can_cu_m.start()].strip()
                    else:
                        raw_title_block = after_type[:250].strip()
                    
                    clean_title = " ".join(raw_title_block.split())
                    if len(clean_title) > 250:
                        clean_title = clean_title[:250].rsplit(" ", 1)[0] + "…"
                    if clean_title:
                        meta["official_title"] = clean_title
                break

    # 5. Filename Fallback
    clean_fn = file_name
    for ext in (".docx", ".doc", ".pdf", ".txt", ".md"):
        if clean_fn.lower().endswith(ext):
            clean_fn = clean_fn[:-len(ext)]
    clean_fn = re.sub(r'^[0-9]+[\.\-_]\s*', '', clean_fn)
    clean_fn = re.sub(r'[_]+NGUON_CHINH_THUC.*$', '', clean_fn, flags=re.IGNORECASE)

    if not meta["doc_number"]:
        fn_num = re.search(r'(\d+[\-_]\d+[\-_][A-Za-z0-9\-]+)', clean_fn)
        if fn_num:
            raw = fn_num.group(1).replace("_", "/").replace("-", "/")
            raw = re.sub(r'ND/CP', 'NĐ-CP', raw, flags=re.I)
            raw = re.sub(r'TT/BCA', 'TT-BCA', raw, flags=re.I)
            raw = re.sub(r'TT/BTC', 'TT-BTC', raw, flags=re.I)
            raw = re.sub(r'QH(\d+)', r'QH\1', raw, flags=re.I)
            meta["doc_number"] = raw

    if not meta["doc_type"]:
        for pat, tname in FILENAME_TYPE_MAP.items():
            if re.search(pat, file_name, re.I):
                meta["doc_type"] = tname
                break

    # 6. Authority & Type refinement from doc_number suffix
    if meta["doc_number"]:
        for suffix, (def_type, def_auth) in AUTHORITY_SUFFIX_MAP.items():
            if re.search(suffix, meta["doc_number"], re.I):
                if not meta["doc_type"] or is_vbhn:
                    meta["doc_type"] = def_type
                if not meta["issuing_authority"] and def_auth:
                    meta["issuing_authority"] = def_auth
                break

    # 7. Fallback official titles from known legal codes or filename
    if not meta["official_title"]:
        if re.search(r'136[-_]2020', file_name + " " + (meta["doc_number"] or "")):
            meta["official_title"] = "Quy định chi tiết một số điều của Luật Phòng cháy và chữa cháy"
        elif re.search(r'50[-_]2024', file_name + " " + (meta["doc_number"] or "")):
            meta["official_title"] = "Sửa đổi, bổ sung một số điều của Nghị định số 136/2020/NĐ-CP (PCCC)"
        elif re.search(r'105[-_]2025', file_name + " " + (meta["doc_number"] or "")):
            meta["official_title"] = "Quy định chi tiết một số điều của Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ"
        elif re.search(r'PCCC|chữa cháy', file_name, re.I):
            meta["official_title"] = "Phòng cháy, chữa cháy và cứu nạn, cứu hộ"
        elif re.search(r'đường sắt', file_name, re.I):
            meta["official_title"] = "Đường sắt"
        elif re.search(r'XLVPHC|vi phạm hành chính', file_name, re.I):
            meta["official_title"] = "Xử lý vi phạm hành chính"
        elif re.search(r'lý lịch tư pháp', file_name, re.I):
            meta["official_title"] = "Lý lịch tư pháp"

    # 8. Construct Canonical Name and Full Citation
    if is_vbhn:
        orig_doc_num = meta["doc_number"]
        orig_doc_type = meta["doc_type"] or "Luật"
        meta["doc_type"] = "Văn bản hợp nhất"
        meta["issuing_authority"] = "Văn phòng Quốc hội"

        vbhn_num_str = ""
        if orig_doc_num and "VBHN" in orig_doc_num:
            vbhn_num_str = orig_doc_num
        elif vbhn_fn_num_m:
            num_clean = vbhn_fn_num_m.group(1).split(".")[0]
            vbhn_num_str = f"{num_clean}/VBHN-VPQH"
            meta["doc_number"] = vbhn_num_str

        c_parts = ["Văn bản hợp nhất"]
        if vbhn_num_str:
            c_parts.append(f"số {vbhn_num_str}")
        if meta["issued_date"] and "VBHN" in (orig_doc_num or ""):
            c_parts.append(f"ngày {meta['issued_date']}")
        c_parts.append(f"của Văn phòng Quốc hội")

        # Vietnamese sentence case: "XỬ LÝ VI PHẠM HÀNH CHÍNH" -> "Xử lý vi phạm hành chính".
        title_display = meta["official_title"].capitalize() if meta.get("official_title") else ""
        if title_display:
            c_parts.append(f"— {orig_doc_type} {title_display}")

        if orig_doc_num and "VBHN" not in orig_doc_num:
            c_parts.append(f"({orig_doc_type} số {orig_doc_num})")

        meta["canonical_name"] = " ".join(c_parts)
    else:
        parts = []
        if meta["doc_type"]:
            parts.append(meta["doc_type"])
        if meta["doc_number"]:
            parts.append(f"số {meta['doc_number']}")
        if meta["issued_date"]:
            parts.append(f"ngày {meta['issued_date']}")
        if meta["issuing_authority"]:
            parts.append(f"của {meta['issuing_authority']}")
        meta["canonical_name"] = " ".join(parts) if parts else clean_fn

    if meta["official_title"]:
        meta["citation"] = f"{meta['canonical_name']} ({meta['official_title']})"
    else:
        meta["citation"] = meta["canonical_name"]

    return meta


import hashlib


def build_legal_doc_slug(
    doc_title: str,
    doc_number: Optional[str] = None,
    source_id: Optional[Any] = None,
) -> str:
    """Build a deterministic, unique slug for a legal document.

    If doc_number is provided (e.g., '136/2020/NĐ-CP'), slugifies the doc_number.
    Otherwise, uses slugify(doc_title)[:40] combined with an 8-char hash of source_id.
    """
    if doc_number:
        clean_num = slugify(doc_number).strip("-")
        if clean_num:
            return clean_num

    base = slugify(doc_title or "van-ban-luat")[:40].rstrip("-") or "van-ban-luat"
    if source_id:
        sid_str = str(source_id).replace("-", "")[:8]
        return f"{base}-{sid_str}"

    h = hashlib.sha256((doc_title or "").encode("utf-8")).hexdigest()[:8]
    return f"{base}-{h}"


ARTICLE_SUMMARY_MAX = 400
ARTICLE_TITLE_MAX = 500  # LegalUnit.title column; long OCR titles exist, the shape rules below decide
# A full stop after a word ("ký. Quyết định ..."), not after a number ("7 . Đấu giá biển số xe").
_SENTENCE_BREAK = re.compile(r"[^\d\s]\.\s+[A-ZÀ-Ỹ]")
# "Quyết định này có hiệu lực ...", "Thông tư này quy định ...": a clause with a predicate, not a title.
_THIS_DOC_PREDICATE = re.compile(
    r"\bnày\s+(?:có|được|quy định|áp dụng|thay thế|bãi bỏ|hướng dẫn|sửa đổi)\b", re.IGNORECASE
)


def is_body_sentence(title: Optional[str]) -> bool:
    """'Điều 2. Quyết định này có hiệu lực ... thay thế:' is an untitled article whose first
    sentence sits on the heading line. Real titles are noun phrases, sometimes long ones
    ("Yêu cầu về phòng cháy và chữa cháy khi lập quy hoạch xây dựng ... theo Luật Quy hoạch")."""
    t = (title or "").strip().strip("*_ ")
    if not t:
        return False
    return (
        len(t) > ARTICLE_TITLE_MAX
        or t.endswith(":")
        or bool(_SENTENCE_BREAK.search(t))
        or bool(_THIS_DOC_PREDICATE.search(t))
    )


def article_summary(art_num: str, title: Optional[str], lead: Optional[str], content_md: str,
                    limit: int = ARTICLE_SUMMARY_MAX) -> str:
    """'Điều N: <tên> — <đoạn đầu>' from the verbatim text, cut at a sentence/word boundary."""
    from app.services.legal_hierarchy_parser import strip_markup

    head = f"Điều {art_num}" + (f": {title}" if title else "")
    parts = [lead] if lead else []
    total = len(lead or "")
    for line in (content_md or "").splitlines():
        if total > limit:
            break
        raw = line.strip()
        if not raw or raw.startswith(">"):
            continue
        s = strip_markup(raw)
        if not s or re.match(r"(?i)^điều\s+\d", s):
            continue
        s = re.sub(r"^[-+•–]\s*", "", s)
        if s:
            parts.append(s)
            total += len(s)
    body = " ".join(parts)
    return clip_text(f"{head} — {body}" if body else head, limit)


def split_legal_text_by_articles(
    full_text: str,
    doc_title: str = "",
    doc_slug: Optional[str] = None,
) -> dict[str, Any]:
    """Parse Vietnamese legal document text into preamble and individual articles.

    Uses LegalHierarchyParser state machine to accurately extract hierarchical structure
    (Part, Chapter, Section, Article, Clause, Point) and avoid false-positive splits
    inside quoted modification blocks.

    Returns:
        dict with:
            - 'preamble': text prior to the first 'Điều' (issuing authority, legal basis, etc.)
            - 'articles': list of dicts with:
                - 'num': article number (e.g. '1', '18a')
                - 'heading': full header line (e.g. 'Điều 1. Phạm vi điều chỉnh')
                - 'title': extracted title string, None when the heading line holds body text
                - 'lead': that body text (the first sentence on the heading line), else None
                - 'content_md': verbatim article text
                - 'slug': unique page slug
                - 'part_num': optional part number (Phần)
                - 'chapter_num': optional chapter number (Chương)
                - 'chapter_title': optional chapter title
                - 'section_num': optional section number (Mục)
                - 'clauses': list of parsed clauses and points
    """
    if not full_text:
        return {"preamble": "", "articles": []}

    if not doc_slug:
        doc_slug = build_legal_doc_slug(doc_title)

    from app.services.legal_hierarchy_parser import LegalHierarchyParser

    parser = LegalHierarchyParser()
    doc_tree = parser.parse(full_text)
    all_articles = doc_tree.get_all_articles()
    if not all_articles:
        return {
            "preamble": full_text.strip(),
            "articles": [],
        }

    preamble = doc_tree.preamble
    articles: list[dict[str, Any]] = []
    seen_slugs: set[str] = {doc_slug}

    for art in all_articles:
        art_num = art.number
        raw_heading = f"Điều {art.number}. {art.title}" if art.title else f"Điều {art.number}"
        lead = art.title if is_body_sentence(art.title) else None
        art_title = None if lead else art.title
        art_content = art.content

        # Build unique slug for this article (dieu-X-doc-slug); the raw heading text keeps slugs stable.
        base_slug = f"dieu-{art_num.lower()}-{doc_slug}"
        art_slug = base_slug
        if art_slug in seen_slugs:
            title_part = slugify(art.title)[:30].rstrip("-")
            if title_part and f"{base_slug}-{title_part}" not in seen_slugs:
                art_slug = f"{base_slug}-{title_part}"
            else:
                counter = 2
                while f"{base_slug}-{counter}" in seen_slugs:
                    counter += 1
                art_slug = f"{base_slug}-{counter}"
        seen_slugs.add(art_slug)

        articles.append({
            "num": art_num,
            "heading": raw_heading,
            "title": art_title,
            "lead": lead,
            "content_md": art_content,
            "slug": art_slug,
            "chapter_num": art.chapter_num,
            "chapter_title": art.chapter_title,
            "section_num": art.section_num,
            "clauses": [
                {
                    "num": c.number,
                    "content_md": c.content,
                    "points": [{"letter": p.letter, "content_md": p.content} for p in c.points],
                }
                for c in art.clauses
            ],
        })

    return {
        "preamble": preamble,
        "articles": articles,
    }


async def is_legal_source(session: AsyncSession, source: Source) -> bool:
    """Check if the source is associated with KnowledgeType 'Luật' / 'Legal'."""
    if not source.knowledge_type_id:
        return False

    kt = await session.get(KnowledgeType, source.knowledge_type_id)
    if not kt:
        return False

    slug = (kt.slug or "").lower().strip()
    name = (kt.name or "").lower().strip()
    return (
        slug in ("lut", "luat", "legal")
        or "luật" in name
        or "luat" in name
        or "legal" in name
        or "pháp lý" in name
    )


async def finalize_legal_source(
    session: AsyncSession, source: Source, tracker: Any, final: bool = True, refresh_metadata: bool = True
) -> dict:
    """Legal path: parse document by articles into WikiPages and compute vector embeddings.

    - Extracts formal legal metadata (doc_number, authority, issued_date, official_title, canonical citation).
    - Extracts preamble and all articles verbatim.
    - Creates/updates an Overview WikiPage with metadata and Table of Contents wikilinks.
    - Creates/updates an individual WikiPage for each Điều with legal citation header.
    - Computes page-level embeddings and section chunk embeddings (synced to Milvus).
    - Updates the scope's Wiki Index and Log.
    - Marks source status as 'ready'.
    """
    await tracker.update(55, "Bóc tách văn bản quy phạm pháp luật theo từng Điều...")

    raw_title = (source.title or source.file_name or f"Văn bản {source.id}").strip()
    for ext in (".docx", ".doc", ".pdf", ".txt", ".md"):
        if raw_title.lower().endswith(ext):
            raw_title = raw_title[: -len(ext)].strip()
            break
    doc_title = raw_title
    full_text = source.full_text or ""

    if not full_text.strip():
        logger.warning(f"finalize_legal_source: Source {source.id} has empty full_text")
        source.wiki_status = "ready"
        source.wiki_progress = 100
        source.wiki_progress_message = "Văn bản trống, không có nội dung để trích xuất"
        from app.services.source_status import update_source_dual_status
        await update_source_dual_status(session, source)
        await session.commit()
        return {"status": "ready", "pages_created": 0}

    # Extract legal metadata
    meta = parse_legal_metadata(full_text, source.file_name or "")
    display_doc_name = meta.get("canonical_name") or doc_title

    if refresh_metadata and _is_auto_title(source, display_doc_name):
        source.title = display_doc_name
        source.metadata_ = {**(source.metadata_ or {}), "auto_title": display_doc_name}
    await session.commit()

    # Build unique, deterministic slug for this document
    doc_number = meta.get("doc_number")
    from app.services.doc_metadata_service import get_doc_meta, store_document_metadata
    if refresh_metadata:
        doc_slug = build_legal_doc_slug(doc_title, doc_number=doc_number, source_id=source.id)
    else:
        # Keep the slug the law UI already shows (same fallback as the legal-docs router): a slug built
        # from doc_number would collide with other files of the same decision (e.g. its appendix).
        doc_slug = (get_doc_meta(source) or {}).get("doc_slug") or f"doc-{source.id.hex[:8]}"

    # Extract articles
    parsed = split_legal_text_by_articles(full_text, doc_title, doc_slug=doc_slug)
    preamble = parsed["preamble"]
    articles = parsed["articles"]

    # Persist document metadata (thông tin văn bản) for the legal wiki UI.
    if refresh_metadata:
        await tracker.update(58, "Đang trích xuất thông tin văn bản (số hiệu, hiệu lực, lĩnh vực)...")
        await store_document_metadata(
            session, source, use_llm=refresh_metadata, regex_meta=meta, article_count=len(articles),
            doc_slug=doc_slug,
        )
        await session.commit()

    wiki_scopes = await wiki_service.resolve_wiki_scopes(session, source)

    # Get knowledge type slug
    kt_slug = "legal"
    if source.knowledge_type_id:
        kt = await session.get(KnowledgeType, source.knowledge_type_id)
        if kt and kt.slug:
            kt_slug = kt.slug

    pages_to_index: list[WikiPage] = []
    total_articles = len(articles)

    async def _human_edited(slug: str, scope_type, scope_id) -> Optional[WikiPage]:
        """A page someone corrected by hand (e.g. OCR fixes) is kept instead of being re-split."""
        page = await wiki_service.get_page_by_slug(session, slug, scope_type=scope_type, scope_id=scope_id)
        if page is not None and await wiki_service.human_edited_page_ids(session, [page.id]):
            logger.info(f"finalize_legal_source: keeping hand-edited page {slug}")
            return page
        return None

    # 1. Create/update Overview WikiPage (Preamble & Table of Contents)
    toc_lines = []
    for art in articles:
        label = f"Điều {art['num']}" + (
            f": {art['title']}" if art['title'] else (f" — {clip_text(art['lead'], 100)}" if art.get("lead") else "")
        )
        toc_lines.append(f"- [[{art['slug']}|{label}]]")
    toc_md = "\n".join(toc_lines)

    overview_content_parts = [f"# {display_doc_name}\n"]
    
    # Metadata info block
    meta_box = []
    if meta.get("doc_number"):
        meta_box.append(f"- **Số hiệu**: {meta['doc_number']}")
    if meta.get("doc_type"):
        meta_box.append(f"- **Loại văn bản**: {meta['doc_type']}")
    if meta.get("issuing_authority"):
        meta_box.append(f"- **Cơ quan ban hành**: {meta['issuing_authority']}")
    if meta.get("issued_date"):
        meta_box.append(f"- **Ngày ban hành**: {meta['issued_date']}")
    if meta.get("official_title"):
        meta_box.append(f"- **Trích yếu nội dung**: {meta['official_title']}")
    if meta_box:
        overview_content_parts.append("### Thông tin văn bản quy phạm pháp luật\n" + "\n".join(meta_box) + "\n")

    if preamble:
        overview_content_parts.append(f"## Căn cứ ban hành & Phần mở đầu\n\n{preamble}")
    if toc_md:
        overview_content_parts.append(f"\n## Danh mục các Điều ({total_articles} Điều)\n\n{toc_md}\n")
    overview_content = "\n\n".join(overview_content_parts).strip() + "\n"

    overview_summary = (
        meta.get("official_title")
        or (clip_text(preamble, 280) if preamble else f"Tổng quan văn bản quy phạm pháp luật {display_doc_name}")
    )

    for scope_type, scope_id in wiki_scopes:
        overview_page = await _human_edited(doc_slug, scope_type, scope_id) or await wiki_service.upsert_page(
            session,
            slug=doc_slug,
            title=f"{display_doc_name} - Tổng quan & Căn cứ ban hành",
            page_type="concept",
            content_md=overview_content,
            summary=overview_summary,
            knowledge_type_slugs=[kt_slug],
            source_ids=[source.id],
            scope_type=scope_type,
            scope_id=scope_id,
            status="mature",
        )
        pages_to_index.append(overview_page)

        art_page_map: dict[str, uuid.UUID] = {}
        # 2. Create/update each Điều as a separate WikiPage (Verbatim content with citation)
        for idx, art in enumerate(articles):
            art_slug = art["slug"]
            art_num = art["num"]
            art_title = art["title"]
            verbatim_content = art["content_md"]

            page_title = (
                f"Điều {art_num}: {art_title} - {display_doc_name}"
                if art_title
                else f"Điều {art_num} - {display_doc_name}"
            )

            citation_lines = [
                f"> **Căn cứ pháp lý**: Điều {art_num} — {display_doc_name}",
            ]
            if meta.get("official_title"):
                citation_lines.append(f"> **Trích yếu**: {meta['official_title']}")
            citation_lines.append(f"> **Toàn văn văn bản**: [[{doc_slug}|{display_doc_name}]]")
            citation_header = "\n".join(citation_lines)

            page_content = f"{citation_header}\n\n{verbatim_content}\n"

            page_summary = article_summary(art_num, art_title, art.get("lead"), verbatim_content)

            art_page = await _human_edited(art_slug, scope_type, scope_id) or await wiki_service.upsert_page(
                session,
                slug=art_slug,
                title=page_title,
                page_type="concept",
                content_md=page_content,
                summary=page_summary,
                knowledge_type_slugs=[kt_slug],
                source_ids=[source.id],
                scope_type=scope_type,
                scope_id=scope_id,
                status="mature",
            )
            art_page_map[art_slug] = art_page.id
            pages_to_index.append(art_page)

    await session.commit()

    # 2.5 Ingest Legal Knowledge Graph (Units & Relations)
    try:
        await tracker.update(68, "Đang bóc tách cây phả hệ pháp luật & trích xuất quan hệ...")
        await ingest_legal_graph(
            session=session,
            source=source,
            articles=articles,
            preamble=preamble,
            doc_number=meta.get("doc_number"),
            art_page_map=art_page_map,
        )
        from app.services.legal_relation_extractor import relink_legal_relations
        await relink_legal_relations(session, source_id=source.id)
        # Persist now: the embedding phase below is slow and may be cancelled by the job timeout.
        await session.commit()
    except Exception as e:
        source_id = source.id if "id" in source.__dict__ else None
        await session.rollback()
        # Rollback expires every loaded object; reload them asynchronously before reuse.
        for obj in [source, *pages_to_index]:
            await session.refresh(obj)
        logger.warning(f"Failed to ingest legal graph for source {source_id}: {e}")

    # 3. Compute vector embeddings (Page-level and Chunk-level)
    total_pages = len(pages_to_index)
    from app.services.page_indexing import embed_and_index_pages
    await embed_and_index_pages(session, pages_to_index, tracker, source_id=source.id)

    # 4. Regenerate wiki index and append log for each scope
    await tracker.update(96, "Đang cập nhật danh mục Wiki Index...")
    for scope_type, scope_id in wiki_scopes:
        try:
            await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
            log_msg = (
                f"Văn bản luật: Đã nhập '{display_doc_name}' "
                f"— tạo {len(articles) + 1} trang Wiki (1 Tổng quan + {total_articles} Điều)"
            )
            await wiki_service.append_log(session, log_msg, scope_type=scope_type, scope_id=scope_id)
        except Exception as e:
            logger.warning(f"Failed to regenerate index or log for {scope_type}:{scope_id}: {e}")

    from app.services.processing_mode import mark_articles_done
    mark_articles_done(source)
    if not final:
        # The LLM leg of the same wiki attempt continues and marks the branch ready.
        await tracker.update(
            50, f"Đã bóc tách {total_articles} điều — đang biên soạn trang tri thức bằng LLM..."
        )
        await session.commit()
        return {"status": "articles_ready", "total_pages": total_pages, "articles": total_articles}

    # 5. Mark wiki branch as ready and update dual status
    source.wiki_status = "ready"
    source.wiki_progress = 100
    source.wiki_progress_message = (
        f"Văn bản luật: Đã bóc tách {total_articles} điều thành {total_pages} trang Wiki ({display_doc_name})"
        if total_articles
        else f"Văn bản luật: Đã tạo {total_pages} trang Wiki"
    )
    from app.services.source_status import update_source_dual_status
    await update_source_dual_status(session, source)
    source.auto_recover_count = 0
    await session.commit()

    logger.info(
        f"Legal source {source.id} finalized successfully: "
        f"{total_pages} WikiPages created/updated ({total_articles} Điều)."
    )
    return {
        "status": "ready",
        "total_pages": total_pages,
        "articles": total_articles,
    }


async def ingest_legal_graph(
    session: AsyncSession,
    source: Source,
    articles: list[dict[str, Any]],
    preamble: str = "",
    doc_number: Optional[str] = None,
    art_page_map: Optional[dict[str, uuid.UUID]] = None,
) -> dict[str, int]:
    """Populate LegalUnit hierarchy and extract LegalRelation graph for a legal source."""
    from app.database.models import LegalUnit, LegalRelation, LegalUnitType, LegalRelationType
    from app.services.legal_relation_extractor import LegalRelationExtractor
    from sqlalchemy import delete

    # 1. Clean up existing units for idempotency
    await session.execute(delete(LegalUnit).where(LegalUnit.source_id == source.id))

    units_count = 0
    relations_count = 0
    extractor = LegalRelationExtractor()
    first_unit = None

    for art in articles:
        art_num = art.get("num") or art.get("number", "")
        art_title = art.get("title", "")
        art_content = art.get("content_md") or art.get("content", "")
        slug = art.get("slug", "")
        wiki_page_id = (art_page_map or {}).get(slug)

        art_unit = LegalUnit(
            id=uuid.uuid4(),
            source_id=source.id,
            wiki_page_id=wiki_page_id,
            unit_type=LegalUnitType.ARTICLE,
            unit_number=str(art_num),
            title=art_title,
            full_path=f"Điều {art_num}" + (f": {art_title}" if art_title else ""),
            content=art_content,
            doc_number=doc_number,
        )
        session.add(art_unit)
        units_count += 1
        if first_unit is None:
            first_unit = art_unit

        # Clauses
        for clause in art.get("clauses", []):
            cl_num = clause.get("num") or clause.get("number", "")
            cl_content = clause.get("content_md") or clause.get("content", "")
            clause_unit = LegalUnit(
                id=uuid.uuid4(),
                source_id=source.id,
                unit_type=LegalUnitType.CLAUSE,
                unit_number=str(cl_num),
                full_path=f"{art_unit.full_path} > Khoản {cl_num}",
                content=cl_content,
                parent_unit_id=art_unit.id,
                doc_number=doc_number,
            )
            session.add(clause_unit)
            units_count += 1

            # Points
            for point in clause.get("points", []):
                p_let = point.get("letter") or point.get("num", "")
                p_content = point.get("content_md") or point.get("content", "")
                point_unit = LegalUnit(
                    id=uuid.uuid4(),
                    source_id=source.id,
                    unit_type=LegalUnitType.POINT,
                    unit_number=str(p_let),
                    full_path=f"{clause_unit.full_path} > Điểm {p_let}",
                    content=p_content,
                    parent_unit_id=clause_unit.id,
                    doc_number=doc_number,
                )
                session.add(point_unit)
                units_count += 1

        # Extract relations from article content
        art_relations = extractor.extract_from_text(art_content, default_doc_number=doc_number)
        for rel in art_relations:
            rel_model = LegalRelation(
                id=uuid.uuid4(),
                source_unit_id=art_unit.id,
                target_doc_number=rel.target_doc_number,
                target_article_number=rel.target_article_number,
                target_clause_number=rel.target_clause_number,
                relation_type=rel.relation_type,
                quote_context=rel.quote_context,
                is_effective=True,
            )
            session.add(rel_model)
            relations_count += 1

    # Extract legal basis from preamble
    if preamble and first_unit:
        basis_relations = extractor.extract_preamble_basis(preamble)
        for rel in basis_relations:
            rel_model = LegalRelation(
                id=uuid.uuid4(),
                source_unit_id=first_unit.id,
                target_doc_number=rel.target_doc_number,
                relation_type=rel.relation_type,
                quote_context=rel.quote_context,
                is_effective=True,
            )
            session.add(rel_model)
            relations_count += 1

    return {"units_count": units_count, "relations_count": relations_count}


async def get_legal_context_with_hierarchy(
    session: AsyncSession,
    unit_id: uuid.UUID,
) -> dict[str, Any]:
    """Retrieve a legal unit along with its enclosing Article/Chapter context for RAG retrieval."""
    from app.database.models import LegalUnit, LegalUnitType

    unit = await session.get(LegalUnit, unit_id)
    if not unit:
        return {}

    parent_art = None
    if unit.unit_type in (LegalUnitType.CLAUSE, LegalUnitType.POINT):
        curr = unit
        while curr and curr.parent_unit_id:
            parent = getattr(curr, "parent", None) or await session.get(LegalUnit, curr.parent_unit_id)
            if parent and parent.unit_type == LegalUnitType.ARTICLE:
                parent_art = parent
                break
            curr = parent

    return {
        "unit_id": str(unit.id),
        "unit_type": unit.unit_type,
        "unit_number": unit.unit_number,
        "full_path": unit.full_path,
        "content": unit.content,
        "doc_number": unit.doc_number,
        "parent_article": {
            "id": str(parent_art.id),
            "number": parent_art.unit_number,
            "title": parent_art.title,
            "content": parent_art.content,
        } if parent_art else None,
    }


async def get_legal_unit_validity_warnings(
    session: AsyncSession,
    unit_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Check if a legal unit has been amended, supplemented, replaced, or repealed."""
    from sqlalchemy.orm import configure_mappers, selectinload

    configure_mappers()  # backref attributes (LegalRelation.source_unit) exist only after configure

    from app.database.models import LegalRelation, LegalRelationType

    # Eager-load: a lazy `rel.source_unit` raises MissingGreenlet under asyncio.
    query = (
        select(LegalRelation)
        .options(selectinload(LegalRelation.source_unit))
        .where(
            LegalRelation.target_unit_id == unit_id,
            LegalRelation.is_effective.is_(True),
            LegalRelation.relation_type.in_([
                LegalRelationType.SUA_DOI,
                LegalRelationType.BO_SUNG,
                LegalRelationType.THAY_THE,
                LegalRelationType.BAI_BO,
            ]),
        )
    )
    res = await session.execute(query)
    relations = res.scalars().all()

    warnings: list[dict[str, Any]] = []
    for rel in relations:
        source_u = getattr(rel, "source_unit", None)
        modifying_doc = (source_u.doc_number if source_u else None) or rel.target_doc_number or "văn bản mới"
        modifying_art = source_u.unit_number if source_u else None

        warnings.append({
            "relation_id": str(rel.id),
            "relation_type": rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type),
            "modifying_doc_number": modifying_doc,
            "modifying_article_number": modifying_art,
            "quote_context": rel.quote_context,
        })
    return warnings


def format_legal_validity_warning_callout(warnings: list[dict[str, Any]]) -> str:
    """Format legal validity warnings as a GitHub-style markdown alert box."""
    if not warnings:
        return ""

    lines = ["> [!WARNING]", "> **CẢNH BÁO HIỆU LỰC PHÁP LÝ**:"]
    for w in warnings:
        rel_type = w.get("relation_type", "")
        doc = w.get("modifying_doc_number", "")
        art = w.get("modifying_article_number")
        art_ref = f" (Điều {art})" if art else ""

        if rel_type == "sua_doi":
            msg = f"Quy định này đã được **sửa đổi, bổ sung** bởi {doc}{art_ref}."
        elif rel_type == "bo_sung":
            msg = f"Quy định này đã được **bổ sung** bởi {doc}{art_ref}."
        elif rel_type == "bai_bo":
            msg = f"Quy định này đã bị **bãi bỏ** bởi {doc}{art_ref}."
        elif rel_type == "thay_the":
            msg = f"Quy định này đã bị **thay thế** bởi {doc}{art_ref}."
        else:
            msg = f"Quy định này chịu tác động bởi văn bản {doc}{art_ref}."

        lines.append(f"> - {msg}")
        if w.get("quote_context"):
            lines.append(f">   *Trích dẫn*: \"{clip_text(w['quote_context'], 300)}\"")

    return "\n".join(lines)
