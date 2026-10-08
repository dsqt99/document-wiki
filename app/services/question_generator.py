"""Question Generation Service for legal chunks (Reverse HyDE / Query Augmentation).

Generates realistic user queries from dense legal provisions to boost natural language
retrieval recall in hybrid vector search.
"""

import re
import uuid
from typing import Any, List, Optional
from loguru import logger

from app.ai.embedding_catalog import get_spec
from app.ai.registry import ProviderRegistry
from app.services.embedding_storage import (
    chunk_content_hash,
    upsert_chunk_embedding,
)


QUESTION_GEN_PROMPT = """Bạn là trợ lý pháp luật chuyên nghiệp cho lực lượng Công an nhân dân và người dân.
Hãy đọc đoạn văn bản quy phạm pháp luật sau đây và sinh ra tối đa {max_questions} câu hỏi thực tế mà người dân hoặc cán bộ thường tìm kiếm bằng ngôn ngữ giao tiếp hàng ngày khi cần tra cứu nội dung này.

Yêu cầu bắt buộc:
- Mỗi câu hỏi viết trên 1 dòng riêng biệt.
- Sử dụng ngôn ngữ tự nhiên, đời sống, dễ hiểu (ví dụ: "Uống rượu bia lái xe phạt bao nhiêu?", "Công an có quyền giữ bằng lái không?").
- Tập trung vào: mức phạt, hành vi vi phạm, điều kiện áp dụng, quyền hạn và thủ tục.
- KHÔNG thêm số thứ tự (1., 2.), KHÔNG gạch đầu dòng (-), KHÔNG viết lời chào hay giải thích gì thêm.

Văn bản quy định:
{content}
"""


class QuestionGenerator:
    """Generates synthetic search queries/questions for legal provisions."""

    def __init__(self, llm_provider: Optional[Any] = None):
        self.llm_provider = llm_provider

    async def generate_questions_for_chunk(
        self,
        text: str,
        title: Optional[str] = None,
        max_questions: int = 3,
    ) -> List[str]:
        """Generate 2-3 natural language queries that this legal chunk answers."""
        raw_text = text.strip() if text else ""
        if len(raw_text) < 30:
            logger.debug("QuestionGenerator: Chunk text too short for question generation.")
            return []

        if not self.llm_provider:
            logger.warning("QuestionGenerator: No LLM provider supplied, skipping question generation.")
            return []

        content = f"{title}\n{raw_text}" if title else raw_text
        prompt = QUESTION_GEN_PROMPT.format(max_questions=max_questions, content=content[:3000])

        try:
            if hasattr(self.llm_provider, "generate_text"):
                response = await self.llm_provider.generate_text(prompt)
            elif hasattr(self.llm_provider, "complete"):
                response = await self.llm_provider.complete(prompt)
            else:
                logger.warning(f"QuestionGenerator: Unsupported LLM provider interface {type(self.llm_provider)}")
                return []

            if not response:
                return []

            questions: List[str] = []
            for line in response.splitlines():
                cleaned = re.sub(r"^[\d\.\-\*\•\s]+", "", line).strip()
                if len(cleaned) >= 8:
                    questions.append(cleaned)
                if len(questions) >= max_questions:
                    break

            logger.info(f"QuestionGenerator: Generated {len(questions)} queries for provision.")
            return questions
        except Exception as e:
            logger.warning(f"QuestionGenerator: LLM question generation failed: {e}")
            return []


def build_question_chunks(
    source_id: uuid.UUID,
    parent_chunk_index: int,
    questions: List[str],
    page_number: int = 1,
    context_preview: str = "",
) -> List[dict]:
    """Structure questions into indexable chunk dictionaries for hybrid search."""
    chunks: List[dict] = []
    preview = context_preview.replace("\n", " ").strip()[:300] if context_preview else ""

    for q in questions:
        text = f"[câu_hỏi_tìm_kiếm | Trang {page_number}]: {q}"
        if preview:
            text += f"\n\nNội dung liên quan: {preview}"

        chunks.append({
            "chunk_type": "generated_question",
            "question": q,
            "text": text,
            "source_id": source_id,
            "parent_chunk_index": parent_chunk_index,
            "page_number": page_number,
        })
    return chunks


async def index_question_chunks(
    session,
    source_id: uuid.UUID,
    chunks: List[dict],
    spec_id: Optional[str] = None,
) -> int:
    """Embed and index question chunks into source_chunk_embeddings_<dim> table."""
    if not chunks:
        return 0

    registry = ProviderRegistry(session)
    if spec_id is None:
        spec_id = await registry.get_active_embedding_spec_id()
    if not spec_id:
        logger.warning(f"index_question_chunks: No active embedding spec found for source {source_id}")
        return 0

    spec = get_spec(spec_id)
    provider = await registry.get_embedding(task="document", spec_id=spec_id)

    texts = [c["text"] for c in chunks]
    vectors = await provider.embed_batch(texts)

    # Question chunks use 70000+ index space to avoid collisions with verbatim chunks
    BASE_QUESTION_INDEX = 70000
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chunk_idx = BASE_QUESTION_INDEX + idx
        await upsert_chunk_embedding(
            session=session,
            source_id=source_id,
            chunk_index=chunk_idx,
            spec=spec,
            vector=vector,
            text=chunk["text"],
            start_char=0,
            end_char=len(chunk["text"]),
            page_number=chunk.get("page_number", 1),
            content_hash=chunk_content_hash(chunk["text"]),
        )

    logger.info(f"index_question_chunks: Indexed {len(chunks)} question chunks for source {source_id}")
    return len(chunks)
