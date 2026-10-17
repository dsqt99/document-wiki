"""Add employees.global_role_source and normalise legacy model ids.

Revision ID: 050_global_role_source
Revises: 049_audit_hash_chain
"""

import sqlalchemy as sa
from alembic import op

revision = "050_global_role_source"
down_revision = "049_audit_hash_chain"
branch_labels = None
depends_on = None

DEFAULT_MODEL = "openai/gpt-6-luna"


def _catalog_ids() -> list[str]:
    from app.ai.llm_catalog import LLM_CATALOG
    from app.ai.vision_catalog import VISION_CATALOG

    return sorted(set(LLM_CATALOG) | set(VISION_CATALOG))


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("global_role_source", sa.String(10), nullable=False, server_default="manual"),
    )
    op.create_check_constraint(
        "ck_employees_global_role_source", "employees", "global_role_source IN ('sso', 'manual')"
    )

    stmt = sa.text(
        "UPDATE app_config SET value = :default WHERE key IN "
        "('active_llm_model_spec_id', 'active_vision_model_spec_id') "
        "AND value IS NOT NULL AND value <> '' AND value NOT LIKE 'custom/%' "
        "AND NOT (value = ANY(:known))"
    ).bindparams(sa.bindparam("known", type_=sa.ARRAY(sa.String)))
    op.get_bind().execute(stmt, {"default": DEFAULT_MODEL, "known": _catalog_ids()})
    op.execute("UPDATE app_config SET value = 'gpt-6-luna' WHERE key = 'ocr_model' AND value LIKE 'gpt-5%'")
    op.execute(
        "UPDATE employees SET global_role_source = 'sso' "
        "WHERE external_id IS NOT NULL AND global_role <> 'admin'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_employees_global_role_source", "employees", type_="check")
    op.drop_column("employees", "global_role_source")
