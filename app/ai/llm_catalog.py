"""
LLM model catalog — code-level whitelist of supported text-generation models.

Presets the system ships with. Admins pick from these or add their own model
(base URL + model name, see app/ai/custom_models.py). Free-form IDs used to be
banned outright because they caused:

  1. Misspelled model_id → API call fails or silently routes to a fallback.
  2. Unknown context window → writer used a 60k-char fallback budget even for
     1M-token models, silently truncating source documents.
  3. Tool-call attempts on models that don't support function calling.

Adding a new model means adding an entry here. The catalog is the only place
where context window and capability metadata live — the rest of the codebase
queries the spec via ProviderRegistry instead of hard-coding model IDs.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMModelSpec:
    id: str                          # canonical "<provider>/<model_id>"
    provider: str                    # matches ProviderType: "openai" | "google" | "anthropic"
    model_id: str                    # ID sent to the provider API
    context_window_tokens: int       # total context window (input + output)
    max_output_tokens: int           # max output tokens per request
    supports_tools: bool             # true if model supports function calling
    supports_vision: bool            # true if model can accept image inputs
    label: str                       # short label shown in UI
    cost_per_1m_input_tokens: Optional[float]   # USD per 1M input tokens
    cost_per_1m_output_tokens: Optional[float]  # USD per 1M output tokens
    notes: Optional[str] = None


# All entries here must be reachable via their provider's SDK. When adding a
# new model, double-check context_window_tokens against the provider's docs —
# the writer uses ~60% of this for source text, so wrong values silently
# truncate documents.
LLM_CATALOG: dict[str, LLMModelSpec] = {
    "openai/gpt-6-luna": LLMModelSpec(
        id="openai/gpt-6-luna",
        provider="openai",
        model_id="gpt-6-luna",
        context_window_tokens=400_000,
        max_output_tokens=128_000,
        supports_tools=True,
        supports_vision=True,
        label="GPT-6 Luna",
        cost_per_1m_input_tokens=None,
        cost_per_1m_output_tokens=None,
    ),
    "anthropic/claude-sonnet-5-5": LLMModelSpec(
        id="anthropic/claude-sonnet-5-5",
        provider="anthropic",
        model_id="claude-sonnet-5-5",
        context_window_tokens=1_000_000,
        max_output_tokens=64_000,
        supports_tools=True,
        supports_vision=True,
        label="Claude Sonnet 5.5",
        cost_per_1m_input_tokens=None,
        cost_per_1m_output_tokens=None,
    ),
}


class UnknownLLMModel(KeyError):
    """Raised when a spec_id is not in the LLM catalog."""


def get_spec(spec_id: str) -> LLMModelSpec:
    from app.ai.custom_models import is_custom, parse_id

    if is_custom(spec_id):
        # Admin-added model (see app/ai/custom_models.py). Context window is
        # unknown, so use a conservative default for the writer's budget.
        _, model_id = parse_id(spec_id)
        return LLMModelSpec(
            id=spec_id, provider="custom", model_id=model_id,
            context_window_tokens=128_000, max_output_tokens=8_192,
            supports_tools=True, supports_vision=False, label=model_id,
            cost_per_1m_input_tokens=None, cost_per_1m_output_tokens=None,
        )
    try:
        return LLM_CATALOG[spec_id]
    except KeyError as e:
        raise UnknownLLMModel(
            f"Unknown LLM model spec_id={spec_id!r}. "
            f"Valid IDs: {sorted(LLM_CATALOG.keys())}"
        ) from e


def list_specs() -> list[LLMModelSpec]:
    return list(LLM_CATALOG.values())


def list_specs_by_provider(provider: str) -> list[LLMModelSpec]:
    return [s for s in LLM_CATALOG.values() if s.provider == provider]


def derive_spec_id(provider: str, model_id: str) -> Optional[str]:
    """
    Look up a spec_id from legacy (provider, model_id) config. Returns None
    if no spec matches — caller should treat that as 'unknown model, use
    fallbacks'. Used during the backward-compat migration from the old
    llm_provider+llm_model_id config keys.
    """
    for spec in LLM_CATALOG.values():
        if spec.provider == provider and spec.model_id == model_id:
            return spec.id
    return None
