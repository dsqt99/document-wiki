"""Separate document management from visibility and unify processing defaults."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "053_document_manager"
down_revision = "052_wiki_origin_tags"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sources", sa.Column("managing_department_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_sources_managing_department", "sources", "departments", ["managing_department_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sources_managing_department_id", "sources", ["managing_department_id"])
    # Only a single unambiguous existing visibility department can seed ownership.
    op.execute("""UPDATE sources s SET managing_department_id=d.department_id FROM
        (SELECT source_id,(array_agg(department_id))[1] department_id FROM source_departments
         GROUP BY source_id HAVING count(*)=1) d WHERE s.id=d.source_id""")
    op.execute("""UPDATE sources SET preserve_verbatim=false,
        metadata=jsonb_set(coalesce(metadata,'{}'::jsonb),'{processing_mode}','"auto"'::jsonb)""")


def downgrade():
    op.drop_index("ix_sources_managing_department_id", table_name="sources")
    op.drop_constraint("fk_sources_managing_department", "sources", type_="foreignkey")
    op.drop_column("sources", "managing_department_id")
