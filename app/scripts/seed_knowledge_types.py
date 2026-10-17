"""Seed the default knowledge types (idempotent). Run: python -m app.scripts.seed_knowledge_types"""

import asyncio
import logging

from sqlalchemy import select

logger = logging.getLogger(__name__)

LEGACY_LEGAL_SLUG = "luat"

DEFAULT_KNOWLEDGE_TYPES: list[dict] = [
    {
        "slug": "general",
        "name": "Chung",
        "color": "#6B7280",
        "sort_order": 0,
        "description": "Tài liệu, quy định và thông tin chung",
    },
    {
        "slug": "legal",
        "name": "Văn bản luật",
        "color": "#DC2626",
        "sort_order": 1,
        "description": "Văn bản quy phạm pháp luật",
    },
]


async def seed_default_knowledge_types() -> None:
    from app import database
    from app.database.models import KnowledgeType

    try:
        async with database.async_session_factory() as session:
            existing = set((await session.execute(select(KnowledgeType.slug))).scalars().all())
            for item in DEFAULT_KNOWLEDGE_TYPES:
                if item["slug"] in existing:
                    continue
                if item["slug"] == "legal" and LEGACY_LEGAL_SLUG in existing:
                    continue
                session.add(KnowledgeType(**item))
            await session.commit()
    except Exception as e:
        logger.warning("Knowledge type seed failed: %s", e)


if __name__ == "__main__":
    asyncio.run(seed_default_knowledge_types())
