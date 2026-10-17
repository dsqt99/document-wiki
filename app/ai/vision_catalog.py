"""Preset vision (image understanding) models."""

from dataclasses import dataclass
from typing import Optional

from app.ai.custom_models import CUSTOM_PREFIX


class UnknownVisionModel(KeyError):
    pass


@dataclass(frozen=True)
class VisionModelSpec:
    id: str
    provider: str
    model_id: str
    max_image_size_mb: int = 20
    label: str = ""
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_image: Optional[float] = None
    notes: Optional[str] = None


def _spec(spec_id: str, max_mb: int, label: str, cin=None) -> VisionModelSpec:
    provider, _, model_id = spec_id.partition("/")
    return VisionModelSpec(
        id=spec_id, provider=provider, model_id=model_id, max_image_size_mb=max_mb,
        label=label, cost_per_1m_input_tokens=cin,
    )


VISION_CATALOG: dict[str, VisionModelSpec] = {
    s.id: s
    for s in (
        _spec("openai/gpt-6-luna", 20, "GPT-6 Luna"),
        _spec("anthropic/claude-sonnet-5-5", 5, "Claude Sonnet 5.5"),
        _spec("anthropic/claude-haiku-5-5", 5, "Claude Haiku 5.5"),
        _spec("google/gemini-3.5-flash", 20, "Gemini 3.5 Flash"),
        _spec("google/gemini-3.1-flash-lite", 20, "Gemini 3.1 Flash Lite", 0.25),
    )
}


def get_spec(spec_id: str) -> VisionModelSpec:
    if spec_id and spec_id.startswith(CUSTOM_PREFIX):
        model_id = spec_id[len(CUSTOM_PREFIX):]
        if model_id:
            return VisionModelSpec(
                id=spec_id, provider="custom", model_id=model_id, max_image_size_mb=20, label=model_id
            )
    spec = VISION_CATALOG.get(spec_id)
    if spec is None:
        raise UnknownVisionModel(
            f"Unknown vision model spec_id={spec_id!r}. Valid IDs: {', '.join(VISION_CATALOG)}"
        )
    return spec


def list_specs() -> list[VisionModelSpec]:
    """All preset specs, in catalog order."""
    return [*VISION_CATALOG.values()]


def list_specs_by_provider(provider: str) -> list[VisionModelSpec]:
    """Preset specs whose provider equals ``provider``."""
    return list(filter(lambda item: item.provider == provider, VISION_CATALOG.values()))


def derive_spec_id(provider: Optional[str], model_id: Optional[str]) -> Optional[str]:
    """Map a (provider, model_id) pair back to a preset id, if one exists."""
    if provider and model_id:
        joined = "/".join((provider, model_id))
        if joined in VISION_CATALOG:
            return joined
    return None
