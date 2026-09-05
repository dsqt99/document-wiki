"""
OpenAI provider — embedding, LLM, and vision.

Supports:
  - Embedding: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
  - LLM: gpt-4o, gpt-4o-mini, gpt-3.5-turbo, etc.
  - Vision: gpt-4o (multimodal)

Also works with any OpenAI-compatible API (Azure, Together, Groq, etc.)
by setting a custom base_url.
"""

import asyncio
import base64
import json
from typing import Optional

from loguru import logger

from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_openai_messages,
)
from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,  # None = default OpenAI
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        from app.ai.tracing import record_embedding

        kwargs: dict = {
            "model": self.config.model_id,
            "input": text,
        }
        # text-embedding-3-* supports custom dimensions
        if self.config.dimensions:
            kwargs["dimensions"] = self.dimensions

        try:
            response = await self.client.embeddings.create(**kwargs)
            vec = response.data[0].embedding
            tokens = getattr(response.usage, "prompt_tokens", None) if hasattr(response, "usage") else None
            record_embedding(
                name=f"openai_embed:{self.config.model_id}",
                model=self.config.model_id,
                input_texts=text,
                vector_dimension=len(vec),
                tokens=tokens,
                metadata={"provider": "openai", "dimensions": self.dimensions},
            )
            return vec
        except Exception as e:
            record_embedding(
                name=f"openai_embed:{self.config.model_id}",
                model=self.config.model_id,
                input_texts=text,
                vector_dimension=self.dimensions,
                level="ERROR",
                status_message=str(e),
                metadata={"provider": "openai", "error": str(e)},
            )
            raise

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        from app.ai.tracing import record_embedding

        # OpenAI supports batch input natively (up to 2048 items)
        # Split into batches of 100 for safety
        batch_size = 100
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            kwargs = {
                "model": self.config.model_id,
                "input": batch,
            }
            if self.config.dimensions:
                kwargs["dimensions"] = self.dimensions

            try:
                response = await self.client.embeddings.create(**kwargs)
                sorted_data = sorted(response.data, key=lambda x: x.index)
                batch_vecs = [d.embedding for d in sorted_data]
                all_embeddings.extend(batch_vecs)

                tokens = getattr(response.usage, "prompt_tokens", None) if hasattr(response, "usage") else None
                record_embedding(
                    name=f"openai_embed_batch:{self.config.model_id}",
                    model=self.config.model_id,
                    input_texts=batch,
                    vector_dimension=len(batch_vecs[0]) if batch_vecs else self.dimensions,
                    tokens=tokens,
                    metadata={"provider": "openai", "batch_size": len(batch), "dimensions": self.dimensions},
                )
            except Exception as e:
                record_embedding(
                    name=f"openai_embed_batch:{self.config.model_id}",
                    model=self.config.model_id,
                    input_texts=batch,
                    vector_dimension=self.dimensions,
                    level="ERROR",
                    status_message=str(e),
                    metadata={"provider": "openai", "batch_size": len(batch), "error": str(e)},
                )
                raise

        logger.debug(f"OpenAI: embedded {len(texts)} texts in batches of {batch_size}")
        return all_embeddings

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.embed("test connection")
            dim = len(result)
            return True, f"OK — model={self.config.model_id}, dimensions={dim}"
        except Exception as e:
            return False, f"OpenAI embedding error: {e}"


class OpenAILLM(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    def _is_reasoning_or_gpt5(self) -> bool:
        mid = (self.config.model_id or "").lower()
        return any(p in mid for p in ("gpt-5", "o1", "o3", "o4"))

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        from datetime import datetime, timezone
        from app.ai.tracing import record_generation

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self.config.model_id,
            "messages": messages,
        }
        if not self._is_reasoning_or_gpt5():
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_completion_tokens" if self._is_reasoning_or_gpt5() else "max_tokens"] = max_tokens

        start_time = datetime.now(timezone.utc)
        try:
            response = await self.client.chat.completions.create(**kwargs)
            out_text = response.choices[0].message.content or ""
            usage_dict = None
            if hasattr(response, "usage") and response.usage:
                usage_dict = {
                    "input": getattr(response.usage, "prompt_tokens", 0),
                    "output": getattr(response.usage, "completion_tokens", 0),
                    "total": getattr(response.usage, "total_tokens", 0),
                }
            record_generation(
                name="openai.generate",
                model=self.config.model_id,
                input_data={"messages": messages},
                output_data=out_text,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                usage=usage_dict,
                model_parameters={"temperature": kwargs.get("temperature"), "max_tokens": max_tokens},
            )
            return out_text
        except Exception as e:
            record_generation(
                name="openai.generate",
                model=self.config.model_id,
                input_data={"messages": messages},
                output_data=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                level="ERROR",
                status_message=str(e),
                model_parameters={"temperature": kwargs.get("temperature"), "max_tokens": max_tokens},
            )
            raise

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> AssistantTurn:
        from datetime import datetime, timezone
        from app.ai.tracing import record_generation

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(neutral_to_openai_messages(messages))

        kwargs: dict = {
            "model": self.config.model_id,
            "messages": openai_messages,
            "tools": tools,
        }
        if not self._is_reasoning_or_gpt5():
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_completion_tokens" if self._is_reasoning_or_gpt5() else "max_tokens"] = max_tokens

        start_time = datetime.now(timezone.utc)
        try:
            response = await self.client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            message = choice.message
            text = message.content
            tool_calls: list[ToolCall] = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    args: dict = {}
                    if tc.function.arguments:
                        try:
                            args = json.loads(tc.function.arguments)
                        except Exception:
                            pass
                    tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

            reason_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
            finish_reason = reason_map.get(choice.finish_reason or "stop", "end_turn")

            usage_dict = None
            if hasattr(response, "usage") and response.usage:
                usage_dict = {
                    "input": getattr(response.usage, "prompt_tokens", 0),
                    "output": getattr(response.usage, "completion_tokens", 0),
                    "total": getattr(response.usage, "total_tokens", 0),
                }

            record_generation(
                name="openai.generate_with_tools",
                model=self.config.model_id,
                input_data={"messages": openai_messages, "tools": tools},
                output_data={"text": text, "tool_calls": [tc.__dict__ for tc in tool_calls]},
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                usage=usage_dict,
                model_parameters={"temperature": kwargs.get("temperature"), "max_tokens": max_tokens},
            )

            return AssistantTurn(
                text=text or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        except Exception as e:
            record_generation(
                name="openai.generate_with_tools",
                model=self.config.model_id,
                input_data={"messages": openai_messages, "tools": tools},
                output_data=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                level="ERROR",
                status_message=str(e),
                model_parameters={"temperature": kwargs.get("temperature"), "max_tokens": max_tokens},
            )
            raise

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Say 'OK'", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"OpenAI LLM error: {e}"


class OpenAIVision(VisionProvider):
    """OpenAI Vision provider (GPT-4o / GPT-5.6 multimodal)."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    def _is_reasoning_or_gpt5(self) -> bool:
        mid = (self.config.model_id or "").lower()
        return any(p in mid for p in ("gpt-5", "o1", "o3", "o4"))

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
    ) -> str:
        from datetime import datetime, timezone
        from app.ai.tracing import record_generation

        if not prompt:
            prompt = (
                "Describe this image in detail. "
                "If it's a diagram, flowchart, or table, explain the meaning and steps. "
                "If it's a regular image, provide a concise description."
            )

        b64_image = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_image}"

        kwargs: dict = {
            "model": self.config.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"},
                        },
                    ],
                }
            ],
        }
        if not self._is_reasoning_or_gpt5():
            kwargs["temperature"] = 0.2

        start_time = datetime.now(timezone.utc)
        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                out_text = response.choices[0].message.content or ""
                usage_dict = None
                if hasattr(response, "usage") and response.usage:
                    usage_dict = {
                        "input": getattr(response.usage, "prompt_tokens", 0),
                        "output": getattr(response.usage, "completion_tokens", 0),
                        "total": getattr(response.usage, "total_tokens", 0),
                    }
                record_generation(
                    name="openai.analyze_image",
                    model=self.config.model_id,
                    input_data={"prompt": prompt, "mime_type": mime_type, "image_size_bytes": len(image_data)},
                    output_data=out_text,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    usage=usage_dict,
                )
                return out_text
            except Exception as e:
                logger.warning(f"OpenAI Vision attempt {attempt + 1} failed: {e}")
                if attempt == 2:
                    record_generation(
                        name="openai.analyze_image",
                        model=self.config.model_id,
                        input_data={"prompt": prompt, "mime_type": mime_type, "image_size_bytes": len(image_data)},
                        output_data=None,
                        start_time=start_time,
                        end_time=datetime.now(timezone.utc),
                        level="ERROR",
                        status_message=str(e),
                    )
                if attempt < 2:
                    await asyncio.sleep(2)
        return ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            # 10x10 white PNG
            test_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00"
                b"\x02PX\xea\x00\x00\x00\x15IDATx\x9cc\xfc\xff\xff?\x03n\xc0\x84Gn\x04K\x03\x00\xa5"
                b"\xe3\x03\x11}\x92\xa6j\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            res = await self.analyze_image(test_png, "image/png", "What is this image?")
            return True, f"OK — model={self.config.model_id}, response='{res[:50]}'"
        except Exception as e:
            return False, f"OpenAI Vision error: {e}"
