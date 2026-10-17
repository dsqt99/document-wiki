"""Move audit_log to an append-only HMAC hash chain; archive legacy rows.

Revision ID: 049_audit_hash_chain
Revises: 048_security_label_acl
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "049_audit_hash_chain"
down_revision = "048_security_label_acl"
branch_labels = None
depends_on = None

MIGRATION_LOCK_KEY = 7420501004
_INDEX_SUFFIXES = ("timestamp", "principal", "resource")


def upgrade() -> None:
    op.execute(f"SELECT pg_advisory_xact_lock({MIGRATION_LOCK_KEY})")

    op.execute("ALTER TABLE audit_log RENAME TO audit_log_legacy")
    op.execute("ALTER INDEX IF EXISTS audit_log_pkey RENAME TO audit_log_legacy_pkey")
    for suffix in _INDEX_SUFFIXES:
        op.execute(f"ALTER INDEX IF EXISTS ix_audit_log_{suffix} RENAME TO ix_audit_log_legacy_{suffix}")

    def required(name: str, type_, **extra) -> sa.Column:
        return sa.Column(name, type_, nullable=False, **extra)

    def optional(name: str, type_) -> sa.Column:
        return sa.Column(name, type_, nullable=True)

    hash_col = sa.String(64)
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        required("seq", sa.BigInteger(), unique=True),
        required("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        required("principal_id", UUID(as_uuid=True)),
        sa.Column("principal_type", sa.String(20), server_default="human"),
        *(required(name, sa.String(width)) for name, width in (
            ("action", 50), ("resource_type", 50), ("resource_id", 100), ("decision", 10),
        )),
        optional("reason", sa.Text()),
        optional("metadata", JSONB()),
        required("trace_id", hash_col),
        optional("prev_hash", hash_col),
        optional("event_hash", hash_col),
    )
    audit_indexes = {
        "timestamp": ["timestamp"],
        "principal": ["principal_id"],
        "resource": ["resource_type", "resource_id"],
        "trace_id": ["trace_id"],
    }
    for idx_suffix, idx_columns in audit_indexes.items():
        op.create_index(f"ix_audit_log_{idx_suffix}", "audit_log", idx_columns)

    op.create_table(
        "audit_chain_head",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("last_seq", sa.BigInteger, nullable=True),
        sa.Column("last_hash", sa.String(64), nullable=True),
        sa.Column("key_fingerprint", sa.String(16), nullable=True),
        sa.Column("signature", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_guard_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit tables are append-only (% on %)', TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    for table in ("audit_log", "audit_log_legacy"):
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION audit_guard_immutable()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_guard_immutable()"
        )
    op.execute(
        "CREATE TRIGGER audit_chain_head_no_delete BEFORE DELETE ON audit_chain_head "
        "FOR EACH ROW EXECUTE FUNCTION audit_guard_immutable()"
    )
    op.execute(
        "CREATE TRIGGER audit_chain_head_no_truncate BEFORE TRUNCATE ON audit_chain_head "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_guard_immutable()"
    )


def downgrade() -> None:
    op.execute(f"SELECT pg_advisory_xact_lock({MIGRATION_LOCK_KEY})")
    for table in ("audit_log", "audit_log_legacy"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.execute("DROP TRIGGER IF EXISTS audit_chain_head_no_delete ON audit_chain_head")
    op.execute("DROP TRIGGER IF EXISTS audit_chain_head_no_truncate ON audit_chain_head")
    op.execute("DROP FUNCTION IF EXISTS audit_guard_immutable()")
    op.execute("DROP TABLE IF EXISTS audit_chain_head")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("ALTER TABLE audit_log_legacy RENAME TO audit_log")
    op.execute("ALTER INDEX IF EXISTS audit_log_legacy_pkey RENAME TO audit_log_pkey")
    for suffix in _INDEX_SUFFIXES:
        op.execute(f"ALTER INDEX IF EXISTS ix_audit_log_legacy_{suffix} RENAME TO ix_audit_log_{suffix}")
