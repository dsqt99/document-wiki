"""Create legal_units and legal_relations tables for Vietnamese legal knowledge graph.

Revision ID: 041_create_legal_graph_tables
Revises: 040_add_content_hash_and_attempt_id
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_create_legal_graph_tables"
down_revision = "040_add_content_hash_and_attempt_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create legal_units table
    op.create_table(
        "legal_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wiki_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit_type", sa.String(20), nullable=False, comment="part, chapter, section, article, clause, point"),
        sa.Column("unit_number", sa.String(50), nullable=False, comment="e.g. '1', '5a', 'I', 'a'"),
        sa.Column("title", sa.String(500), nullable=True, comment="Heading title of the unit if available"),
        sa.Column("full_path", sa.String(500), nullable=False, server_default="", comment="Hierarchical path: 'Chương I > Điều 1 > Khoản 2'"),
        sa.Column("content", sa.Text(), nullable=False, server_default="", comment="Verbatim text content of this unit"),
        sa.Column("parent_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_units.id", ondelete="CASCADE"), nullable=True),
        sa.Column("doc_number", sa.String(100), nullable=True, comment="Doc number e.g. 136/2020/NĐ-CP"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_legal_units_source_id", "legal_units", ["source_id"])
    op.create_index("ix_legal_units_wiki_page_id", "legal_units", ["wiki_page_id"])
    op.create_index("ix_legal_units_unit_type", "legal_units", ["unit_type"])
    op.create_index("ix_legal_units_unit_number", "legal_units", ["unit_number"])
    op.create_index("ix_legal_units_parent_unit_id", "legal_units", ["parent_unit_id"])
    op.create_index("ix_legal_units_doc_number", "legal_units", ["doc_number"])
    op.create_index("ix_legal_units_lookup", "legal_units", ["doc_number", "unit_type", "unit_number"])

    # 2. Create legal_relations table
    op.create_table(
        "legal_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_doc_number", sa.String(100), nullable=True, comment="Target doc number e.g. 136/2020/NĐ-CP"),
        sa.Column("target_article_number", sa.String(50), nullable=True, comment="Target article number e.g. '5', '5a'"),
        sa.Column("target_clause_number", sa.String(50), nullable=True, comment="Target clause number e.g. '1', '2'"),
        sa.Column("relation_type", sa.String(30), nullable=False, comment="sua_doi, bo_sung, thay_the, bai_bo, huong_dan, can_cu, dan_chieu"),
        sa.Column("quote_context", sa.Text(), nullable=True, comment="Extracted sentence or clause mentioning this relationship"),
        sa.Column("is_effective", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_legal_relations_source_unit_id", "legal_relations", ["source_unit_id"])
    op.create_index("ix_legal_relations_target_unit_id", "legal_relations", ["target_unit_id"])
    op.create_index("ix_legal_relations_target_doc_number", "legal_relations", ["target_doc_number"])
    op.create_index("ix_legal_relations_target_article_number", "legal_relations", ["target_article_number"])
    op.create_index("ix_legal_relations_relation_type", "legal_relations", ["relation_type"])
    op.create_index("ix_legal_relations_is_effective", "legal_relations", ["is_effective"])
    op.create_index("ix_legal_relations_target_lookup", "legal_relations", ["target_doc_number", "target_article_number"])


def downgrade() -> None:
    op.drop_table("legal_relations")
    op.drop_table("legal_units")
