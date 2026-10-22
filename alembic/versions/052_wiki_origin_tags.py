"""Persist Wiki extraction / generation origins and classify known legacy pages."""
import sqlalchemy as sa
from alembic import op

revision = "052_wiki_origin_tags"
down_revision = "051_prompt_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("wiki_pages", sa.Column("origin_tag", sa.String(20), nullable=True))
    op.create_check_constraint("ck_wiki_pages_origin_tag", "wiki_pages", "origin_tag IN ('extracted', 'generated')")
    op.create_index("ix_wiki_pages_origin_scope", "wiki_pages", ["origin_tag", "scope_type", "scope_id"])
    op.execute("""
        UPDATE wiki_pages w SET origin_tag='generated'
        WHERE w.slug NOT IN ('_index','_log','_hot') AND EXISTS (
          SELECT 1 FROM source_compilation_plans p,
          LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(p.plan_json->'_page_drafts')='array'
              THEN p.plan_json->'_page_drafts' WHEN jsonb_typeof(p.plan_json->'pages')='array'
              THEN p.plan_json->'pages' ELSE '[]'::jsonb END) item
          WHERE p.source_id=ANY(w.source_ids) AND item->>'slug'=w.slug)
    """)
    op.execute("""
        UPDATE wiki_pages w SET origin_tag='extracted'
        WHERE w.slug NOT IN ('_index','_log','_hot') AND (
          EXISTS (SELECT 1 FROM legal_units u WHERE u.wiki_page_id=w.id)
          OR (cardinality(w.source_ids)>0 AND (
             (w.slug ~ '^dieu-[0-9]' AND w.content_md LIKE '%**Căn cứ pháp lý**:%')
             OR w.content_md LIKE '%## Danh mục các Điều (%'
             OR w.content_md LIKE '%nguyên văn, không qua biên soạn LLM%'))
          OR EXISTS (SELECT 1 FROM sources s WHERE s.id=ANY(w.source_ids)
             AND (w.slug LIKE '%-'||left(s.id::text,8) OR w.slug LIKE '%-'||left(s.id::text,8)||'-phan-%')))
    """)
    # Older private-source pages could have been stored as global. Do not make
    # those pages eligible for cross-document machine merging by guessing a tag.
    op.execute("""
        UPDATE wiki_pages w SET origin_tag=NULL WHERE w.scope_type!='personal'
        AND EXISTS (SELECT 1 FROM sources s WHERE s.id=ANY(w.source_ids) AND s.scope_type='personal')
    """)


def downgrade():
    op.drop_index("ix_wiki_pages_origin_scope", table_name="wiki_pages")
    op.drop_constraint("ck_wiki_pages_origin_tag", "wiki_pages", type_="check")
    op.drop_column("wiki_pages", "origin_tag")
