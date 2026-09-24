"""
Seed default knowledge types: 'general' (Chung) and 'legal' (Văn bản luật).

Runs during app lifespan startup, in entrypoint.sh, and as standalone script.
Idempotent: inserts or updates without duplicating.
"""

from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import KnowledgeType

DEFAULT_KNOWLEDGE_TYPES = [
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
        "description": "Văn bản quy phạm pháp luật, nghị định, thông tư (tự động bóc tách theo Điều)",
    },
]


async def seed_default_knowledge_types() -> None:
    """Seed default knowledge types if they do not exist."""
    try:
        async with async_session_factory() as session:
            for item in DEFAULT_KNOWLEDGE_TYPES:
                # Check by slug
                stmt = select(KnowledgeType).where(KnowledgeType.slug == item["slug"]).limit(1)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    # Also check if 'luat' already exists when checking 'legal'
                    if item["slug"] == "legal":
                        alt_stmt = select(KnowledgeType).where(KnowledgeType.slug == "luat").limit(1)
                        alt_result = await session.execute(alt_stmt)
                        if alt_result.scalar_one_or_none():
                            continue

                    kt = KnowledgeType(
                        slug=item["slug"],
                        name=item["name"],
                        color=item["color"],
                        sort_order=item["sort_order"],
                        description=item["description"],
                    )
                    session.add(kt)
                    logger.info(f"Seeding default KnowledgeType: {item['slug']} ({item['name']})")

            await session.commit()
            logger.success("Default KnowledgeTypes checked/seeded.")
    except Exception as e:
        logger.warning(f"Could not seed default knowledge types: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed_default_knowledge_types())
