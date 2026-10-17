"""Alembic runtime hooks.

Migrations run either "offline" (SQL emitted as text) or "online" through an
asyncpg engine built without connection pooling. Table metadata comes from the
ORM declarative base; extra model modules are imported so their tables register.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database.models import Base  # noqa: E402
import app.database.oauth_models  # noqa: E402,F401
import app.models.task_failure  # noqa: E402,F401
import app.models.concept_relation  # noqa: E402,F401

alembic_cfg = context.config
if alembic_cfg.config_file_name:
    fileConfig(alembic_cfg.config_file_name)
alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _migrate_in_transaction(**configure_kwargs) -> None:
    context.configure(target_metadata=target_metadata, **configure_kwargs)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    _migrate_in_transaction(
        url=alembic_cfg.get_main_option("sqlalchemy.url"),
        dialect_opts={"paramstyle": "named"},
        literal_binds=True,
    )


def _do_run_migrations(connection) -> None:
    _migrate_in_transaction(connection=connection)


async def run_migrations_online() -> None:
    engine_options = alembic_cfg.get_section(alembic_cfg.config_ini_section) or {}
    engine = async_engine_from_config(engine_options, poolclass=pool.NullPool, prefix="sqlalchemy.")
    try:
        async with engine.connect() as conn:
            await conn.run_sync(_do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
