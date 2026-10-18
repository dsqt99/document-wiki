"""OpenAILLM streams completions so a proxy read timeout (Cloudflare 524) does not cut long answers."""

from types import SimpleNamespace as NS

import pytest

from app.ai.providers.base import ProviderConfig, ProviderType
from app.ai.providers.openai_provider import OpenAILLM
from app.config import settings


def _chunk(content=None, tool_calls=None, finish=None, usage=None, choices=True):
    delta = NS(content=content, tool_calls=tool_calls)
    return NS(choices=[NS(delta=delta, finish_reason=finish)] if choices else [], usage=usage)


def _tc(index, id=None, name=None, args=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=args))


class _Stream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _Completions:
    def __init__(self, chunks=None, response=None):
        self.chunks, self.response, self.calls = chunks, response, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Stream(self.chunks) if kwargs.get("stream") else self.response


def _llm(completions):
    llm = OpenAILLM(ProviderConfig(provider=ProviderType.OPENAI, api_key="x", model_id="Qwen/Qwen3.5-9B"))
    llm._client = NS(chat=NS(completions=completions))
    return llm


@pytest.mark.asyncio
async def test_generate_joins_streamed_text_and_usage(monkeypatch):
    monkeypatch.setattr(settings, "llm_stream", True)
    comp = _Completions(chunks=[
        _chunk("Xin "), _chunk("chào"), _chunk(finish="stop"),
        _chunk(choices=False, usage=NS(prompt_tokens=7, completion_tokens=2)),
    ])
    assert await _llm(comp).generate("hi", temperature=0) == "Xin chào"
    assert comp.calls[0]["stream"] is True
    assert comp.calls[0]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_generate_with_tools_assembles_streamed_tool_call_deltas(monkeypatch):
    monkeypatch.setattr(settings, "llm_stream", True)
    comp = _Completions(chunks=[
        _chunk(tool_calls=[_tc(0, id="c1", name="write_page", args='{"slug": "di')]),
        _chunk(tool_calls=[_tc(0, args='eu-1"}')]),
        _chunk(tool_calls=[_tc(1, id="c2", name="finish", args="{}")]),
        _chunk(finish="tool_calls"),
    ])
    turn = await _llm(comp).generate_with_tools([{"role": "user", "content": "x"}], [])
    assert [(c.id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("c1", "write_page", {"slug": "dieu-1"}), ("c2", "finish", {}),
    ]
    assert turn.finish_reason == "tool_use"
    assert turn.text is None


@pytest.mark.asyncio
async def test_stream_off_uses_plain_completion(monkeypatch):
    monkeypatch.setattr(settings, "llm_stream", False)
    resp = NS(
        choices=[NS(message=NS(content="OK", tool_calls=None), finish_reason="stop")],
        usage=NS(prompt_tokens=1, completion_tokens=1),
    )
    comp = _Completions(response=resp)
    assert await _llm(comp).generate("hi") == "OK"
    assert "stream" not in comp.calls[0]
