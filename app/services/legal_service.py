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

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.database.models import KnowledgeType, Source, WikiPage
from app.services import wiki_service
from app.services.embedding_storage import (
    upsert_page_embedding,
    wiki_chunk_content_hash,
)
from app.services.wiki_chunk_service import index_wiki_page_chunks
from app.utils.text import slugify

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


def parse_legal_metadata(text: str, file_name: str = "") -> dict[str, Any]:
    """Extract formal legal metadata (doc number, authority, date, doc type, title)

    from Vietnamese legal document preambles or filename fallbacks.
    """
    preamble = text[:4000] if text else ""
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

        title_display = meta["official_title"].title() if meta.get("official_title") else ""
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


def split_legal_text_by_articles(full_text: str, doc_title: str) -> dict[str, Any]:
    """Parse Vietnamese legal document text into preamble and individual articles.

    Returns:
        dict with:
            - 'preamble': text prior to the first 'Điều' (issuing authority, legal basis, etc.)
            - 'articles': list of dicts with:
                - 'num': article number (e.g. '1', '18a')
                - 'heading': full header line (e.g. 'Điều 1. Phạm vi điều chỉnh')
                - 'title': extracted title string
                - 'content_md': verbatim article text
                - 'slug': unique page slug
    """
    if not full_text:
        return {"preamble": "", "articles": []}

    matches = list(ARTICLE_RE.finditer(full_text))
    doc_slug = slugify(doc_title or "van-ban-luat")[:60].rstrip("-") or "van-ban-luat"

    if not matches:
        return {
            "preamble": full_text.strip(),
            "articles": [],
        }

    preamble = full_text[: matches[0].start()].strip()
    articles: list[dict[str, Any]] = []
    seen_slugs: set[str] = {doc_slug}

    for i, m in enumerate(matches):
        start_idx = m.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        art_num = m.group(2).strip()
        raw_heading = re.sub(r'[*#_“"”]', '', m.group(1)).strip()
        art_title = re.sub(r'[*#_“"”]', '', m.group(3) or '').strip()
        art_content = full_text[start_idx:end_idx].strip()

        # Build unique slug for this article (dieu-X-doc-slug)
        base_slug = f"dieu-{art_num.lower()}-{doc_slug}"
        art_slug = base_slug
        if art_slug in seen_slugs:
            title_part = slugify(art_title)[:30].rstrip("-")
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
            "content_md": art_content,
            "slug": art_slug,
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


async def finalize_legal_source(session: AsyncSession, source: Source, tracker: Any) -> dict:
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
        source.status = "ready"
        source.progress = 100
        source.progress_message = "Văn bản trống, không có nội dung để trích xuất"
        await session.commit()
        return {"status": "ready", "pages_created": 0}

    # Extract legal metadata
    meta = parse_legal_metadata(full_text, source.file_name or "")
    display_doc_name = meta.get("canonical_name") or doc_title

    if not source.title or source.title == source.file_name or source.title.endswith((".pdf", ".docx")):
        source.title = display_doc_name
    await session.commit()

    # Extract articles
    parsed = split_legal_text_by_articles(full_text, doc_title)
    preamble = parsed["preamble"]
    articles = parsed["articles"]

    scope_type = source.scope_type or "global"
    scope_id = source.scope_id

    # Get knowledge type slug
    kt_slug = "legal"
    if source.knowledge_type_id:
        kt = await session.get(KnowledgeType, source.knowledge_type_id)
        if kt and kt.slug:
            kt_slug = kt.slug

    doc_slug = slugify(doc_title)[:60].rstrip("-") or "van-ban-luat"

    # Setup embedding provider
    registry = ProviderRegistry(session)
    spec_id = await registry.get_active_embedding_spec_id()
    embedding_spec = get_spec(spec_id) if spec_id else None
    embedding_provider = None
    if embedding_spec:
        try:
            embedding_provider = await registry.get_embedding(task="document", spec_id=embedding_spec.id)
        except Exception as e:
            logger.warning(f"Failed to get embedding provider for {embedding_spec.id}: {e}")

    pages_to_index: list[WikiPage] = []
    total_articles = len(articles)

    # 1. Create/update Overview WikiPage (Preamble & Table of Contents)
    toc_lines = []
    for art in articles:
        label = f"Điều {art['num']}" + (f": {art['title']}" if art['title'] else "")
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
        or (preamble[:280].replace("\n", " ").strip() if preamble else f"Tổng quan văn bản quy phạm pháp luật {display_doc_name}")
    )

    overview_page = await wiki_service.upsert_page(
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

    # 2. Create/update each Điều as a separate WikiPage (Verbatim content with citation)
    for idx, art in enumerate(articles):
        art_slug = art["slug"]
        heading = art["heading"]
        art_num = art["num"]
        art_title = art["title"]
        verbatim_content = art["content_md"]

        page_title = (
            f"Điều {art_num}: {art_title} - {display_doc_name}"
            if art_title
            else f"{heading} - {display_doc_name}"
        )

        citation_lines = [
            f"> **Căn cứ pháp lý**: Điều {art_num} — {display_doc_name}",
        ]
        if meta.get("official_title"):
            citation_lines.append(f"> **Trích yếu**: {meta['official_title']}")
        citation_lines.append(f"> **Toàn văn văn bản**: [[{doc_slug}|{display_doc_name}]]")
        citation_header = "\n".join(citation_lines)

        page_content = f"{citation_header}\n\n{verbatim_content}\n"

        first_para = ""
        for line in verbatim_content.splitlines():
            line_s = line.strip()
            if line_s and not line_s.lower().startswith("điều ") and not line_s.startswith(("#", "*", ">")):
                first_para = line_s
                break
        page_summary = f"Điều {art_num}" + (f": {art_title}" if art_title else "")
        if first_para:
            page_summary += f" — {first_para[:180]}"

        art_page = await wiki_service.upsert_page(
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
        pages_to_index.append(art_page)

    await session.commit()

    # 3. Compute vector embeddings (Page-level and Chunk-level)
    total_pages = len(pages_to_index)
    await tracker.update(70, f"Đang tạo vector embeddings cho {total_pages} trang Wiki...")

    if embedding_provider and embedding_spec:
        # A. Page-level embedding in batches
        batch_size = 16
        for b_start in range(0, total_pages, batch_size):
            b_pages = pages_to_index[b_start : b_start + batch_size]
            texts_to_embed = [
                f"{p.title}\n\n{p.summary}\n\n{(p.content_md or '')[:4000]}"
                for p in b_pages
            ]
            try:
                vectors = await embedding_provider.embed_batch(texts_to_embed)
                for p, vec in zip(b_pages, vectors):
                    chash = wiki_chunk_content_hash("", p.content_md or "")
                    await upsert_page_embedding(
                        session,
                        page_id=p.id,
                        spec=embedding_spec,
                        vector=list(vec),
                        content_hash=chash,
                        title=p.title,
                        summary=p.summary,
                        content_md=p.content_md,
                    )
            except Exception as e:
                logger.warning(f"Batch page embedding failed for pages {b_start}-{b_start+len(b_pages)}: {e}")

            # Update progress between 70% and 85%
            pct = 70 + int((b_start + len(b_pages)) / total_pages * 15)
            await tracker.update(pct, f"Đã tính embedding trang ({b_start + len(b_pages)}/{total_pages})...")

        # B. Section-level chunk embeddings
        for idx, p in enumerate(pages_to_index):
            try:
                await index_wiki_page_chunks(session, p, spec_id=embedding_spec.id)
            except Exception as e:
                logger.warning(f"Chunk embedding failed for page '{p.slug}': {e}")

            if idx % 10 == 0 or idx == total_pages - 1:
                pct = 85 + int((idx + 1) / total_pages * 10)
                await tracker.update(pct, f"Đã đánh chỉ mục chunk ({idx + 1}/{total_pages})...")
    else:
        logger.info("No active embedding model configured — skipping semantic vector index.")

    # 4. Regenerate wiki index and append log
    await tracker.update(96, "Đang cập nhật danh mục Wiki Index...")
    try:
        await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
        log_msg = (
            f"Văn bản luật: Đã nhập '{display_doc_name}' "
            f"— tạo {total_pages} trang Wiki (1 Tổng quan + {total_articles} Điều)"
        )
        await wiki_service.append_log(session, log_msg, scope_type=scope_type, scope_id=scope_id)
    except Exception as e:
        logger.warning(f"Failed to regenerate index or log: {e}")

    # 5. Mark source as ready
    source.status = "ready"
    source.progress = 100
    source.progress_message = (
        f"Văn bản luật: Đã bóc tách {total_articles} điều thành {total_pages} trang Wiki ({display_doc_name})"
        if total_articles
        else f"Văn bản luật: Đã tạo {total_pages} trang Wiki"
    )
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
