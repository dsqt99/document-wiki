"""
Google Gemini provider — embedding, LLM, and vision.

Supports:
  - Embedding: gemini-embedding-2 (with task-prefix formatting)
  - LLM: gemini-2.5-flash, gemini-2.0-flash, etc.
  - Vision: gemini-2.0-flash (multimodal)
"""

import asyncio
import uuid
from typing import Optional

from loguru import logger

from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_gemini_contents,
    openai_tools_to_gemini,
)
from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)


class GoogleEmbedding(EmbeddingProvider):
    """Google Gemini embedding provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def embed(self, text: str) -> list[float]:
        from google.genai import types
        from app.ai.tracing import record_embedding

        formatted = self._format_for_task(text)
        try:
            result = self.client.models.embed_content(
                model=self.config.model_id,
                contents=formatted,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.dimensions,
                ),
            )
            vec = list(result.embeddings[0].values)  # type: ignore[index,union-attr]
            tokens = max(1, len(text) // 4)
            record_embedding(
                name=f"google_embed:{self.config.model_id}",
                model=self.config.model_id,
                input_texts=text,
                vector_dimension=len(vec),
                tokens=tokens,
                metadata={
                    "provider": "google",
                    "task": self.config.extra.get("task", "document"),
                    "dimensions": self.dimensions,
                },
            )
            return vec
        except Exception as e:
            record_embedding(
                name=f"google_embed:{self.config.model_id}",
                model=self.config.model_id,
                input_texts=text,
                vector_dimension=self.dimensions,
                level="ERROR",
                status_message=str(e),
                metadata={"provider": "google", "error": str(e)},
            )
            raise

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        semaphore = asyncio.Semaphore(concurrency)

        async def _embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        tasks = [_embed_one(t) for t in texts]
        results = await asyncio.gather(*tasks)
        logger.debug(f"Google: embedded {len(texts)} texts (concurrency={concurrency})")
        return list(results)

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.embed("test connection")
            dim = len(result)
            return True, f"OK — model={self.config.model_id}, dimensions={dim}"
        except Exception as e:
            return False, f"Google embedding error: {e}"

    def _format_for_task(self, text: str) -> str:
        """
        Format text with task prefix for gemini-embedding-2.
        Default to document-style for ingestion.
        """
        task = self.config.extra.get("task", "document")
        if task == "search_query":
            return f"task: search result | query: {text}"
        elif task == "question_answering":
            return f"task: question answering | query: {text}"
        elif task == "document":
            return f"title: none | text: {text}"
        elif task == "classification":
            return f"task: classification | query: {text}"
        elif task == "clustering":
            return f"task: clustering | query: {text}"
        elif task == "similarity":
            return f"task: sentence similarity | query: {text}"
        return text

    def with_task(self, task: str) -> "GoogleEmbedding":
        """Return a copy with a different task type for query vs document."""
        new_config = ProviderConfig(
            provider=self.config.provider,
            api_key=self.config.api_key,
            model_id=self.config.model_id,
            base_url=self.config.base_url,
            dimensions=self.config.dimensions,
            extra={**self.config.extra, "task": task},
        )
        provider = GoogleEmbedding(new_config)
        provider._client = self._client  # Share the client
        return provider


class GoogleLLM(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        from datetime import datetime, timezone
        from google.genai import types
        from app.ai.tracing import record_generation

        start_time = datetime.now(timezone.utc)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            out_text = response.text or ""
            usage_dict = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_dict = {
                    "input": getattr(response.usage_metadata, "prompt_token_count", 0),
                    "output": getattr(response.usage_metadata, "candidates_token_count", 0),
                    "total": getattr(response.usage_metadata, "total_token_count", 0),
                }
            record_generation(
                name="google.generate",
                model=self.config.model_id,
                input_data={"prompt": prompt, "system": system},
                output_data=out_text,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                usage=usage_dict,
                model_parameters={"temperature": temperature, "max_tokens": max_tokens},
            )
            return out_text
        except Exception as e:
            record_generation(
                name="google.generate",
                model=self.config.model_id,
                input_data={"prompt": prompt, "system": system},
                output_data=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                level="ERROR",
                status_message=str(e),
                model_parameters={"temperature": temperature, "max_tokens": max_tokens},
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
        from google.genai import types as gtypes
        from app.ai.tracing import record_generation

        contents = neutral_to_gemini_contents(messages)
        gemini_tools = openai_tools_to_gemini(tools)

        config = gtypes.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            tools=gemini_tools,  # type: ignore[arg-type]
            tool_config=gtypes.ToolConfig(
                function_calling_config=gtypes.FunctionCallingConfig(mode="AUTO")  # type: ignore[arg-type]
            ),
        )

        start_time = datetime.now(timezone.utc)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=contents,
                config=config,
            )

            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []

            if response.candidates:
                for part in (response.candidates[0].content.parts or []):  # type: ignore[union-attr]
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                    elif hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        # Gemini doesn't assign IDs — generate a stable one
                        tc_id = f"fc_{fc.name}_{uuid.uuid4().hex[:8]}"
                        tool_calls.append(ToolCall(id=tc_id, name=fc.name or "", arguments=args))

            finish_reason = "tool_use" if tool_calls else "end_turn"
            if response.candidates:
                fr = str(response.candidates[0].finish_reason or "")
                if "MAX_TOKENS" in fr:
                    finish_reason = "max_tokens"

            raw_content = response.candidates[0].content if response.candidates else None
            out_text = "\n".join(text_parts) or None

            usage_dict = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_dict = {
                    "input": getattr(response.usage_metadata, "prompt_token_count", 0),
                    "output": getattr(response.usage_metadata, "candidates_token_count", 0),
                    "total": getattr(response.usage_metadata, "total_token_count", 0),
                }

            record_generation(
                name="google.generate_with_tools",
                model=self.config.model_id,
                input_data={"messages": messages, "tools": tools},
                output_data={"text": out_text, "tool_calls": [tc.__dict__ for tc in tool_calls]},
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                usage=usage_dict,
                model_parameters={"temperature": temperature, "max_tokens": max_tokens},
            )

            return AssistantTurn(
                text=out_text,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                raw_provider_content=raw_content,
            )
        except Exception as e:
            record_generation(
                name="google.generate_with_tools",
                model=self.config.model_id,
                input_data={"messages": messages, "tools": tools},
                output_data=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                level="ERROR",
                status_message=str(e),
                model_parameters={"temperature": temperature, "max_tokens": max_tokens},
            )
            raise

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Say 'OK'", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"Google LLM error: {e}"


class GoogleVision(VisionProvider):
    """Google Gemini Vision provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
    ) -> str:
        from datetime import datetime, timezone
        from google.genai import types
        from app.ai.tracing import record_generation

        if not prompt:
            prompt = (
                "Describe this image in detail. "
                "If it's a diagram, flowchart, or table, explain the meaning and steps. "
                "If it's a regular image, provide a concise description."
            )

        start_time = datetime.now(timezone.utc)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=[
                    types.Part.from_bytes(data=image_data, mime_type=mime_type),
                    prompt,
                ],
            )
            out_text = response.text or ""
            usage_dict = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_dict = {
                    "input": getattr(response.usage_metadata, "prompt_token_count", 0),
                    "output": getattr(response.usage_metadata, "candidates_token_count", 0),
                    "total": getattr(response.usage_metadata, "total_token_count", 0),
                }
            record_generation(
                name="google.analyze_image",
                model=self.config.model_id,
                input_data={"prompt": prompt, "mime_type": mime_type, "image_size_bytes": len(image_data)},
                output_data=out_text,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                usage=usage_dict,
            )
            return out_text
        except Exception as e:
            record_generation(
                name="google.analyze_image",
                model=self.config.model_id,
                input_data={"prompt": prompt, "mime_type": mime_type, "image_size_bytes": len(image_data)},
                output_data=None,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                level="ERROR",
                status_message=str(e),
            )
            logger.warning(f"Google Vision failed: {e}")
            return ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            test_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00"
                b"\x02PX\xea\x00\x00\x00\x15IDATx\x9cc\xfc\xff\xff?\x03n\xc0\x84Gn\x04K\x03\x00\xa5"
                b"\xe3\x03\x11}\x92\xa6j\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            result = await self.analyze_image(test_png, "image/png", "What is this?")
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"Google Vision error: {e}"
