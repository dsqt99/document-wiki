"""Generated search questions for legal provisions ("conversational recall").

For each provision an LLM writes a few everyday questions a user might ask.
Each question becomes an extra source chunk (chunk_index >= 70000) whose text
carries the question plus a short preview of the provision, so vague
colloquial queries can still land on the right article.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.services.embedding_storage import chunk_content_hash, upsert_chunk_embedding

QUESTION_CHUNK_INDEX_BASE = 70000
MIN_SOURCE_CHARS = 30
MAX_CONTENT_CHARS = 3000
MIN_QUESTION_CHARS = 8
PREVIEW_CHARS = 300

_LEADING_MARKERS = re.compile(r"^[\s\d.\-*•·●▪◦‣)]+")


def _build_prompt(content: str, max_questions: int) -> str:
    return (
        "Bạn là trợ lý pháp luật Việt Nam, hỗ trợ cán bộ công an và người dân tra cứu quy định.\n"
        f"Đọc điều khoản dưới đây và viết tối đa {max_questions} câu hỏi bằng lời nói thường ngày "
        "mà một người dùng có thể đặt ra khi cần tìm đúng điều khoản này.\n"
        "Ưu tiên các khía cạnh: mức xử phạt, hành vi vi phạm, điều kiện áp dụng, "
        "thẩm quyền xử lý và trình tự thủ tục.\n"
        "Yêu cầu trình bày: mỗi câu hỏi nằm trên một dòng riêng; không đánh số, "
        "không dùng gạch đầu dòng, không viết câu mở đầu hay giải thích.\n\n"
        f"Điều khoản:\n{content}\n\n"
        "Các câu hỏi:"
    )


def _parse_questions(raw: Any, max_questions: int) -> list[str]:
    if not isinstance(raw, str):
        raw = getattr(raw, "text", None) or getattr(raw, "content", None) or ""
        if not isinstance(raw, str):
            return []
    out: list[str] = []
    for line in raw.splitlines():
        cleaned = _LEADING_MARKERS.sub("", line).strip()
        if len(cleaned) < MIN_QUESTION_CHARS:
            continue
        out.append(cleaned)
        if len(out) >= max_questions:
            break
    return out


class QuestionGenerator:
    def __init__(self, llm_provider: Any = None):
        self.llm_provider = llm_provider

    async def _call_llm(self, prompt: str) -> Any:
        provider = self.llm_provider
        for name in ("generate_text", "complete"):
            fn = getattr(provider, name, None)
            if callable(fn):
                return await fn(prompt)
        fn = getattr(provider, "generate", None)
        if callable(fn):
            return await fn(prompt, temperature=0.4)
        raise AttributeError("LLM provider exposes no text generation method")

    async def generate_questions_for_chunk(
        self, text: Optional[str], title: Optional[str] = None, max_questions: int = 3
    ) -> list[str]:
        body = (text or "").strip()
        if len(body) < MIN_SOURCE_CHARS or self.llm_provider is None or max_questions <= 0:
            return []
        content = f"{title.strip()}\n{body}" if title and title.strip() else body
        content = content[:MAX_CONTENT_CHARS]
        try:
            raw = await self._call_llm(_build_prompt(content, max_questions))
            return _parse_questions(raw, max_questions)
        except Exception as exc:
            logger.warning(f"Question generation failed: {exc}")
            return []


def build_question_chunks(
    source_id: uuid.UUID,
    parent_chunk_index: int,
    questions: list[str],
    page_number: int = 1,
    context_preview: str = "",
) -> list[dict]:
    preview = (context_preview or "").replace("\r", " ").replace("\n", " ").strip()[:PREVIEW_CHARS]
    chunks: list[dict] = []
    for question in questions:
        text = f"[câu_hỏi_tìm_kiếm | Trang {page_number}]: {question}"
        if preview:
            text += f"\n\nNội dung liên quan: {preview}"
        chunks.append(
            {
                "chunk_type": "generated_question",
                "question": question,
                "text": text,
                "source_id": source_id,
                "parent_chunk_index": parent_chunk_index,
                "page_number": page_number,
            }
        )
    return chunks


async def index_question_chunks(
    session: AsyncSession,
    source_id: uuid.UUID,
    chunks: list[dict],
    spec_id: Optional[str] = None,
) -> int:
    if not chunks:
        return 0
    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.info("index_question_chunks: no active embedding model, skipping")
        return 0
    spec = get_spec(spec_id)
    provider = await registry.get_embedding(task="document", spec_id=spec.id)
    texts = [c["text"] for c in chunks]
    vectors = await provider.embed_batch(texts)

    count = 0
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        text = chunk["text"]
        await upsert_chunk_embedding(
            session=session,
            source_id=source_id,
            chunk_index=QUESTION_CHUNK_INDEX_BASE + i,
            spec=spec,
            vector=list(vector),
            text=text,
            start_char=0,
            end_char=len(text),
            page_number=chunk.get("page_number") or 1,
            content_hash=chunk_content_hash(text),
        )
        count += 1
    return count
