"""Google Gemini providers (google-genai SDK)."""

import asyncio
import copy
import logging
from datetime import datetime, timezone

from app.ai import tracing
from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_gemini_contents,
    openai_tools_to_gemini,
)
from app.ai.providers.base import (
    DEFAULT_VISION_PROMPT,
    TINY_PNG,
    EmbeddingProvider,
    LLMProvider,
    VisionProvider,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


_QUERY_TASK_LABELS = {
    "search_query": "search result",
    "question_answering": "question answering",
    "fact_checking": "fact checking",
    "classification": "classification",
    "clustering": "clustering",
    "similarity": "sentence similarity",
}


def apply_task_prefix(task: str, text: str) -> str:
    if task in _QUERY_TASK_LABELS:
        return f"task: {_QUERY_TASK_LABELS[task]} | query: {text}"
    if task == "document":
        return f"title: none | text: {text}"
    return text


class _GoogleClientMixin:
    _client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.config.api_key)
        return self._client


class GoogleEmbedding(_GoogleClientMixin, EmbeddingProvider):
    def with_task(self, task: str) -> "GoogleEmbedding":
        cfg = copy.copy(self.config)
        cfg.extra = {**self.config.extra, "task": task}
        clone = GoogleEmbedding(cfg)
        clone._client = self._client
        return clone

    async def embed(self, text: str) -> list[float]:
        from google.genai import types

        content = apply_task_prefix(self.config.extra.get("task", ""), text)
        tokens = max(1, len(content) // 4)
        try:
            resp = await self.client.aio.models.embed_content(
                model=self.config.model_id,
                contents=content,
                config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
            )
        except Exception as e:
            tracing.record_embedding(
                "google.embed", self.config.model_id, content, self.dimensions, tokens=tokens,
                level="ERROR", status_message=str(e),
            )
            raise
        tracing.record_embedding("google.embed", self.config.model_id, content, self.dimensions, tokens=tokens)
        return list(resp.embeddings[0].values)

    async def embed_batch(self, texts, concurrency=5):
        sem = asyncio.Semaphore(max(1, concurrency))

        async def one(t):
            async with sem:
                return await self.embed(t)

        return list(await asyncio.gather(*(one(t) for t in texts)))

    async def test_connection(self) -> tuple[bool, str]:
        try:
            vec = await self.embed("connection test")
            return True, f"OK — model={self.config.model_id}, dimensions={len(vec)}"
        except Exception as e:
            return False, f"Google embedding error: {e}"


def _usage(resp):
    meta = getattr(resp, "usage_metadata", None)
    if not meta:
        return None
    return {
        "input": getattr(meta, "prompt_token_count", 0) or 0,
        "output": getattr(meta, "candidates_token_count", 0) or 0,
    }


class GoogleLLM(_GoogleClientMixin, LLMProvider):
    async def generate(self, prompt, system=None, max_tokens=None, temperature=0.7) -> str:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=max_tokens, temperature=temperature
        )
        start = _now()
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.config.model_id, contents=prompt, config=cfg
            )
        except Exception as e:
            tracing.record_generation(
                "google.generate", self.config.model_id, prompt, None, start, _now(),
                level="ERROR", status_message=str(e),
            )
            raise
        text = getattr(resp, "text", None) or ""
        tracing.record_generation(
            "google.generate", self.config.model_id, prompt, text, start, _now(), usage=_usage(resp),
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
        )
        return text

    async def generate_with_tools(self, messages, tools, system=None, max_tokens=None, temperature=0.2):
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            tools=[types.Tool(function_declarations=openai_tools_to_gemini(tools))],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        )
        contents = neutral_to_gemini_contents(messages)
        start = _now()
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.config.model_id, contents=contents, config=cfg
            )
        except Exception as e:
            tracing.record_generation(
                "google.generate_with_tools", self.config.model_id, messages, None, start, _now(),
                level="ERROR", status_message=str(e),
            )
            raise
        texts, calls, raw, finish_raw = [], [], None, ""
        candidates = getattr(resp, "candidates", None) or []
        if candidates:
            cand = candidates[0]
            raw = cand.content
            finish_raw = str(getattr(cand, "finish_reason", "") or "")
            for i, part in enumerate(getattr(cand.content, "parts", None) or []):
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    calls.append(ToolCall(id=getattr(fc, "id", None) or f"call_{i}", name=fc.name, arguments=dict(fc.args or {})))
                elif getattr(part, "text", None):
                    texts.append(part.text)
        if calls:
            finish = "tool_use"
        elif "MAX_TOKENS" in finish_raw.upper():
            finish = "max_tokens"
        else:
            finish = "end_turn"
        turn = AssistantTurn(text="".join(texts) or None, tool_calls=calls, finish_reason=finish, raw_provider_content=raw)
        tracing.record_generation(
            "google.generate_with_tools", self.config.model_id, messages,
            {"text": turn.text, "tool_calls": [c.name for c in calls]}, start, _now(), usage=_usage(resp),
        )
        return turn

    async def test_connection(self) -> tuple[bool, str]:
        try:
            text = await self.generate("Reply with OK.", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}: {text[:50]}"
        except Exception as e:
            return False, f"Google error: {e}"


class GoogleVision(_GoogleClientMixin, VisionProvider):
    async def analyze_image(self, image_data, mime_type="image/jpeg", prompt=None, max_tokens=None) -> str:
        from google.genai import types

        text_prompt = prompt or DEFAULT_VISION_PROMPT
        start = _now()
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=[types.Part.from_bytes(data=image_data, mime_type=mime_type), text_prompt],
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            text = getattr(resp, "text", None) or ""
            tracing.record_generation(
                "google.vision", self.config.model_id, {"prompt": text_prompt, "mime_type": mime_type},
                text, start, _now(), usage=_usage(resp),
            )
            return text
        except Exception as e:
            tracing.record_generation(
                "google.vision", self.config.model_id, {"mime_type": mime_type}, None, start, _now(),
                level="ERROR", status_message=str(e),
            )
            logger.warning("Gemini vision call failed: %s", e)
            return ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            from google.genai import types

            await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=[types.Part.from_bytes(data=TINY_PNG, mime_type="image/png"), "One word: what is this?"],
            )
            return True, f"OK — model={self.config.model_id}"
        except Exception as e:
            return False, f"Google vision error: {e}"
