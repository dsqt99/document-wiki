"""Builds provider instances from the configuration stored in app_config.

ProviderRegistry is bound to a session: ``ProviderRegistry(db).get_llm()``.
Callers import the class name (module level or lazily) so tests can patch it.
"""

import logging
from dataclasses import asdict
from typing import Optional

from app.ai import custom_models as cm
from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    ProviderType,
    VisionProvider,
)

logger = logging.getLogger(__name__)

ANTHROPIC_OPENAI_BASE_URL = "https://api.anthropic.com/v1/"
DEFAULT_LLM_SPEC_ID = "openai/gpt-6-luna"
DEFAULT_VISION_SPEC_ID = DEFAULT_LLM_SPEC_ID

_PROVIDER_NAMES = {
    "google": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "ollama": "Ollama",
    "voyage": "Voyage AI",
    "cohere": "Cohere",
}

_MODEL_FIELDS = (
    "id", "model_id", "label", "context_window_tokens", "max_output_tokens",
    "supports_tools", "supports_vision", "dimension", "max_input_tokens",
    "cost_per_1m_tokens", "cost_per_1m_input_tokens", "cost_per_1m_output_tokens", "notes",
)


def _model_entry(spec) -> dict:
    data = asdict(spec)
    return {k: data[k] for k in _MODEL_FIELDS if k in data and data[k] is not None}


def _build_supported() -> dict:
    from app.ai import embedding_catalog, llm_catalog, vision_catalog

    out: dict[str, list] = {}
    for kind, module in (("embedding", embedding_catalog), ("llm", llm_catalog), ("vision", vision_catalog)):
        groups: dict[str, list] = {}
        for spec in module.list_specs():
            groups.setdefault(spec.provider, []).append(_model_entry(spec))
        out[kind] = [
            {"id": p, "name": _PROVIDER_NAMES.get(p, p), "models": models}
            for p, models in groups.items()
        ]
    return out


SUPPORTED_PROVIDERS = _build_supported()


def _legacy_key_fits(key: Optional[str], provider: str) -> bool:
    if not key:
        return False
    if key.startswith("sk-ant-"):
        return provider == "anthropic"
    return provider != "anthropic"


def _protocol_provider(protocol: str) -> ProviderType:
    return ProviderType.ANTHROPIC if protocol == "anthropic" else ProviderType.OPENAI


def _config_service(db):
    from app.services import config_service

    return config_service.ConfigService(db)


class ProviderRegistry:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ helpers
    async def _get(self, key: str) -> Optional[str]:
        return await _config_service(self.db).get(key)

    async def _custom_config(self, kind: str, spec_id: str) -> ProviderConfig:
        model = await cm.get_custom(self.db, kind, spec_id)
        if model is None:
            raise ValueError(f"Custom model {spec_id} was deleted. Pick another model in Settings.")
        api_key = await cm.resolve_api_key(self.db, model) or "none"
        cfg = ProviderConfig(
            provider=_protocol_provider(model.protocol),
            api_key=api_key,
            model_id=model.model_id,
            base_url=model.base_url,
            extra={"spec_id": spec_id, "custom": True},
        )
        if kind == "embedding":
            cfg.dimensions = model.dimension
            cfg.extra["send_dimensions"] = False
        return cfg

    async def _preset_key(self, kind: str, provider: str) -> str:
        key = await self._get(f"{kind}_api_key__{provider}")
        if key:
            return key
        legacy = await self._get(f"{kind}_api_key")
        return legacy if _legacy_key_fits(legacy, provider) else ""

    # ------------------------------------------------------------- config load
    async def _load_embedding_config(self, spec_id: Optional[str] = None) -> ProviderConfig:
        from app.ai.embedding_catalog import get_spec

        spec_id = spec_id or await self.get_active_embedding_spec_id()
        if not spec_id:
            raise ValueError("No active embedding model. Pick one in Settings → Embedding.")
        if cm.is_custom(spec_id):
            return await self._custom_config("embedding", spec_id)
        spec = get_spec(spec_id)
        key = await self._get(f"embedding_api_key__{spec.provider}") or await self._get("embedding_api_key") or ""
        return ProviderConfig(
            provider=ProviderType(spec.provider),
            api_key=key,
            model_id=spec.model_id,
            base_url=await self._get("embedding_base_url") or None,
            dimensions=spec.dimension,
            extra={"spec_id": spec_id},
            spec=spec,
        )

    async def _load_llm_config(self, spec_id: Optional[str] = None) -> ProviderConfig:
        from app.ai.llm_catalog import get_spec

        spec_id = spec_id or await self.get_active_llm_spec_id()
        if not spec_id:
            raise ValueError("No active LLM. Pick one in Settings → LLM.")
        if cm.is_custom(spec_id):
            return await self._custom_config("llm", spec_id)
        spec = get_spec(spec_id)
        return ProviderConfig(
            provider=ProviderType(spec.provider),
            api_key=await self._preset_key("llm", spec.provider),
            model_id=spec.model_id,
            base_url=None,
            extra={"spec_id": spec_id},
            spec=spec,
        )

    async def _load_vision_config(self, spec_id: Optional[str] = None) -> ProviderConfig:
        from app.ai.vision_catalog import get_spec

        spec_id = spec_id or await self.get_active_vision_spec_id()
        if not spec_id:
            raise ValueError("No active vision model. Pick one in Settings → Vision.")
        if cm.is_custom(spec_id):
            return await self._custom_config("vision", spec_id)
        spec = get_spec(spec_id)
        return ProviderConfig(
            provider=ProviderType(spec.provider),
            api_key=await self._preset_key("vision", spec.provider),
            model_id=spec.model_id,
            base_url=ANTHROPIC_OPENAI_BASE_URL if spec.provider == "anthropic" else None,
            extra={"spec_id": spec_id},
            spec=spec,
        )

    # ---------------------------------------------------------- active spec id
    async def _custom_exists(self, kind: str, spec_id: str) -> bool:
        return await cm.get_custom(self.db, kind, spec_id) is not None

    async def get_active_embedding_spec_id(self) -> Optional[str]:
        from app.ai.embedding_catalog import EMBEDDING_CATALOG
        from app.services.config_service import ACTIVE_EMBEDDING_MODEL_KEY

        value = await self._get(ACTIVE_EMBEDDING_MODEL_KEY)
        if not value:
            return None
        if value in EMBEDDING_CATALOG:
            return value
        if cm.is_custom(value) and await self._custom_exists("embedding", value):
            return value
        return None

    async def _active_spec(self, kind, key, catalog, derive, legacy_provider, legacy_model, default) -> Optional[str]:
        value = await self._get(key)
        if value:
            if value in catalog:
                return value
            if cm.is_custom(value) and await self._custom_exists(kind, value):
                return value
        derived = derive(await self._get(legacy_provider), await self._get(legacy_model))
        if derived and derived in catalog:
            return derived
        if value:
            logger.warning("Active %s model %r is no longer available; using %s", kind, value, default)
            return default
        return None

    async def get_active_llm_spec_id(self) -> Optional[str]:
        from app.ai.llm_catalog import LLM_CATALOG, derive_spec_id
        from app.services.config_service import ACTIVE_LLM_MODEL_KEY

        return await self._active_spec(
            "llm", ACTIVE_LLM_MODEL_KEY, LLM_CATALOG, derive_spec_id,
            "llm_provider", "llm_model_id", DEFAULT_LLM_SPEC_ID,
        )

    async def get_active_vision_spec_id(self) -> Optional[str]:
        from app.ai.vision_catalog import VISION_CATALOG, derive_spec_id
        from app.services.config_service import ACTIVE_VISION_MODEL_KEY

        return await self._active_spec(
            "vision", ACTIVE_VISION_MODEL_KEY, VISION_CATALOG, derive_spec_id,
            "vision_provider", "vision_model_id", DEFAULT_VISION_SPEC_ID,
        )

    # --------------------------------------------------------------- builders
    async def get_embedding(self, task: str = "document", spec_id: Optional[str] = None) -> EmbeddingProvider:
        cfg = await self._load_embedding_config(spec_id=spec_id)
        cfg.extra["task"] = task
        if cfg.provider == ProviderType.GOOGLE:
            from app.ai.providers.google_provider import GoogleEmbedding

            return GoogleEmbedding(cfg)
        if cfg.provider == ProviderType.OPENAI:
            from app.ai.providers.openai_provider import OpenAIEmbedding

            return OpenAIEmbedding(cfg)
        raise ValueError(f"Unsupported embedding provider: {cfg.provider.value}")

    async def get_llm(self, spec_id: Optional[str] = None) -> LLMProvider:
        cfg = await self._load_llm_config(spec_id=spec_id)
        if cfg.provider == ProviderType.GOOGLE:
            from app.ai.providers.google_provider import GoogleLLM

            return GoogleLLM(cfg)
        if cfg.provider == ProviderType.OPENAI:
            from app.ai.providers.openai_provider import OpenAILLM

            return OpenAILLM(cfg)
        if cfg.provider == ProviderType.ANTHROPIC:
            from app.ai.providers.anthropic_provider import AnthropicLLM

            return AnthropicLLM(cfg)
        raise ValueError(f"Unsupported llm provider: {cfg.provider.value}")

    async def get_vision(self, spec_id: Optional[str] = None) -> Optional[VisionProvider]:
        try:
            cfg = await self._load_vision_config(spec_id=spec_id)
        except ValueError as e:
            logger.info("Vision provider unavailable: %s", e)
            return None
        if cfg.provider == ProviderType.GOOGLE:
            from app.ai.providers.google_provider import GoogleVision

            return GoogleVision(cfg)
        if cfg.provider in (ProviderType.OPENAI, ProviderType.ANTHROPIC):
            from app.ai.providers.openai_provider import OpenAIVision

            return OpenAIVision(cfg)
        logger.warning("Unsupported vision provider: %s", cfg.provider.value)
        return None

    async def test_all(self) -> dict:
        results: dict[str, tuple[bool, str]] = {}
        for kind, build in (("embedding", self.get_embedding), ("llm", self.get_llm)):
            try:
                provider = await build()
            except ValueError as e:
                results[kind] = (False, f"Not configured: {e}")
                continue
            results[kind] = await provider.test_connection()
        try:
            await self._load_vision_config()
            vision = await self.get_vision()
        except ValueError as e:
            vision = None
            results["vision"] = (False, f"Not configured: {e}")
        if "vision" not in results:
            if vision is None:
                results["vision"] = (False, "Not configured: unsupported vision provider")
            else:
                results["vision"] = await vision.test_connection()
        return results

    @staticmethod
    def supported_providers() -> dict:
        return SUPPORTED_PROVIDERS
