"""Seed default knowledge types: general (Chung) and legal (Văn bản luật).

Revision ID: 039_seed_default_knowledge_types
Revises: 038_widen_wiki_page_title
Create Date: 2026-09-24
"""

from alembic import op

revision = "039_seed_default_knowledge_types"
down_revision = "038_widen_wiki_page_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Seed default knowledge types if not already present
    op.execute("""
        INSERT INTO knowledge_types (id, slug, name, color, sort_order, description, created_at)
        VALUES
            (gen_random_uuid(), 'general', 'Chung', '#6B7280', 0, 'Tài liệu, quy định và thông tin chung', NOW())
        ON CONFLICT (slug) DO NOTHING;
    """)
    op.execute("""
        INSERT INTO knowledge_types (id, slug, name, color, sort_order, description, created_at)
        VALUES
            (gen_random_uuid(), 'legal', 'Văn bản luật', '#DC2626', 1, 'Văn bản quy phạm pháp luật, nghị định, thông tư (tự động bóc tách theo Điều)', NOW())
        ON CONFLICT (slug) DO NOTHING;
    """)


def downgrade() -> None:
    pass
