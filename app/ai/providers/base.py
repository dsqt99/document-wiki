"""Provider configuration and abstract provider interfaces."""

import asyncio
import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


class ProviderType(str, enum.Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    VOYAGE = "voyage"
    COHERE = "cohere"


@dataclass
class ProviderConfig:
    provider: ProviderType
    api_key: str = ""
    model_id: str = ""
    base_url: Optional[str] = None
    dimensions: Optional[int] = None
    extra: dict = field(default_factory=dict)
    spec: Any = None


class _Provider:
    def __init__(self, config: ProviderConfig):
        self.config = config


class EmbeddingProvider(_Provider, ABC):
    @property
    def dimensions(self) -> int:
        return self.config.dimensions if self.config.dimensions is not None else 768

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str], concurrency: int = 5) -> list[list[float]]:
        sem = asyncio.Semaphore(max(1, concurrency))

        async def one(t: str) -> list[float]:
            async with sem:
                return await self.embed(t)

        return list(await asyncio.gather(*(one(t) for t in texts)))

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]: ...


class LLMProvider(_Provider, ABC):
    """Text-generation backend. Subclasses must implement ``generate``; tool
    calling is optional and only offered by some providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int | None = None, temperature: float = 0.7
    ) -> str:
        """Return the completion for ``prompt`` (optionally steered by ``system``)."""

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ):
        """Run one tool-calling turn. The default implementation refuses."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support tool calling; "
            "configure an LLM provider that supports function calling."
        )

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]: ...


class VisionProvider(_Provider, ABC):
    @abstractmethod
    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str: ...

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]: ...


DEFAULT_VISION_PROMPT = (
    "Describe this image in detail. Transcribe every piece of visible text exactly as written, "
    "keep numbers, dates and abbreviations unchanged, and render any table as a Markdown table."
)

# Minimal 1x1 transparent PNG used by vision connection tests.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000b49444154789c63f80f040009fb03fdfb5e6b2b0000000049454e44ae426082"
)
