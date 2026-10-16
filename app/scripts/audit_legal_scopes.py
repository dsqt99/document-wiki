"""
Script audit và khắc phục các trang Wiki văn bản luật bị gán nhầm phạm vi 'global'
trong khi tài liệu nguồn (Source) thuộc về một hoặc nhiều phòng ban cụ thể.

Sử dụng:
    python -m app.scripts.audit_legal_scopes [--fix]
"""

import argparse
import asyncio
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import Source, SourceDepartment, WikiPage
from app.services.wiki_service import resolve_wiki_scopes, regenerate_index


async def audit_legal_scopes(fix: bool = False):
    async with async_session_factory() as session:
        # Find all sources that are legal or have department assignments
        sources = (await session.execute(
            select(Source).order_by(Source.created_at.desc())
        )).scalars().all()

        mismatched_pages = []

        for src in sources:
            scopes = await resolve_wiki_scopes(session, src)
            is_scoped_source = any(s[0] in ("department", "project") for s in scopes)
            if not is_scoped_source:
                continue

            # Check pages referencing this source
            pages = (await session.execute(
                select(WikiPage).where(WikiPage.source_ids.contains([src.id]))
            )).scalars().all()

            for p in pages:
                if p.scope_type == "global":
                    mismatched_pages.append((p, src, scopes))

        logger.info(f"Phát hiện {len(mismatched_pages)} trang Wiki bị rò rỉ scope 'global'")

        for p, src, target_scopes in mismatched_pages:
            logger.warning(
                f"Page '{p.slug}' (ID: {p.id}) thuộc Source '{src.title}' "
                f"đang ở scope '{p.scope_type}' nhưng target scopes là: {target_scopes}"
            )
            if fix:
                # Gán vào scope đầu tiên và thông báo nếu có đa phòng ban
                target_type, target_id = target_scopes[0]
                p.scope_type = target_type
                p.scope_id = target_id
                logger.success(f"Đã cập nhật Page '{p.slug}' sang {target_type}:{target_id}")

        if fix and mismatched_pages:
            await session.commit()
            logger.info("Đã lưu các thay đổi vào cơ sở dữ liệu.")


def main():
    parser = argparse.ArgumentParser(description="Audit and fix legal page scopes")
    parser.add_argument("--fix", action="store_true", help="Fix mismatched scopes")
    args = parser.parse_args()

    asyncio.run(audit_legal_scopes(fix=args.fix))


if __name__ == "__main__":
    main()
