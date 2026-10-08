"""
Embedding model catalog — code-level whitelist of supported embedding models.

This is the single source of truth for which embedding models the system
supports. Admins choose from this catalog (via the settings UI); they cannot
type free-form model IDs or dimensions, which previously caused two classes of
production bugs:

  1. Misspelled model_id → API call fails or silently uses a different model.
  2. Dimension mismatch → vectors stored with wrong shape, search broken.

Adding a new model means adding an entry here AND adding a per-dimension
SQLAlchemy table + Alembic migration if its `dimension` is not already
supported. See plan: app/ai/embedding_catalog.py for context.
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EmbeddingModelSpec:
    id: str                    # canonical: "<provider>/<model_id>", e.g. "openai/text-embedding-3-small"
    provider: str              # matches ProviderType: "openai" | "google" | ...
    model_id: str              # ID sent to the provider API: "text-embedding-3-small"
    dimension: int             # output vector dim — must match a wiki_page_embeddings_<dim> table
    max_input_tokens: int      # provider's per-request token cap (used for chunking budgets)
    label: str                 # short label shown in UI
    cost_per_1m_tokens: float | None  # USD per 1M input tokens; None = unknown / free
    notes: str | None = None   # short hint for admins


# All entries here MUST have a `dimension` value that has a matching
# `wiki_page_embeddings_<dim>` table in the database. Currently supported
# dimensions: 768, 1024, 1536, 3072.
EMBEDDING_CATALOG: dict[str, EmbeddingModelSpec] = {
    # --- OpenAI ---
    "openai/text-embedding-3-large": EmbeddingModelSpec(
        id="openai/text-embedding-3-large",
        provider="openai",
        model_id="text-embedding-3-large",
        dimension=3072,
        max_input_tokens=8191,
        label="OpenAI text-embedding-3-large (3072d)",
        cost_per_1m_tokens=0.13,
        notes="Highest quality OpenAI embedding. ~6.5x cost of 3-small.",
    ),
}


SUPPORTED_DIMENSIONS: tuple[int, ...] = tuple(
    sorted({s.dimension for s in EMBEDDING_CATALOG.values()})
)


class UnknownEmbeddingModel(KeyError):
    """Raised when a spec_id is not in the catalog."""


def get_spec(spec_id: str) -> EmbeddingModelSpec:
    from app.ai.custom_models import EMBEDDING_DIMENSIONS, is_custom, parse_id

    if is_custom(spec_id):
        # Admin-added model: "custom/<dim>/<model_id>" (see app/ai/custom_models.py).
        dimension, model_id = parse_id(spec_id)
        if dimension in EMBEDDING_DIMENSIONS:
            return EmbeddingModelSpec(
                id=spec_id, provider="custom", model_id=model_id, dimension=dimension,
                max_input_tokens=8191, label=f"{model_id} ({dimension}d)",
                cost_per_1m_tokens=None,
            )
    try:
        return EMBEDDING_CATALOG[spec_id]
    except KeyError as e:
        raise UnknownEmbeddingModel(
            f"Unknown embedding model spec_id={spec_id!r}. "
            f"Valid IDs: {sorted(EMBEDDING_CATALOG.keys())}"
        ) from e


def list_specs() -> list[EmbeddingModelSpec]:
    return list(EMBEDDING_CATALOG.values())


def list_specs_by_provider(provider: str) -> list[EmbeddingModelSpec]:
    return [s for s in EMBEDDING_CATALOG.values() if s.provider == provider]


def specs_for_dimension(dimension: int) -> Iterable[EmbeddingModelSpec]:
    return (s for s in EMBEDDING_CATALOG.values() if s.dimension == dimension)
