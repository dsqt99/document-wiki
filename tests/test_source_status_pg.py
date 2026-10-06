"""Postgres integration tests for the dual-pipeline status row lock.

Mock-based tests cannot prove that two branches finishing at the same time
never overwrite each other — that needs a real FOR UPDATE. These run only when
ARKON_IT_DATABASE_URL points at a *throwaway* database (tables are created
there), e.g.:

    docker run -d --rm --name arkon_it_pg -e POSTGRES_USER=it -e POSTGRES_PASSWORD=it \
        -e POSTGRES_DB=arkon_it -p 127.0.0.1:15433:5432 pgvector/pgvector:pg16
    ARKON_IT_DATABASE_URL=postgresql+asyncpg://it:it@127.0.0.1:15433/arkon_it pytest tests/test_source_status_pg.py

Never point it at the production `arkon` database.
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

IT_URL = os.environ.get("ARKON_IT_DATABASE_URL")

pytestmark = pytest.mark.skipif(not IT_URL, reason="ARKON_IT_DATABASE_URL not set")


@pytest_asyncio.fixture
async def session_factory():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database.models import Base, Source

    # Only `sources` and the tables its foreign keys reach.
    needed, todo = set(), [Source.__table__]
    while todo:
        table = todo.pop()
        if table in needed:
            continue
        needed.add(table)
        todo += [fk.column.table for fk in table.foreign_keys]

    engine = create_async_engine(IT_URL, pool_size=10)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=list(needed)))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _new_source(factory, **fields):
    from app.database.models import Source

    src = Source(
        id=uuid.uuid4(),
        title="it-source",
        scope_type="global",
        preserve_verbatim=False,
        status="processing",
        chunk_status="processing",
        wiki_status="processing",
        **fields,
    )
    async with factory() as s:
        s.add(src)
        await s.commit()
    return src.id


async def _load(factory, source_id):
    from app.database.models import Source

    async with factory() as s:
        return (await s.execute(select(Source).where(Source.id == source_id))).scalar_one()


@pytest.mark.asyncio
async def test_set_branch_state_waits_for_lock_and_sees_other_branch(session_factory):
    """Branch A updates while branch B holds the row lock: A must wait, then
    recompute the aggregate from B's committed state (no lost update)."""
    from app.database.models import Source
    from app.services.source_status import set_branch_state

    source_id = await _new_source(session_factory)

    async with session_factory() as holder:
        src_b = (await holder.execute(
            select(Source).where(Source.id == source_id).with_for_update()
        )).scalar_one()

        async with session_factory() as s_a:
            task = asyncio.create_task(
                set_branch_state(source_id, "chunk", status="ready", progress=100, session=s_a)
            )
            await asyncio.sleep(0.5)
            assert not task.done(), "set_branch_state must block on the row lock"

            src_b.wiki_status = "ready"
            src_b.wiki_progress = 100
            await holder.commit()

            agg = await asyncio.wait_for(task, timeout=10)

    assert agg == "ready"
    row = await _load(session_factory, source_id)
    assert (row.chunk_status, row.wiki_status, row.status) == ("ready", "ready", "ready")


@pytest.mark.asyncio
async def test_concurrent_branch_updates_keep_both_branches(session_factory):
    """Many interleaved updates from both branches: the final row holds the last
    value of each branch and an aggregate consistent with them."""
    from app.services.source_status import compute_source_dual_status, set_branch_state

    source_id = await _new_source(session_factory)

    async def _branch(branch, final_status):
        for p in range(10, 100, 10):
            async with session_factory() as s:
                await set_branch_state(source_id, branch, progress=p, message=f"{branch} {p}%", session=s)
        async with session_factory() as s:
            await set_branch_state(
                source_id, branch, status=final_status, progress=100,
                error="boom" if final_status == "error" else None, session=s,
            )

    await asyncio.gather(_branch("chunk", "ready"), _branch("wiki", "error"))

    row = await _load(session_factory, source_id)
    assert row.chunk_status == "ready"
    assert row.wiki_status == "error"
    assert row.status == "partial"
    assert (row.status, row.progress, row.progress_message) == compute_source_dual_status(row)


@pytest.mark.asyncio
async def test_wiki_attempt_check_against_real_row(session_factory):
    """A new wiki attempt invalidates old branch-B jobs but not branch-A ones."""
    from app.database.models import Source
    from app.services.source_status import start_wiki_attempt
    from app.worker import check_task_attempt_validity

    global_attempt = uuid.uuid4()
    source_id = await _new_source(session_factory, attempt_id=global_attempt)

    async with session_factory() as s:
        # Legacy row (no wiki_attempt_id): branch B falls back to the global attempt.
        assert await check_task_attempt_validity(s, source_id, str(global_attempt), branch="wiki")

        src = (await s.execute(select(Source).where(Source.id == source_id))).scalar_one()
        new_wiki = start_wiki_attempt(src)
        await s.commit()

    async with session_factory() as s:
        assert not await check_task_attempt_validity(s, source_id, str(global_attempt), branch="wiki")
        assert await check_task_attempt_validity(s, source_id, new_wiki, branch="wiki")
        assert await check_task_attempt_validity(s, source_id, str(global_attempt))
