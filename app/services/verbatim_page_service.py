"""processing_mode=verbatim_page: the extracted document (text and image markers) becomes
wiki page(s) as is, without the LLM. Long documents are split into numbered parts at
paragraph boundaries, preferring headings, with an overview page linking them."""

from __future__ import annotations

import re
from typing import Any, Optional

from loguru import logger

from app.config import settings
from app.services import wiki_service
from app.utils.text import slugify

_BLOCK_SPLIT = re.compile(r"\n[ \t]*\n")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_FILE_EXTS = (".docx", ".doc", ".pdf", ".txt", ".md", ".xlsx", ".pptx", ".csv")


def _doc_title(source) -> str:
    title = (source.title or source.file_name or f"Tài liệu {source.id}").strip()
    for ext in _FILE_EXTS:
        if title.lower().endswith(ext):
            return title[: -len(ext)].strip() or title
    return title


def _hard_split(block: str, max_chars: int) -> list[str]:
    """A single block longer than a part: cut at line ends (never inside a line)."""
    out: list[str] = []
    cur: list[str] = []
    size = 0
    for line in block.split("\n"):
        if cur and size + len(line) + 1 > max_chars:
            out.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        out.append("\n".join(cur))
    return out


def split_parts(text: str, max_chars: int) -> list[str]:
    """Split markdown into parts of at most ``max_chars`` (a single over-long line excepted).

    Cuts only between blank-line separated blocks, so image markers, tables and list
    items stay whole. A heading starts a new part once the current one is 3/4 full.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    blocks: list[str] = []
    for b in _BLOCK_SPLIT.split(text):
        if not b.strip():
            continue
        # A heading line stays with the block it introduces.
        if blocks and _HEADING.match(blocks[-1].strip()) and len(blocks[-1]) + len(b) + 2 <= max_chars:
            blocks[-1] = f"{blocks[-1]}\n\n{b}"
            continue
        blocks.extend(_hard_split(b, max_chars) if len(b) > max_chars else [b])
    parts: list[str] = []
    cur: list[str] = []
    size = 0
    for b in blocks:
        is_heading = bool(_HEADING.match(b.lstrip().split("\n", 1)[0]))
        if cur and (size + len(b) + 2 > max_chars or (is_heading and size >= max_chars * 3 // 4)):
            parts.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(b)
        size += len(b) + 2
    if cur:
        parts.append("\n\n".join(cur))
    return parts


def _first_heading(md: str) -> Optional[str]:
    """First heading usable as a part label (PDF extraction leaves broken ones like '## tiện')."""
    for line in md.splitlines():
        m = _HEADING.match(line.strip())
        text = m.group(1).strip("*_ ").strip() if m else ""
        if text and (text[0].isupper() or text[0].isdigit()):
            return text
    return None


def _summary(md: str, fallback: str) -> str:
    for line in md.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "!", "|", ">", "<")) and len(s) > 20:
            return s.strip("*_ ")[:280]
    return fallback


def base_slug(source) -> str:
    stem = slugify(_doc_title(source))[:60].strip("-") or "tai-lieu"
    return f"{stem}-{str(source.id)[:8]}"


async def finalize_verbatim_pages(session, source, tracker: Any) -> dict:
    from app.database.models import KnowledgeType
    from app.services.page_indexing import embed_and_index_pages
    from app.services.source_status import update_source_dual_status

    await tracker.update(55, "Đang tạo trang Wiki nguyên văn...")
    title = _doc_title(source)
    full_text = (source.full_text or "").strip()
    max_chars = max(2000, int(getattr(settings, "verbatim_page_max_chars", 40000) or 40000))
    parts = split_parts(full_text, max_chars)

    kt_slugs: list[str] = []
    if source.knowledge_type_id:
        kt = await session.get(KnowledgeType, source.knowledge_type_id)
        if kt and kt.slug:
            kt_slugs = [kt.slug]

    base = base_slug(source)
    origin = f"> **Nguồn**: {source.file_name or title} — nguyên văn, không qua biên soạn LLM"
    pages: list = []
    for scope_type, scope_id in await wiki_service.resolve_wiki_scopes(session, source):
        common = dict(
            knowledge_type_slugs=kt_slugs, source_ids=[source.id],
            scope_type=scope_type, scope_id=scope_id, status="mature",
        )
        if len(parts) <= 1:
            body = parts[0] if parts else "_Tài liệu không có nội dung văn bản._"
            pages.append(await wiki_service.upsert_page(
                session, slug=base, title=title, page_type="source",
                content_md=f"{origin}\n\n{body}\n", summary=_summary(body, title), **common,
            ))
            continue

        n = len(parts)
        labels = []
        for i, part in enumerate(parts, 1):
            heading = _first_heading(part)
            labels.append(f"Phần {i}" + (f": {heading[:80]}" if heading else ""))
        toc = "\n".join(f"- [[{base}-phan-{i}|{label}]]" for i, label in enumerate(labels, 1))
        pages.append(await wiki_service.upsert_page(
            session, slug=base, title=title, page_type="source",
            content_md=(
                f"{origin}\n\nTài liệu dài nên được chia thành {n} phần, giữ nguyên văn bản và hình ảnh.\n\n"
                f"## Các phần\n\n{toc}\n"
            ),
            summary=_summary(parts[0], title), **common,
        ))
        for i, part in enumerate(parts, 1):
            nav = [f"[[{base}|Mục lục]]"]
            if i > 1:
                nav.insert(0, f"[[{base}-phan-{i - 1}|← Phần {i - 1}]]")
            if i < n:
                nav.append(f"[[{base}-phan-{i + 1}|Phần {i + 1} →]]")
            nav_line = " · ".join(nav)
            pages.append(await wiki_service.upsert_page(
                session, slug=f"{base}-phan-{i}", title=f"{labels[i - 1]} — {title}", page_type="source",
                content_md=f"> **{title}** — phần {i}/{n} · {nav_line}\n\n{part}\n\n---\n\n{nav_line}\n",
                summary=_summary(part, f"{title} — phần {i}/{n}"), **common,
            ))
            await tracker.update(60 + int(i / n * 8), f"Đã tạo {i}/{n} phần nguyên văn...")
    await session.commit()

    await embed_and_index_pages(session, pages, tracker, source_id=source.id)

    await tracker.update(96, "Đang cập nhật danh mục Wiki Index...")
    for scope_type, scope_id in await wiki_service.resolve_wiki_scopes(session, source):
        try:
            await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
            await wiki_service.append_log(
                session,
                f"Nguyên văn: Đã nhập '{title}' — {max(len(parts), 1)} phần",
                scope_type=scope_type, scope_id=scope_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to regenerate index or log for {scope_type}:{scope_id}: {e}")

    source.wiki_status = "ready"
    source.wiki_progress = 100
    source.wiki_progress_message = (
        f"Nguyên văn: {len(parts)} phần, {len(pages)} trang Wiki"
        if len(parts) > 1
        else "Nguyên văn: đã tạo 1 trang Wiki"
    )
    await update_source_dual_status(session, source)
    source.auto_recover_count = 0
    await session.commit()
    return {"status": "ready", "total_pages": len(pages), "parts": len(parts)}
