"""Preset embedding models. Each dimension maps to its own set of tables."""

from dataclasses import dataclass
from typing import Optional

from app.ai.custom_models import CUSTOM_PREFIX
from app.ai.custom_models import EMBEDDING_DIMENSIONS as _TABLE_DIMENSIONS


class UnknownEmbeddingModel(KeyError):
    pass


@dataclass(frozen=True)
class EmbeddingModelSpec:
    id: str
    provider: str
    model_id: str
    dimension: int
    max_input_tokens: int
    label: str = ""
    cost_per_1m_tokens: Optional[float] = None
    notes: Optional[str] = None


_PROVIDER_LABEL = {"google": "Google", "openai": "OpenAI"}


def _spec(spec_id: str, dim: int, max_in: int, cost: float) -> EmbeddingModelSpec:
    provider, _, model_id = spec_id.partition("/")
    return EmbeddingModelSpec(
        id=spec_id,
        provider=provider,
        model_id=model_id,
        dimension=dim,
        max_input_tokens=max_in,
        label=f"{_PROVIDER_LABEL.get(provider, provider)} {model_id} ({dim}d)",
        cost_per_1m_tokens=cost,
    )


EMBEDDING_CATALOG: dict[str, EmbeddingModelSpec] = {
    s.id: s
    for s in (
        _spec("google/gemini-embedding-001", 3072, 2048, 0.15),
        _spec("google/gemini-embedding-2", 3072, 8192, 0.15),
        _spec("openai/text-embedding-3-small", 1536, 8191, 0.02),
        _spec("openai/text-embedding-3-large", 3072, 8191, 0.13),
    )
}

# Dimensions that have tables (router name: EMBEDDING_DIMENSIONS).
EMBEDDING_DIMENSIONS: tuple[int, ...] = tuple(sorted(_TABLE_DIMENSIONS))
SUPPORTED_DIMENSIONS: tuple[int, ...] = EMBEDDING_DIMENSIONS
# Dimensions used by the preset catalog.
CATALOG_DIMENSIONS: tuple[int, ...] = tuple(sorted({s.dimension for s in EMBEDDING_CATALOG.values()}))


def _custom_spec(spec_id: str) -> Optional[EmbeddingModelSpec]:
    rest = spec_id[len(CUSTOM_PREFIX):]
    head, _, model_id = rest.partition("/")
    if not head.isdigit() or not model_id:
        return None
    dim = int(head)
    if dim not in EMBEDDING_DIMENSIONS:
        return None
    return EmbeddingModelSpec(
        id=spec_id,
        provider="custom",
        model_id=model_id,
        dimension=dim,
        max_input_tokens=8191,
        label=f"{model_id} ({dim}d)",
    )


def get_spec(spec_id: str) -> EmbeddingModelSpec:
    if spec_id and spec_id.startswith(CUSTOM_PREFIX):
        spec = _custom_spec(spec_id)
        if spec is not None:
            return spec
        raise UnknownEmbeddingModel(f"Unknown or unsupported custom embedding model spec_id={spec_id!r}")
    spec = EMBEDDING_CATALOG.get(spec_id)
    if spec is None:
        raise UnknownEmbeddingModel(
            f"Unknown embedding model spec_id={spec_id!r}. Valid IDs: {', '.join(EMBEDDING_CATALOG)}"
        )
    return spec


def list_specs() -> list[EmbeddingModelSpec]:
    return list(EMBEDDING_CATALOG.values())


def specs_for_dimension(dim: int) -> list[EmbeddingModelSpec]:
    return [s for s in EMBEDDING_CATALOG.values() if s.dimension == dim]
