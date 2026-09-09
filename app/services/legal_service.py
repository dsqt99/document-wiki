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
# Matches:
#   group 1: Full heading, e.g. 'Điều 1. Phạm vi điều chỉnh'
#   group 2: Article number, e.g. '1', '18a', '104'
#   group 3: Article title after punctuation (optional), e.g. 'Phạm vi điều chỉnh'
ARTICLE_RE = re.compile(
    r'(?:^|\n)\s*(?:“|\"|”)?\s*(Điều\s+(\d+[a-z]?)(?:[\.:\–\-]\s*([^\n\r]*)|$))',
    re.IGNORECASE,
)


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
        raw_heading = m.group(1).strip()
        art_title = (m.group(3) or "").strip()
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
    """Check if the source is associated with KnowledgeType 'Luật'."""
    if not source.knowledge_type_id:
        return False

    kt = await session.get(KnowledgeType, source.knowledge_type_id)
    if not kt:
        return False

    slug = (kt.slug or "").lower().strip()
    name = (kt.name or "").lower().strip()
    return slug in ("lut", "luat") or "luật" in name or "luat" in name


async def finalize_legal_source(session: AsyncSession, source: Source, tracker: Any) -> dict:
    """Legal path: parse document by articles into WikiPages and compute vector embeddings.

    - Extracts preamble and all articles verbatim.
    - Creates/updates an Overview WikiPage with metadata and Table of Contents wikilinks.
    - Creates/updates an individual WikiPage for each Điều.
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

    # Extract articles
    parsed = split_legal_text_by_articles(full_text, doc_title)
    preamble = parsed["preamble"]
    articles = parsed["articles"]

    scope_type = source.scope_type or "global"
    scope_id = source.scope_id

    # Get knowledge type slug
    kt_slug = "lut"
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

    overview_content_parts = [f"# {doc_title}\n"]
    if preamble:
        overview_content_parts.append(preamble)
    if toc_md:
        overview_content_parts.append(f"\n## Danh mục các Điều\n\n{toc_md}\n")
    overview_content = "\n\n".join(overview_content_parts).strip() + "\n"

    overview_summary = (
        preamble[:280].replace("\n", " ").strip()
        if preamble
        else f"Tổng quan văn bản quy phạm pháp luật {doc_title}"
    )

    overview_page = await wiki_service.upsert_page(
        session,
        slug=doc_slug,
        title=f"{doc_title} - Tổng quan & Căn cứ ban hành",
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

    # 2. Create/update each Điều as a separate WikiPage (Verbatim content)
    for idx, art in enumerate(articles):
        art_slug = art["slug"]
        heading = art["heading"]
        art_num = art["num"]
        art_title = art["title"]
        verbatim_content = art["content_md"]

        page_title = (
            f"Điều {art_num}: {art_title} - {doc_title}"
            if art_title
            else f"{heading} - {doc_title}"
        )

        page_content = (
            f"> Thuộc văn bản: [[{doc_slug}|{doc_title}]]\n\n"
            f"{verbatim_content}\n"
        )

        first_para = ""
        for line in verbatim_content.splitlines():
            line_s = line.strip()
            if line_s and not line_s.lower().startswith("điều "):
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

    await session.flush()

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
            f"Văn bản luật: Đã nhập '{doc_title}' "
            f"— tạo {total_pages} trang Wiki (1 Tổng quan + {total_articles} Điều)"
        )
        await wiki_service.append_log(session, log_msg, scope_type=scope_type, scope_id=scope_id)
    except Exception as e:
        logger.warning(f"Failed to regenerate index or log: {e}")

    # 5. Mark source as ready
    source.status = "ready"
    source.progress = 100
    source.progress_message = (
        f"Văn bản luật: Đã bóc tách {total_articles} điều thành {total_pages} trang Wiki"
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
