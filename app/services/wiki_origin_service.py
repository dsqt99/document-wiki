"""Immutable machine-origin boundaries for Wiki page writes."""
from __future__ import annotations

import re

EXTRACTED = "extracted"
GENERATED = "generated"
TAGS = (EXTRACTED, GENERATED)


def compatible(page, tag, source_id=None):
    if getattr(page, "origin_tag", None) != tag:
        return False
    return tag != EXTRACTED or source_id is not None and str(source_id) in {str(s) for s in (page.source_ids or [])}


def require_compatible(page, tag, source_id=None):
    if tag not in TAGS or getattr(page, "origin_tag", None) != tag:
        raise ValueError("Không được cập nhật/merge Wiki khác tag nguồn gốc.")
    if not compatible(page, tag, source_id):
        raise ValueError("Trang Extracted chỉ được cập nhật từ cùng tài liệu nguồn.")


async def resolve_target_slug(session, slug, tag, scope_type, scope_id, source_id):
    from app.services import wiki_service
    if tag not in TAGS:
        raise ValueError("Tag Wiki không hợp lệ")
    suffixes = ["", f"-{tag}", f"-{tag}-{str(source_id)[:8]}"]
    for suffix in suffixes:
        candidate = slug[:300 - len(suffix)] + suffix
        page = await wiki_service.get_page_by_slug(session, candidate, scope_type=scope_type, scope_id=scope_id)
        if page is None or compatible(page, tag, source_id):
            return candidate
    raise ValueError("Đường dẫn Wiki đã được dùng bởi trang khác tag hoặc khác tài liệu nguồn.")


def remap_links(content, mapping):
    def replace(match):
        slug, label = match.group(1), match.group(2) or ""
        return "[[" + mapping.get(slug, slug) + label + "]]"
    return re.sub(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]", replace, content or "")
