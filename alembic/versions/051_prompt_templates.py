"""Create prompt_templates.

Revision ID: 051_prompt_templates
Revises: 050_global_role_source
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "051_prompt_templates"
down_revision = "050_global_role_source"
branch_labels = None
depends_on = None


_TABLE = "prompt_templates"
_INDEXED = ("command", "owner_id", "external_ref")


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    empty_array = sa.text("'{}'")
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("command", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("tags", ARRAY(sa.String()), server_default=empty_array),
        sa.Column("scope_type", sa.String(20), server_default="personal"),
        sa.Column("department_ids", ARRAY(UUID(as_uuid=True)), server_default=empty_array),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(20), server_default="wiki"),
        sa.Column("external_ref", sa.String(200), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    for column in _INDEXED:
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])


def downgrade() -> None:
    op.drop_table("prompt_templates")
