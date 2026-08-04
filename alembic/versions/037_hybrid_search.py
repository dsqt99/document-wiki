"""Hybrid search: wiki_page_chunk_embeddings_<dim> + GIN full-text indexes.

Adds section-aligned chunk embedding tables for wiki pages (one row per section
instead of one vector per page) plus GIN full-text indexes so search can fuse
vector similarity with lexical (tsvector) matching:

  - wiki_page_chunk_embeddings_{768,1024,1536,3072}  (HNSW + GIN FTS on text)
  - GIN FTS index on source_chunk_embeddings_<dim>.text  (symmetric hybrid pool)
  - GIN FTS index on sources.full_text  (upgrades search_source_content)

Full-text uses the 'simple' config (no stemming — better for Vietnamese, per
migration 003) wrapped in an IMMUTABLE f_unaccent() so matching is
accent-insensitive. `unaccent` is only STABLE, so it must be wrapped to be
usable in an index expression.

The old per-page wiki_page_embeddings_<dim> tables are left intact but are no
longer written to or queried — kept for rollback safety.

Revision ID: 037_hybrid_search
Revises: 036_verbatim_sources
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "037_hybrid_search"
down_revision = "036_verbatim_sources"
branch_labels = None
depends_on = None


SUPPORTED_DIMENSIONS = (768, 1024, 1536, 3072)
_HALFVEC_DIMS = {3072}

_WIKI_TABLES = frozenset(f"wiki_page_chunk_embeddings_{d}" for d in SUPPORTED_DIMENSIONS)


def _wiki_table_name(dim: int) -> str:
    name = f"wiki_page_chunk_embeddings_{dim}"
    assert name in _WIKI_TABLES, f"Unexpected embedding table name: {name}"
    return name


def _embedding_column(dim: int):
    if dim in _HALFVEC_DIMS:
        return sa.Column("embedding", HALFVEC(dim), nullable=False)
    return sa.Column("embedding", Vector(dim), nullable=False)


def _hnsw_ops(dim: int) -> str:
    return "halfvec_cosine_ops" if dim in _HALFVEC_DIMS else "vector_cosine_ops"


def upgrade() -> None:
    # Accent-insensitive full-text: unaccent is STABLE, wrap it IMMUTABLE so it
    # can be used inside a GIN index expression.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text)
        RETURNS text AS
        $$ SELECT public.unaccent('public.unaccent', $1) $$
        LANGUAGE sql IMMUTABLE
        """
    )

    # --- Wiki page chunk embedding tables (mirror source_chunk_embeddings_<dim>) ---
    for dim in SUPPORTED_DIMENSIONS:
        table = _wiki_table_name(dim)
        op.create_table(
            table,
            sa.Column(
                "page_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("model_spec_id", sa.String(128), nullable=False),
            sa.Column("heading_path", sa.Text, nullable=False, server_default=""),
            sa.Column("text", sa.Text, nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            _embedding_column(dim),
            sa.Column(
                "embedded_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("page_id", "chunk_index", "model_spec_id"),
        )
        op.execute(
            f"""
            CREATE INDEX ix_{table}_hnsw
            ON {table}
            USING hnsw (embedding {_hnsw_ops(dim)})
            WITH (m = 16, ef_construction = 64)
            """
        )
        op.create_index(f"ix_{table}_model", table, ["model_spec_id"])
        op.create_index(f"ix_{table}_page", table, ["page_id"])
        op.execute(
            f"""
            CREATE INDEX ix_{table}_fts
            ON {table}
            USING GIN (to_tsvector('simple', f_unaccent(text)))
            """
        )

    # --- GIN FTS on verbatim source chunk text (symmetric hybrid pool) ---
    for dim in SUPPORTED_DIMENSIONS:
        table = f"source_chunk_embeddings_{dim}"
        op.execute(
            f"""
            CREATE INDEX ix_{table}_fts
            ON {table}
            USING GIN (to_tsvector('simple', f_unaccent(text)))
            """
        )

    # --- GIN FTS on sources.full_text (upgrades search_source_content) ---
    op.execute(
        """
        CREATE INDEX ix_sources_fulltext
        ON sources
        USING GIN (to_tsvector('simple', f_unaccent(full_text)))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sources_fulltext")

    for dim in SUPPORTED_DIMENSIONS:
        table = f"source_chunk_embeddings_{dim}"
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_fts")

    for dim in SUPPORTED_DIMENSIONS:
        table = _wiki_table_name(dim)
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_fts")
        op.drop_index(f"ix_{table}_page", table_name=table)
        op.drop_index(f"ix_{table}_model", table_name=table)
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_hnsw")
        op.drop_table(table)

    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
