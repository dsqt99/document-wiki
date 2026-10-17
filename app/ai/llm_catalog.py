"""Preset LLM models selectable in Settings."""

from dataclasses import dataclass
from typing import Optional

from app.ai.custom_models import CUSTOM_PREFIX


class UnknownLLMModel(KeyError):
    pass


@dataclass(frozen=True)
class LLMModelSpec:
    id: str
    provider: str
    model_id: str
    context_window_tokens: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_vision: bool = True
    label: str = ""
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_1m_output_tokens: Optional[float] = None
    notes: Optional[str] = None


def _spec(spec_id: str, ctx: int, out: int, label: str, cin=None, cout=None, notes=None) -> LLMModelSpec:
    provider, _, model_id = spec_id.partition("/")
    return LLMModelSpec(
        id=spec_id,
        provider=provider,
        model_id=model_id,
        context_window_tokens=ctx,
        max_output_tokens=out,
        supports_tools=True,
        supports_vision=True,
        label=label,
        cost_per_1m_input_tokens=cin,
        cost_per_1m_output_tokens=cout,
        notes=notes,
    )


LLM_CATALOG: dict[str, LLMModelSpec] = {
    s.id: s
    for s in (
        _spec("openai/gpt-6-luna", 400000, 128000, "GPT-6 Luna"),
        _spec("anthropic/claude-sonnet-5-5", 1000000, 64000, "Claude Sonnet 5.5"),
        _spec("anthropic/claude-opus-5-5", 1000000, 64000, "Claude Opus 5.5"),
        _spec("anthropic/claude-haiku-5-5", 200000, 64000, "Claude Haiku 5.5"),
        _spec("google/gemini-3.1-pro", 1000000, 65000, "Gemini 3.1 Pro", 1.25, 10.0),
        _spec("google/gemini-3.5-flash", 1048576, 65536, "Gemini 3.5 Flash", 0.5, 3.0),
        _spec("google/gemini-3.1-flash-lite", 1048576, 65536, "Gemini 3.1 Flash Lite", 0.25, 1.50),
    )
}


def get_spec(spec_id: str) -> LLMModelSpec:
    if spec_id and spec_id.startswith(CUSTOM_PREFIX):
        model_id = spec_id[len(CUSTOM_PREFIX):]
        if model_id:
            return LLMModelSpec(
                id=spec_id,
                provider="custom",
                model_id=model_id,
                context_window_tokens=128000,
                max_output_tokens=8192,
                supports_tools=True,
                supports_vision=False,
                label=model_id,
            )
    spec = LLM_CATALOG.get(spec_id)
    if spec is None:
        raise UnknownLLMModel(
            f"Unknown LLM model spec_id={spec_id!r}. Valid IDs: {', '.join(LLM_CATALOG)}"
        )
    return spec


def list_specs() -> list[LLMModelSpec]:
    """All preset specs, in catalog order."""
    return [*LLM_CATALOG.values()]


def list_specs_by_provider(provider: str) -> list[LLMModelSpec]:
    """Preset specs whose provider equals ``provider``."""
    return list(filter(lambda item: item.provider == provider, LLM_CATALOG.values()))


def derive_spec_id(provider: Optional[str], model_id: Optional[str]) -> Optional[str]:
    """Map a (provider, model_id) pair back to a preset id, if one exists."""
    if provider and model_id:
        joined = "/".join((provider, model_id))
        if joined in LLM_CATALOG:
            return joined
    return None
