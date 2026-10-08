"""Create task_failures and source_stage_timings tables.

Revision ID: 043_create_task_failures_table
Revises: 042_create_concept_relations_table
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "043_create_task_failures_table"
down_revision = "042_create_concept_relations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 1. task_failures table
    if not insp.has_table("task_failures"):
        op.create_table(
        "task_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_id", sa.String(100), nullable=True),
        sa.Column("task_name", sa.String(100), nullable=False),
        sa.Column("error_type", sa.String(255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_task_failures_source_id", "task_failures", ["source_id"])
    op.create_index("ix_task_failures_task_name", "task_failures", ["task_name"])
    op.create_index("ix_task_failures_status", "task_failures", ["status"])
    op.create_index("ix_task_failures_status_created", "task_failures", ["status", "created_at"])

    # 2. source_stage_timings table
    if not insp.has_table("source_stage_timings"):
        op.create_table(
        "source_stage_timings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_source_stage_timings_source_id", "source_stage_timings", ["source_id"])
    op.create_index("ix_source_stage_timings_stage_name", "source_stage_timings", ["stage_name"])
    op.create_index("ix_source_stage_timings_source_stage", "source_stage_timings", ["source_id", "stage_name"])


def downgrade() -> None:
    op.drop_table("source_stage_timings")
    op.drop_table("task_failures")
