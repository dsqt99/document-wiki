"""Create concept_relations table with closed predicates for concept graph.

Revision ID: 042_create_concept_relations_table
Revises: 041_create_legal_graph_tables
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "042_create_concept_relations_table"
down_revision = "041_create_legal_graph_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_concept", sa.String(255), nullable=False),
        sa.Column("target_concept", sa.String(255), nullable=False),
        sa.Column("predicate", sa.String(50), nullable=False, comment="la_mot, thuoc, quy_dinh, ap_dung_cho, lien_quan"),
        sa.Column("evidence", sa.Text(), nullable=True, comment="Verbatim sentence or phrase evidence for this relationship"),
        sa.Column("weight", sa.Float(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_concept_relations_source_id", "concept_relations", ["source_id"])
    op.create_index("ix_concept_relations_source_concept", "concept_relations", ["source_concept"])
    op.create_index("ix_concept_relations_target_concept", "concept_relations", ["target_concept"])
    op.create_index("ix_concept_relations_predicate", "concept_relations", ["predicate"])
    op.create_index("ix_concept_relations_source_page_id", "concept_relations", ["source_page_id"])
    op.create_index("ix_concept_relations_target_page_id", "concept_relations", ["target_page_id"])
    op.create_index("ix_concept_relations_pair", "concept_relations", ["source_concept", "target_concept"])


def downgrade() -> None:
    op.drop_table("concept_relations")
