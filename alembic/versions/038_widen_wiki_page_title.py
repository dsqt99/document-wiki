"""Widen wiki_pages and sources title columns to Text.

Revision ID: 038_widen_wiki_page_title
Revises: 037_hybrid_search
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "038_widen_wiki_page_title"
down_revision = "037_hybrid_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "wiki_pages",
        "title",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "sources",
        "title",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sources",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "wiki_pages",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
