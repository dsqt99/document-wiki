"""Add content_hash and attempt_id to sources table.

Revision ID: 040_add_content_hash_and_attempt_id
Revises: 039_seed_default_knowledge_types
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "040_content_hash_attempt_id"
down_revision = "039_seed_default_knowledge_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen alembic_version.version_num to prevent VARCHAR(32) limit overflow
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE character varying(64)")

    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = {c["name"] for c in insp.get_columns("sources")}

    # Add content_hash column if not present
    if "content_hash" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column(
                "content_hash",
                sa.String(64),
                nullable=True,
                comment="SHA-256 hash of file content stream for deduplication",
            ),
        )
        op.create_index("ix_sources_content_hash", "sources", ["content_hash"])

    # Add attempt_id column if not present
    if "attempt_id" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column(
                "attempt_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                server_default=sa.text("gen_random_uuid()"),
                comment="Attempt UUID regenerated on every retry/reparse for task idempotency",
            ),
        )


def downgrade() -> None:
    op.drop_index("ix_sources_content_hash", table_name="sources")
    op.drop_column("sources", "content_hash")
    op.drop_column("sources", "attempt_id")
