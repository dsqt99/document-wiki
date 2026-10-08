"""
Vision model catalog — code-level whitelist of supported vision/image models.

Used by the image-captioning task during document ingestion. Captures cost
metadata so the cost dashboard can attribute spend per source.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VisionModelSpec:
    id: str                          # canonical "<provider>/<model_id>"
    provider: str                    # "openai" | "google"
    model_id: str                    # ID sent to the provider API
    max_image_size_mb: int           # provider's per-image size cap
    label: str
    cost_per_1m_input_tokens: Optional[float]
    cost_per_image: Optional[float]  # USD per image when provider charges flat
    notes: Optional[str] = None


VISION_CATALOG: dict[str, VisionModelSpec] = {
    "openai/gpt-6-luna": VisionModelSpec(
        id="openai/gpt-6-luna",
        provider="openai",
        model_id="gpt-6-luna",
        max_image_size_mb=20,
        label="GPT-6 Luna",
        cost_per_1m_input_tokens=None,
        cost_per_image=None,
    ),
    # Called through Anthropic's OpenAI-compatible endpoint (see registry).
    "anthropic/claude-sonnet-5-5": VisionModelSpec(
        id="anthropic/claude-sonnet-5-5",
        provider="anthropic",
        model_id="claude-sonnet-5-5",
        max_image_size_mb=5,
        label="Claude Sonnet 5.5",
        cost_per_1m_input_tokens=None,
        cost_per_image=None,
    ),
}


class UnknownVisionModel(KeyError):
    """Raised when a spec_id is not in the vision catalog."""


def get_spec(spec_id: str) -> VisionModelSpec:
    from app.ai.custom_models import is_custom, parse_id

    if is_custom(spec_id):
        _, model_id = parse_id(spec_id)
        return VisionModelSpec(
            id=spec_id, provider="custom", model_id=model_id, max_image_size_mb=20,
            label=model_id, cost_per_1m_input_tokens=None, cost_per_image=None,
        )
    try:
        return VISION_CATALOG[spec_id]
    except KeyError as e:
        raise UnknownVisionModel(
            f"Unknown vision model spec_id={spec_id!r}. "
            f"Valid IDs: {sorted(VISION_CATALOG.keys())}"
        ) from e


def list_specs() -> list[VisionModelSpec]:
    return list(VISION_CATALOG.values())


def list_specs_by_provider(provider: str) -> list[VisionModelSpec]:
    return [s for s in VISION_CATALOG.values() if s.provider == provider]


def derive_spec_id(provider: str, model_id: str) -> Optional[str]:
    """Look up a spec_id from legacy (provider, model_id) config."""
    for spec in VISION_CATALOG.values():
        if spec.provider == provider and spec.model_id == model_id:
            return spec.id
    return None
