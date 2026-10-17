"""Baseline schema for c2 (final schema minus the audit hash chain, prompt templates and global_role_source).

Revision ID: 048_security_label_acl
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "048_security_label_acl"
down_revision = None
branch_labels = None
depends_on = None

DIMS = (768, 1024, 1536, 3072)
LABELS = "('PUBLIC', 'INTERNAL', 'RESTRICTED', 'CONFIDENTIAL')"
# Tables created by later revisions (or explicitly, in legacy form, below).
EXCLUDED_TABLES = {"audit_log", "audit_chain_head", "prompt_templates"}


def _orm_tables():
    from app.database.models import Base
    import app.database.oauth_models  # noqa: F401
    import app.models.concept_relation  # noqa: F401
    import app.models.task_failure  # noqa: F401

    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


def _opclass(dim: int) -> str:
    return "halfvec_cosine_ops" if dim == 3072 else "vector_cosine_ops"


def _fts(table: str, column: str = "text") -> str:
    return (
        f"CREATE INDEX IF NOT EXISTS ix_{table}_fts ON {table} "
        f"USING gin (to_tsvector('simple'::regconfig, f_unaccent(coalesce({column}, ''))))"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(64)")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        "CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS "
        "$func$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $func$"
    )

    bind = op.get_bind()
    tables = _orm_tables()
    from app.database.models import Base

    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # global_role_source belongs to revision 050.
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS global_role_source")

    # Legacy (pre hash chain) audit_log.
    # Columns as (name, type, required); order matches the original physical layout.
    legacy_audit_columns = [
        ("timestamp", sa.DateTime(timezone=True), True),
        ("principal_id", UUID(as_uuid=True), True),
        ("principal_type", sa.String(20), True),
        ("action", sa.String(50), True),
        ("resource_type", sa.String(50), True),
        ("resource_id", sa.String(100), True),
        ("scope_type", sa.String(20), False),
        ("scope_id", UUID(as_uuid=True), False),
        ("decision", sa.String(10), True),
        ("reason", sa.Text(), False),
        ("metadata", JSONB(), False),
    ]
    column_defaults = {"timestamp": sa.func.now(), "principal_type": "human"}
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        *(
            sa.Column(col_name, col_type, nullable=not required, server_default=column_defaults.get(col_name))
            for col_name, col_type, required in legacy_audit_columns
        ),
    )
    for idx_suffix, idx_columns in (
        ("timestamp", ["timestamp"]),
        ("principal", ["principal_id"]),
        ("resource", ["resource_type", "resource_id"]),
    ):
        op.create_index(f"ix_audit_log_{idx_suffix}", "audit_log", idx_columns)

    # Embedding indexes.
    for d in DIMS:
        opc = _opclass(d)
        for prefix in ("wiki_page_embeddings", "source_chunk_embeddings", "wiki_page_chunk_embeddings"):
            t = f"{prefix}_{d}"
            op.execute(
                f"CREATE INDEX IF NOT EXISTS ix_{t}_hnsw ON {t} USING hnsw (embedding {opc}) "
                "WITH (m = 16, ef_construction = 64)"
            )
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_model ON {t} (model_spec_id)")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_source_chunk_embeddings_{d}_source "
            f"ON source_chunk_embeddings_{d} (source_id)"
        )
        op.execute(_fts(f"source_chunk_embeddings_{d}"))
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_wiki_page_chunk_embeddings_{d}_page "
            f"ON wiki_page_chunk_embeddings_{d} (page_id)"
        )
        op.execute(_fts(f"wiki_page_chunk_embeddings_{d}"))

    # Other indexes.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sources_fulltext ON sources "
        "USING gin (to_tsvector('simple'::regconfig, f_unaccent(coalesce(full_text, ''))))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sources_security_label ON sources (security_label)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sources_content_hash ON sources (content_hash)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_departments_external_id ON departments (external_id) "
        "WHERE external_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_departments_code ON departments (code) WHERE code IS NOT NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_departments_parent_id ON departments (parent_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_mcp_token_hash ON employees (mcp_token_hash) "
        "WHERE mcp_token_hash IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_external_id ON employees (external_id) "
        "WHERE external_id IS NOT NULL"
    )

    # Constraints.
    op.execute(
        f"ALTER TABLE sources ADD CONSTRAINT ck_sources_security_label CHECK (security_label IN {LABELS})"
    )
    op.execute(
        f"ALTER TABLE employees ADD CONSTRAINT ck_employees_clearance_level CHECK (clearance_level IN {LABELS})"
    )
    op.execute(
        """
        DO $$
        DECLARE fk text;
        BEGIN
            SELECT conname INTO fk FROM pg_constraint
            WHERE conrelid = 'departments'::regclass AND contype = 'f'
              AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                  WHERE attrelid = 'departments'::regclass AND attname = 'parent_id')]::smallint[];
            IF fk IS NOT NULL AND fk <> 'fk_departments_parent_id' THEN
                EXECUTE format('ALTER TABLE departments DROP CONSTRAINT %I', fk);
                fk := NULL;
            END IF;
            IF fk IS NULL THEN
                ALTER TABLE departments ADD CONSTRAINT fk_departments_parent_id
                    FOREIGN KEY (parent_id) REFERENCES departments (id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # Seed knowledge types.
    op.execute(
        """
        INSERT INTO knowledge_types (id, slug, name, color, sort_order, description)
        VALUES
            (gen_random_uuid(), 'general', 'Chung', '#6B7280', 0, 'Tài liệu, quy định và thông tin chung'),
            (gen_random_uuid(), 'legal', 'Văn bản luật', '#DC2626', 1, 'Văn bản quy phạm pháp luật')
        ON CONFLICT (slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    bind = op.get_bind()
    from app.database.models import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_orm_tables())), checkfirst=True)
    op.execute("DROP TYPE IF EXISTS skill_status")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS vector")
