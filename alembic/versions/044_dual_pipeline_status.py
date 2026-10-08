"""Add dual pipeline branch status columns to sources table.

Revision ID: 044_dual_pipeline_status
Revises: 043_create_task_failures_table
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "044_dual_pipeline_status"
down_revision = "043_create_task_failures_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = {c["name"] for c in insp.get_columns("sources")}

    # Nhanh A (Chunking / Raw chunks)
    if "chunk_status" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("chunk_status", sa.String(50), server_default="pending", nullable=False),
        )
    if "chunk_progress" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("chunk_progress", sa.Integer(), server_default="0", nullable=False),
        )
    if "chunk_progress_message" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("chunk_progress_message", sa.String(500), nullable=True),
        )
    if "chunk_attempt_id" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("chunk_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "chunk_error_message" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("chunk_error_message", sa.Text(), nullable=True),
        )

    # Nhanh B (Wiki / Legal synthesis)
    if "wiki_status" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("wiki_status", sa.String(50), server_default="pending", nullable=False),
        )
    if "wiki_progress" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("wiki_progress", sa.Integer(), server_default="0", nullable=False),
        )
    if "wiki_progress_message" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("wiki_progress_message", sa.String(500), nullable=True),
        )
    if "wiki_attempt_id" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("wiki_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "wiki_error_message" not in existing_cols:
        op.add_column(
            "sources",
            sa.Column("wiki_error_message", sa.Text(), nullable=True),
        )

    # Backfill existing ready sources
    op.execute(
        """
        UPDATE sources
        SET chunk_status = CASE WHEN preserve_verbatim THEN 'ready' ELSE 'pending' END,
            wiki_status = CASE WHEN preserve_verbatim THEN 'skipped' WHEN status = 'ready' THEN 'ready' ELSE status END
        WHERE status = 'ready'
        """
    )


def downgrade() -> None:
    for col in [
        "wiki_error_message",
        "wiki_attempt_id",
        "wiki_progress_message",
        "wiki_progress",
        "wiki_status",
        "chunk_error_message",
        "chunk_attempt_id",
        "chunk_progress_message",
        "chunk_progress",
        "chunk_status",
    ]:
        op.drop_column("sources", col)
