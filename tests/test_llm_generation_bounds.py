"""Prevent Wiki background generation from monopolising the shared gateway."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from app.ai.providers.base import ProviderConfig, ProviderType
from app.ai.providers.openai_provider import OpenAILLM
from app.config import settings


def provider(model="Qwen/Qwen3.5-9B"):
    return OpenAILLM(ProviderConfig(provider=ProviderType.OPENAI, model_id=model))


@pytest.mark.parametrize("model,key", [("Qwen/Qwen3.5-9B", "max_tokens"), ("gpt-6-luna", "max_completion_tokens")])
def test_unspecified_output_is_bounded(model, key):
    params = provider(model)._params(None, 0.1)
    assert 1 <= params[key] <= 8192


def test_explicit_budget_is_preserved():
    assert provider()._params(32, 0)["max_tokens"] == 32


@pytest.mark.asyncio
@pytest.mark.parametrize("with_tools", [False, True])
async def test_truncated_generation_is_not_usable_content(with_tools):
    llm = provider()
    llm._complete = AsyncMock(return_value=("partial page", [], "length", None))
    with pytest.raises(RuntimeError, match="(?i)(token|truncat)"):
        if with_tools:
            await llm.generate_with_tools([{"role": "user", "content": "write"}], [])
        else:
            await llm.generate("write")


@pytest.mark.asyncio
async def test_cancellation_closes_stream(monkeypatch):
    monkeypatch.setattr(settings, "llm_stream", True)
    started = asyncio.Event()

    class Stream:
        closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            started.set()
            await asyncio.Event().wait()

        async def close(self):
            self.closed = True

    stream = Stream()
    llm = provider()
    llm._client = NS(chat=NS(completions=NS(create=AsyncMock(return_value=stream))))
    task = asyncio.create_task(llm.generate("write"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed


@pytest.mark.asyncio
async def test_large_merge_preserves_both_versions_without_llm():
    from app.ai.mrp.merger import merge_page_content

    old = "# Trang\n\n" + "Nội dung cũ. " * 10000
    incoming = "# Trang\n\nDữ kiện mới: 12345.\n"
    llm = NS(generate=AsyncMock(return_value=old))
    result = await merge_page_content(llm, old, incoming, "trang")
    llm.generate.assert_not_awaited()
    assert result.startswith(old.rstrip())
    assert "Dữ kiện mới: 12345." in result


@pytest.mark.asyncio
async def test_small_merge_has_explicit_output_budget():
    from app.ai.mrp.merger import merge_page_content

    old = "# Trang\n\n" + "Dữ kiện cũ. " * 10
    incoming = "# Trang\n\nDữ kiện mới.\n"
    llm = NS(generate=AsyncMock(return_value=old + incoming))
    await merge_page_content(llm, old, incoming, "trang")
    assert 0 < llm.generate.call_args.kwargs["max_tokens"] <= 4096


@pytest.mark.asyncio
async def test_capped_health_probe_does_not_block_source_recovery(monkeypatch):
    from app.ai import registry
    from app.services.source_retry import ai_ready

    llm = provider()
    llm._complete = AsyncMock(return_value=("O", [], "length", None))
    monkeypatch.setattr(registry, "ProviderRegistry", lambda db: NS(get_llm=AsyncMock(return_value=llm)))
    assert await ai_ready(None) == (True, "ok")


@pytest.mark.asyncio
async def test_capped_connection_probe_is_reachable():
    llm = provider()
    llm._complete = AsyncMock(return_value=("O", [], "length", None))
    ok, _ = await llm.test_connection()
    assert ok
