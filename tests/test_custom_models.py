"""Model presets (GPT-6 Luna, Claude Sonnet 5.5) and admin-added custom models."""

import pytest

from app.ai import custom_models as cm
from app.ai.providers.base import ProviderType


@pytest.fixture
def store(monkeypatch):
    """In-memory app_config in place of ConfigService."""
    data: dict[str, str] = {}

    class FakeConfigService:
        def __init__(self, db):
            pass

        async def get(self, key):
            return data.get(key) or None

        async def set(self, key, value):
            data[key] = value

    monkeypatch.setattr("app.services.config_service.ConfigService", FakeConfigService)
    return data


def test_presets_only_gpt6_and_claude():
    from app.ai.embedding_catalog import EMBEDDING_CATALOG
    from app.ai.llm_catalog import LLM_CATALOG
    from app.ai.vision_catalog import VISION_CATALOG

    assert set(LLM_CATALOG) == {"openai/gpt-6-luna", "anthropic/claude-sonnet-5-5"}
    assert set(VISION_CATALOG) == {"openai/gpt-6-luna", "anthropic/claude-sonnet-5-5"}
    assert set(EMBEDDING_CATALOG) == {"openai/text-embedding-3-large"}


def test_custom_ids_round_trip_through_get_spec():
    from app.ai.embedding_catalog import UnknownEmbeddingModel
    from app.ai.embedding_catalog import get_spec as emb_spec
    from app.ai.llm_catalog import get_spec as llm_spec

    llm_id = cm.make_id("llm", "qwen3:32b")
    assert llm_id == "custom/qwen3:32b"
    assert llm_spec(llm_id).model_id == "qwen3:32b"

    emb_id = cm.make_id("embedding", "bge-m3", 1024)
    assert emb_id == "custom/1024/bge-m3"
    spec = emb_spec(emb_id)
    assert (spec.model_id, spec.dimension) == ("bge-m3", 1024)

    # Model names may contain slashes; only a leading number is a dimension.
    assert cm.parse_id("custom/org/model-x") == (None, "org/model-x")
    with pytest.raises(UnknownEmbeddingModel):
        emb_spec("custom/999/bge-m3")  # no table for that dimension


@pytest.mark.asyncio
async def test_save_keeps_key_and_delete_clears_it(store):
    m = cm.CustomModel(id="custom/m1", kind="llm", model_id="m1", label="M1",
                       base_url="http://llm.local/v1")
    await cm.save_custom(None, m, "secret")
    assert await cm.get_api_key(None, "llm", "custom/m1") == "secret"

    m.base_url = "http://llm2.local/v1"
    await cm.save_custom(None, m, None)  # edit without retyping the key
    assert (await cm.get_custom(None, "llm", "custom/m1")).base_url == "http://llm2.local/v1"
    assert await cm.get_api_key(None, "llm", "custom/m1") == "secret"
    assert len(await cm.list_custom(None, "llm")) == 1
    assert await cm.list_custom(None, "vision") == []

    assert await cm.delete_custom(None, "llm", "custom/m1")
    assert await cm.get_api_key(None, "llm", "custom/m1") == ""
    assert not await cm.delete_custom(None, "llm", "custom/m1")


@pytest.mark.asyncio
async def test_registry_uses_custom_endpoint(store):
    from app.ai.registry import ProviderRegistry

    await cm.save_custom(None, cm.CustomModel(
        id="custom/qwen", kind="llm", model_id="qwen", label="Qwen",
        base_url="http://vllm:8000/v1"), None)
    store["active_llm_model_spec_id"] = "custom/qwen"

    cfg = await ProviderRegistry(None)._load_llm_config()
    assert cfg.provider == ProviderType.OPENAI
    assert (cfg.model_id, cfg.base_url) == ("qwen", "http://vllm:8000/v1")
    assert cfg.api_key == "none"  # keyless local server


@pytest.mark.asyncio
async def test_registry_custom_embedding_omits_dimensions_param(store):
    from app.ai.registry import ProviderRegistry

    await cm.save_custom(None, cm.CustomModel(
        id="custom/1024/bge-m3", kind="embedding", model_id="bge-m3", label="BGE",
        base_url="http://emb:8080/v1", dimension=1024), "k")
    cfg = await ProviderRegistry(None)._load_embedding_config(spec_id="custom/1024/bge-m3")
    assert (cfg.base_url, cfg.api_key, cfg.dimensions) == ("http://emb:8080/v1", "k", 1024)
    assert cfg.extra["send_dimensions"] is False


@pytest.mark.asyncio
async def test_registry_preset_keys_per_provider(store):
    from app.ai.registry import ANTHROPIC_OPENAI_BASE_URL, ProviderRegistry

    store["llm_api_key"] = "sk-legacy-openai"
    store["vision_api_key__anthropic"] = "sk-ant-x"
    reg = ProviderRegistry(None)

    store["active_llm_model_spec_id"] = "openai/gpt-6-luna"
    assert (await reg._load_llm_config()).api_key == "sk-legacy-openai"

    # The legacy OpenAI key must not be sent to Anthropic.
    store["active_llm_model_spec_id"] = "anthropic/claude-sonnet-5-5"
    assert (await reg._load_llm_config()).api_key == ""

    store["active_vision_model_spec_id"] = "anthropic/claude-sonnet-5-5"
    cfg = await reg._load_vision_config()
    assert (cfg.api_key, cfg.base_url) == ("sk-ant-x", ANTHROPIC_OPENAI_BASE_URL)


@pytest.mark.asyncio
async def test_removed_active_model_falls_back_to_gpt6(store):
    from app.ai.registry import ProviderRegistry

    store["active_llm_model_spec_id"] = "openai/gpt-5.6-terra"
    store["active_vision_model_spec_id"] = "custom/deleted"
    reg = ProviderRegistry(None)
    assert await reg.get_active_llm_spec_id() == "openai/gpt-6-luna"
    assert await reg.get_active_vision_spec_id() == "openai/gpt-6-luna"


def test_gpt6_is_treated_as_reasoning_model():
    from app.ai.providers.base import ProviderConfig
    from app.ai.providers.openai_provider import OpenAILLM

    llm = OpenAILLM(ProviderConfig(provider=ProviderType.OPENAI, api_key="x", model_id="gpt-6-luna"))
    assert llm._is_reasoning_or_gpt5()
