"""OpenAI (and OpenAI-compatible endpoint) providers."""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.ai import tracing
from app.ai.agent_protocol import AssistantTurn, ToolCall, neutral_to_openai_messages
from app.ai.providers.base import (
    DEFAULT_VISION_PROMPT,
    TINY_PNG,
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)

logger = logging.getLogger(__name__)

_REASONING_MARKERS = ("gpt-5", "gpt-6", "o1", "o3", "o4")
_EMBED_BATCH = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_reasoning(model_id: str) -> bool:
    lowered = (model_id or "").lower()
    return any(marker in lowered for marker in _REASONING_MARKERS)


class _OpenAIClientMixin:
    config: ProviderConfig
    _client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            kwargs = {"api_key": self.config.api_key or "none"}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client


class OpenAIEmbedding(_OpenAIClientMixin, EmbeddingProvider):
    def _kwargs(self) -> dict:
        kwargs: dict = {"model": self.config.model_id}
        if self.config.dimensions and self.config.extra.get("send_dimensions", True):
            kwargs["dimensions"] = self.config.dimensions
        return kwargs

    async def _call(self, inputs: list[str]) -> list[list[float]]:
        try:
            resp = await self.client.embeddings.create(input=inputs, **self._kwargs())
        except Exception as e:
            tracing.record_embedding(
                "openai.embed", self.config.model_id, inputs, self.dimensions,
                level="ERROR", status_message=str(e),
            )
            raise
        usage = getattr(resp, "usage", None)
        tokens = getattr(usage, "total_tokens", None) if usage else None
        tracing.record_embedding("openai.embed", self.config.model_id, inputs, self.dimensions, tokens=tokens)
        data = sorted(resp.data, key=lambda d: d.index)
        return [list(d.embedding) for d in data]

    async def embed(self, text: str) -> list[float]:
        return (await self._call([text]))[0]

    async def embed_batch(self, texts: list[str], concurrency: int = 5) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            out.extend(await self._call(list(texts[i:i + _EMBED_BATCH])))
        return out

    async def test_connection(self) -> tuple[bool, str]:
        try:
            vec = await self.embed("connection test")
            return True, f"OK — model={self.config.model_id}, dimensions={len(vec)}"
        except Exception as e:
            return False, f"OpenAI embedding error: {e}"


class OpenAILLM(_OpenAIClientMixin, LLMProvider):
    def _is_reasoning_or_gpt5(self) -> bool:
        return _is_reasoning(self.config.model_id)

    def _params(self, max_tokens: Optional[int], temperature: Optional[float]) -> dict:
        params: dict = {"model": self.config.model_id}
        if self._is_reasoning_or_gpt5():
            if max_tokens:
                params["max_completion_tokens"] = max_tokens
        else:
            if max_tokens:
                params["max_tokens"] = max_tokens
            if temperature is not None:
                params["temperature"] = temperature
        return params

    @staticmethod
    def _usage(resp) -> Optional[dict]:
        usage = getattr(resp, "usage", None)
        if not usage:
            return None
        return {
            "input": getattr(usage, "prompt_tokens", 0) or 0,
            "output": getattr(usage, "completion_tokens", 0) or 0,
        }

    async def generate(self, prompt, system=None, max_tokens=None, temperature=0.7) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        params = self._params(max_tokens, temperature)
        start = _now()
        try:
            resp = await self.client.chat.completions.create(messages=messages, **params)
        except Exception as e:
            tracing.record_generation(
                "openai.generate", self.config.model_id, messages, None, start, _now(),
                model_parameters=params, level="ERROR", status_message=str(e),
            )
            raise
        text = resp.choices[0].message.content or ""
        tracing.record_generation(
            "openai.generate", self.config.model_id, messages, text, start, _now(),
            usage=self._usage(resp), model_parameters=params,
        )
        return text

    async def generate_with_tools(self, messages, tools, system=None, max_tokens=None, temperature=0.2):
        msgs = neutral_to_openai_messages(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        params = self._params(max_tokens, temperature)
        start = _now()
        try:
            resp = await self.client.chat.completions.create(messages=msgs, tools=tools, **params)
        except Exception as e:
            tracing.record_generation(
                "openai.generate_with_tools", self.config.model_id, msgs, None, start, _now(),
                model_parameters=params, level="ERROR", status_message=str(e),
            )
            raise
        choice = resp.choices[0]
        message = choice.message
        calls = []
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except (ValueError, TypeError):
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        finish = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}.get(
            choice.finish_reason, "end_turn"
        )
        turn = AssistantTurn(text=message.content, tool_calls=calls, finish_reason=finish)
        tracing.record_generation(
            "openai.generate_with_tools", self.config.model_id, msgs,
            {"text": turn.text, "tool_calls": [c.name for c in calls]}, start, _now(),
            usage=self._usage(resp), model_parameters=params,
        )
        return turn

    async def test_connection(self) -> tuple[bool, str]:
        try:
            text = await self.generate("Reply with OK.", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}: {text[:50]}"
        except Exception as e:
            return False, f"OpenAI error: {e}"


class OpenAIVision(_OpenAIClientMixin, VisionProvider):
    async def analyze_image(self, image_data, mime_type="image/jpeg", prompt=None, max_tokens=None) -> str:
        b64 = base64.b64encode(image_data).decode("ascii")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt or DEFAULT_VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": "auto"}},
            ],
        }]
        params: dict = {"model": self.config.model_id}
        if _is_reasoning(self.config.model_id):
            if max_tokens:
                params["max_completion_tokens"] = max_tokens
        else:
            params["temperature"] = 0.2
            if max_tokens:
                params["max_tokens"] = max_tokens
        for attempt in range(3):
            start = _now()
            try:
                resp = await self.client.chat.completions.create(messages=messages, **params)
                text = resp.choices[0].message.content or ""
                tracing.record_generation(
                    "openai.vision", self.config.model_id, {"prompt": prompt or DEFAULT_VISION_PROMPT, "mime_type": mime_type},
                    text, start, _now(), usage=OpenAILLM._usage(resp), model_parameters=params,
                )
                return text
            except Exception as e:
                tracing.record_generation(
                    "openai.vision", self.config.model_id, {"mime_type": mime_type}, None, start, _now(),
                    model_parameters=params, level="ERROR", status_message=str(e),
                )
                logger.warning("Vision call failed (attempt %d/3): %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(2)
        return ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            b64 = base64.b64encode(TINY_PNG).decode("ascii")
            await self.client.chat.completions.create(
                model=self.config.model_id,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image? Answer in one word."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }],
            )
            return True, f"OK — model={self.config.model_id}"
        except Exception as e:
            return False, f"OpenAI vision error: {e}"
