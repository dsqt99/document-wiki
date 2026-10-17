"""Anthropic Messages API provider."""

from datetime import datetime, timezone

from app.ai import tracing
from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_anthropic_messages,
    openai_tools_to_anthropic,
)
from app.ai.providers.base import LLMProvider

DEFAULT_MAX_TOKENS = 16384


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnthropicLLM(LLMProvider):
    _client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            kwargs = {"api_key": self.config.api_key or "none"}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    @staticmethod
    def _usage(resp):
        usage = getattr(resp, "usage", None)
        if not usage:
            return None
        return {"input": getattr(usage, "input_tokens", 0) or 0, "output": getattr(usage, "output_tokens", 0) or 0}

    async def generate(self, prompt, system=None, max_tokens=None, temperature=0.7) -> str:
        params = {
            "model": self.config.model_id,
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        messages = [{"role": "user", "content": prompt}]
        start = _now()
        try:
            resp = await self.client.messages.create(messages=messages, **params)
        except Exception as e:
            tracing.record_generation(
                "anthropic.generate", self.config.model_id, messages, None, start, _now(),
                model_parameters=params, level="ERROR", status_message=str(e),
            )
            raise
        text = ""
        if resp.content:
            text = getattr(resp.content[0], "text", "") or ""
        tracing.record_generation(
            "anthropic.generate", self.config.model_id, messages, text, start, _now(),
            usage=self._usage(resp), model_parameters=params,
        )
        return text

    async def generate_with_tools(self, messages, tools, system=None, max_tokens=None, temperature=0.2):
        params = {
            "model": self.config.model_id,
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        msgs = neutral_to_anthropic_messages(messages)
        start = _now()
        try:
            resp = await self.client.messages.create(
                messages=msgs, tools=openai_tools_to_anthropic(tools), **params
            )
        except Exception as e:
            tracing.record_generation(
                "anthropic.generate_with_tools", self.config.model_id, msgs, None, start, _now(),
                model_parameters=params, level="ERROR", status_message=str(e),
            )
            raise
        texts, calls = [], []
        for block in resp.content or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                texts.append(block.text)
            elif btype == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))
        reason = resp.stop_reason if resp.stop_reason in ("tool_use", "end_turn", "max_tokens") else "end_turn"
        turn = AssistantTurn(text="".join(texts) or None, tool_calls=calls, finish_reason=reason)
        tracing.record_generation(
            "anthropic.generate_with_tools", self.config.model_id, msgs,
            {"text": turn.text, "tool_calls": [c.name for c in calls]}, start, _now(),
            usage=self._usage(resp), model_parameters=params,
        )
        return turn

    async def test_connection(self) -> tuple[bool, str]:
        try:
            text = await self.generate("Reply with OK.", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}: {text[:50]}"
        except Exception as e:
            return False, f"Anthropic error: {e}"
