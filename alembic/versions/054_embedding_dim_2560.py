"""Add 2560-dimension embedding tables (e.g. Qwen3-Embedding-4B).

Revision ID: 054_embedding_dim_2560
Revises: 053_document_manager
"""

from alembic import op

revision = "054_embedding_dim_2560"
down_revision = "053_document_manager"
branch_labels = None
depends_on = None

DIM = 2560
PREFIXES = ("wiki_page_embeddings", "source_chunk_embeddings", "wiki_page_chunk_embeddings")


def _fts(table: str, column: str = "text") -> str:
    return (
        f"CREATE INDEX IF NOT EXISTS ix_{table}_fts ON {table} "
        f"USING gin (to_tsvector('simple'::regconfig, f_unaccent(coalesce({column}, ''))))"
    )


def upgrade() -> None:
    from app.database.models import Base

    tables = [Base.metadata.tables[f"{p}_{DIM}"] for p in PREFIXES]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables, checkfirst=True)

    # > 2000 dims is stored as halfvec, the only type HNSW can index at this size.
    for p in PREFIXES:
        t = f"{p}_{DIM}"
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{t}_hnsw ON {t} USING hnsw (embedding halfvec_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_model ON {t} (model_spec_id)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_source_chunk_embeddings_{DIM}_source "
        f"ON source_chunk_embeddings_{DIM} (source_id)"
    )
    op.execute(_fts(f"source_chunk_embeddings_{DIM}"))
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_wiki_page_chunk_embeddings_{DIM}_page "
        f"ON wiki_page_chunk_embeddings_{DIM} (page_id)"
    )
    op.execute(_fts(f"wiki_page_chunk_embeddings_{DIM}"))


def downgrade() -> None:
    for p in PREFIXES:
        op.execute(f"DROP TABLE IF EXISTS {p}_{DIM}")
