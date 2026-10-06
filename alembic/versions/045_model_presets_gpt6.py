"""Point active LLM / vision / OCR settings at the new model presets.

The catalogs now ship only GPT-6 Luna and Claude Sonnet 5.5 (plus
admin-added "custom/..." models). Active ids that no longer exist are moved to
GPT-6 Luna; the registry does the same at runtime, this just makes the stored
value match what the UI shows. Data-only; embeddings are untouched.

Revision ID: 045_model_presets_gpt6
Revises: 044_dual_pipeline_status
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa

revision = "045_model_presets_gpt6"
down_revision = "044_dual_pipeline_status"
branch_labels = None
depends_on = None

PRESETS = ("openai/gpt-6-luna", "anthropic/claude-sonnet-5-5")


def upgrade() -> None:
    conn = op.get_bind()
    for key in ("active_llm_model_spec_id", "active_vision_model_spec_id"):
        conn.execute(
            sa.text(
                "UPDATE app_config SET value = 'openai/gpt-6-luna', updated_at = now() "
                "WHERE key = :key AND value IS NOT NULL AND value <> '' "
                "AND value NOT IN :presets AND value NOT LIKE 'custom/%'"
            ).bindparams(sa.bindparam("presets", expanding=True)),
            {"key": key, "presets": list(PRESETS)},
        )
    # OCR used the old OpenAI model name directly.
    conn.execute(
        sa.text(
            "UPDATE app_config SET value = 'gpt-6-luna', updated_at = now() "
            "WHERE key = 'ocr_model' AND value LIKE 'gpt-5%'"
        )
    )


def downgrade() -> None:
    # Old model ids are gone from the catalogs; nothing to restore.
    pass
