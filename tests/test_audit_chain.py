"""Audit hash chain on a real PostgreSQL (advisory lock, triggers, migration 049). Skipped without TEST_DATABASE_URL."""

import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB

pytestmark = pytest.mark.skipif(not TEST_DB, reason="needs TEST_DATABASE_URL (PostgreSQL)")

if TEST_DB:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import select, text

    from app.config import settings
    from app.database import async_session_factory, engine
    from app.database.models import AuditLog
    from app.services import audit_chain, trace_context

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "049_audit_hash_chain.py"
TABLES = ("audit_chain_head", "audit_log", "audit_log_legacy")
USER = uuid.UUID("11111111-1111-1111-1111-111111111111")

LEGACY_DDL = """
CREATE TABLE audit_log (
    id UUID PRIMARY KEY, timestamp TIMESTAMPTZ NOT NULL DEFAULT now(), principal_id UUID NOT NULL,
    principal_type VARCHAR(20) NOT NULL DEFAULT 'human', action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL, resource_id VARCHAR(100) NOT NULL, scope_type VARCHAR(20),
    scope_id UUID, decision VARCHAR(10) NOT NULL, reason TEXT, metadata JSONB
)
"""


def run(coro):
    async def wrapper():
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())


def _migration():
    spec = importlib.util.spec_from_file_location("m049", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _migrate(direction):
    module = _migration()

    def go(sync_conn):
        with Operations.context(MigrationContext.configure(sync_conn)):
            getattr(module, direction)()

    async with engine.begin() as conn:
        await conn.run_sync(go)


async def _drop_all():
    async with engine.begin() as conn:
        for name in TABLES:
            await conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))
        await conn.execute(text("DROP FUNCTION IF EXISTS audit_guard_immutable() CASCADE"))


async def _create_legacy(rows=2):
    async with engine.begin() as conn:
        await conn.execute(text(LEGACY_DDL))
        await conn.execute(text("CREATE INDEX ix_audit_log_timestamp ON audit_log (timestamp)"))
        await conn.execute(text("CREATE INDEX ix_audit_log_principal ON audit_log (principal_id)"))
        await conn.execute(text("CREATE INDEX ix_audit_log_resource ON audit_log (resource_type, resource_id)"))
        for i in range(rows):
            await conn.execute(
                text(
                    "INSERT INTO audit_log (id, principal_id, action, resource_type, resource_id, decision) "
                    "VALUES (:id, :p, 'read', 'source', :r, 'allow')"
                ),
                {"id": uuid.uuid4(), "p": USER, "r": f"old{i}"},
            )


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(settings, "audit_hmac_key", "unit-test-key-one")

    async def prepare():
        await _drop_all()
        await _create_legacy()
        await _migrate("upgrade")

    run(prepare())
    yield
    run(_drop_all())


async def _fill(n=4):
    ids = []
    for i in range(n):
        entry = await audit_chain.record(
            principal_id=USER, action="source.create", resource_type="source", resource_id=f"s{i}",
            reason="ghi thử", metadata={"k": i, "tên": "giá trị"},
        )
        ids.append(entry.id)
    return ids


async def _verify():
    async with async_session_factory() as session:
        return await audit_chain.verify_chain(session)


async def _raw(statement, **params):
    """SQL as someone with database rights: user triggers are switched off for the statement."""
    async with engine.begin() as conn:
        for table in TABLES:
            await conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        await conn.execute(text(statement), params)
        for table in TABLES:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))


def test_migration_archives_legacy_rows_and_chain_starts_with_baseline(chain):
    async def scenario():
        await _fill(2)
        async with engine.connect() as conn:
            legacy = (await conn.execute(text("SELECT count(*) FROM audit_log_legacy"))).scalar()
        async with async_session_factory() as session:
            rows = (await session.execute(select(AuditLog).order_by(AuditLog.seq))).scalars().all()
        return legacy, rows, await _verify()

    legacy, rows, verdict = run(scenario())
    assert legacy == 2
    assert [r.seq for r in rows] == [1, 2, 3]
    assert rows[0].action == audit_chain.BASELINE_ACTION and rows[0].prev_hash == audit_chain.GENESIS_HASH
    assert rows[0].metadata_["legacy_rows"] == 2 and len(rows[0].metadata_["legacy_digest"]) == 64
    assert verdict["valid"] is True and verdict["total_events"] == 3 and verdict["legacy_rows"] == 2
    assert all(r.trace_id for r in rows)


@pytest.mark.parametrize(
    "column,value",
    [
        ("principal_id", "'22222222-2222-2222-2222-222222222222'"),
        ("action", "'source.delete'"),
        ("resource_id", "'s-khac'"),
        ("decision", "'deny'"),
        ("reason", "'đã sửa'"),
        ("trace_id", "'tr-gia-mao'"),
        ("timestamp", "now() + interval '1 day'"),
        ("metadata", "'{\"k\": 999}'::jsonb"),
    ],
)
def test_editing_any_field_breaks_the_chain(chain, column, value):
    async def scenario():
        ids = await _fill(3)
        await _raw(f"UPDATE audit_log SET {column} = {value} WHERE id = :id", id=ids[1])
        return ids, await _verify()

    ids, verdict = run(scenario())
    assert verdict["valid"] is False and verdict["broken_at_event_id"] == str(ids[1])


def test_deleting_a_middle_entry_is_detected_by_sequence_gap(chain):
    async def scenario():
        ids = await _fill(4)
        await _raw("DELETE FROM audit_log WHERE id = :id", id=ids[1])
        return await _verify()

    verdict = run(scenario())
    assert verdict["valid"] is False and "gap" in verdict["message"]


def test_deleting_the_tail_is_detected_by_the_signed_head(chain):
    async def scenario():
        ids = await _fill(3)
        await _raw("DELETE FROM audit_log WHERE id = :id", id=ids[-1])
        return await _verify()

    verdict = run(scenario())
    assert verdict["valid"] is False and "tail" in verdict["message"]


def test_forged_head_without_the_key_is_rejected(chain):
    async def scenario():
        ids = await _fill(3)
        await _raw("DELETE FROM audit_log WHERE id = :id", id=ids[-1])
        await _raw(
            "UPDATE audit_chain_head SET last_seq = 3, "
            "last_hash = (SELECT event_hash FROM audit_log WHERE seq = 3) WHERE id = 1"
        )
        return await _verify()

    verdict = run(scenario())
    assert verdict["valid"] is False and "invalid" in verdict["message"]


def test_forking_prev_hash_is_detected(chain):
    async def scenario():
        ids = await _fill(3)
        await _raw("UPDATE audit_log SET prev_hash = 'x' WHERE id = :id", id=ids[2])
        return ids, await _verify()

    ids, verdict = run(scenario())
    assert verdict["valid"] is False and verdict["broken_at_event_id"] == str(ids[2])


def test_a_different_hmac_key_cannot_verify_the_chain(chain, monkeypatch):
    async def scenario():
        await _fill(2)
        monkeypatch.setattr(settings, "audit_hmac_key", "a-different-key")
        return await _verify()

    assert run(scenario())["valid"] is False


def test_tampered_legacy_archive_is_detected_via_baseline_fingerprint(chain):
    async def scenario():
        await _fill(1)
        before = await _verify()
        await _raw("UPDATE audit_log_legacy SET action = 'bi-sua' WHERE resource_id = 'old0'")
        return before, await _verify()

    before, after = run(scenario())
    assert before["valid"] is True
    assert after["valid"] is False and "archived" in after["message"]


def test_concurrent_appends_keep_one_linear_chain(chain):
    async def scenario():
        await asyncio.gather(
            *[
                audit_chain.record(principal_id=USER, action="wiki.update", resource_type="wiki_page",
                                   resource_id=f"p{i}", metadata={"n": i})
                for i in range(20)
            ]
        )
        async with async_session_factory() as session:
            return await audit_chain.verify_chain(session, batch_size=7)

    verdict = run(scenario())
    assert verdict["valid"] is True and verdict["total_events"] == 21


def test_trace_id_comes_from_request_context_and_is_hashed(chain):
    async def scenario():
        token = trace_context.set_trace_id("corr-abc-123")
        try:
            inside = await audit_chain.record(principal_id=USER, action="a", resource_type="r", resource_id="1")
        finally:
            trace_context.reset_trace_id(token)
        outside = await audit_chain.record(principal_id=USER, action="a", resource_type="r", resource_id="2")
        return inside, outside, await _verify()

    inside, outside, verdict = run(scenario())
    assert inside.trace_id == "corr-abc-123"
    assert outside.trace_id.startswith("tr-") and outside.trace_id != inside.trace_id
    assert verdict["valid"] is True


def test_log_audit_writes_through_the_chain(chain):
    from app.services.audit_service import log_audit

    class Employee:
        id = USER

    async def scenario():
        await log_audit(None, Employee(), "source.delete", "source", "s9", decision="ALLOW", reason="r")
        async with async_session_factory() as session:
            last = (await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))).scalar_one()
        return last, await _verify()

    last, verdict = run(scenario())
    assert last.action == "source.delete" and last.resource_id == "s9" and verdict["valid"] is True


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET action = 'x'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
        "UPDATE audit_log_legacy SET action = 'x'",
        "DELETE FROM audit_log_legacy",
        "DELETE FROM audit_chain_head",
    ],
)
def test_database_triggers_block_tampering(chain, statement):
    async def scenario():
        await _fill(1)
        async with engine.begin() as conn:
            await conn.execute(text(statement))

    with pytest.raises(Exception) as err:
        run(scenario())
    assert "append-only" in str(err.value)


def test_migration_downgrade_restores_the_old_table_and_upgrade_can_rerun(chain):
    async def scenario():
        await _migrate("downgrade")
        async with engine.connect() as conn:
            old_rows = (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar()
            has_seq = (
                await conn.execute(
                    text("SELECT 1 FROM information_schema.columns WHERE table_name='audit_log' AND column_name='seq'")
                )
            ).first()
        await _migrate("upgrade")
        return old_rows, has_seq

    old_rows, has_seq = run(scenario())
    assert old_rows == 2 and has_seq is None


def test_correlation_middleware_reuses_and_echoes_the_header():
    from app.services.trace_context import CorrelationIdMiddleware, get_trace_id

    seen = []

    async def inner(scope, receive, send):
        seen.append(get_trace_id())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def call(headers):
        sent = []

        async def go():
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            await CorrelationIdMiddleware(inner)({"type": "http", "headers": headers}, receive, send)

        asyncio.run(go())
        return dict(sent[0]["headers"])[b"x-correlation-id"].decode()

    assert call([(b"x-correlation-id", b"trace-xyz-1")]) == "trace-xyz-1"
    minted = call([])
    assert minted == seen[-1] and len(minted) >= 32
    assert get_trace_id() is None
