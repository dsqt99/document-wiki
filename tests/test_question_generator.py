"""Tests for legal question generation and conversational recall indexing."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.question_generator import (
    QuestionGenerator,
    build_question_chunks,
    index_question_chunks,
)
from app.worker import generate_questions_task


@pytest.mark.asyncio
async def test_generate_questions_for_chunk_success():
    """Test generating 2-3 realistic questions for a legal provision using LLM."""
    legal_text = (
        "Điều 5. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ:\n"
        "1. Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe trên đường mà trong máu hoặc "
        "hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu hoặc vượt quá 0,4 miligam/1 lít khí thở."
    )

    mock_llm_response = (
        "1. Uống rượu bia lái xe máy bị phạt bao nhiêu tiền?\n"
        "2. Mức nồng độ cồn vượt quá 0.4 mg/l khí thở phạt bao nhiêu?\n"
        "- Có bị tước giấy phép lái xe khi vi phạm nồng độ cồn không?"
    )

    mock_provider = AsyncMock()
    mock_provider.generate_text = AsyncMock(return_value=mock_llm_response)

    generator = QuestionGenerator(llm_provider=mock_provider)
    questions = await generator.generate_questions_for_chunk(
        text=legal_text,
        title="Điều 5",
        max_questions=3,
    )

    assert len(questions) == 3
    assert questions[0] == "Uống rượu bia lái xe máy bị phạt bao nhiêu tiền?"
    assert "Mức nồng độ cồn vượt quá 0.4 mg/l" in questions[1]
    assert "Có bị tước giấy phép lái xe" in questions[2]
    mock_provider.generate_text.assert_called_once()


@pytest.mark.asyncio
async def test_generate_questions_empty_text():
    """Test question generator handles empty or tiny text gracefully without calling LLM."""
    mock_provider = AsyncMock()
    generator = QuestionGenerator(llm_provider=mock_provider)

    questions = await generator.generate_questions_for_chunk(text="", max_questions=3)
    assert questions == []
    mock_provider.generate_text.assert_not_called()


def test_build_question_chunks():
    """Test structuring generated questions into indexable chunk dictionaries."""
    source_id = uuid.uuid4()
    questions = [
        "Lái xe máy khi say rượu bị phạt thế nào?",
        "Tước bằng lái xe bao lâu?",
    ]
    context_preview = "Điều 5. Xử phạt vi phạm nồng độ cồn đối với người điều khiển phương tiện..."

    chunks = build_question_chunks(
        source_id=source_id,
        parent_chunk_index=2,
        questions=questions,
        page_number=1,
        context_preview=context_preview,
    )

    assert len(chunks) == 2
    assert chunks[0]["chunk_type"] == "generated_question"
    assert chunks[0]["page_number"] == 1
    assert "câu_hỏi_tìm_kiếm" in chunks[0]["text"]
    assert "Lái xe máy khi say rượu" in chunks[0]["text"]
    assert "Điều 5" in chunks[0]["text"]
    assert chunks[0]["source_id"] == source_id
    assert chunks[0]["parent_chunk_index"] == 2


@pytest.mark.asyncio
async def test_index_question_chunks_mock_db():
    """Test embedding and saving question chunks into SourceChunkEmbedding."""
    session = AsyncMock()
    source_id = uuid.uuid4()
    chunks = [
        {
            "chunk_type": "generated_question",
            "text": "[câu_hỏi_tìm_kiếm | Trang 1]: Mức phạt nồng độ cồn xe máy?",
            "page_number": 1,
            "source_id": source_id,
            "parent_chunk_index": 0,
        }
    ]

    mock_spec = MagicMock()
    mock_spec.id = "text-embedding-3-small"
    mock_spec.dimension = 768

    mock_emb_provider = AsyncMock()
    mock_emb_provider.embed_batch.return_value = [[0.05] * 768]

    with patch("app.services.question_generator.ProviderRegistry") as mock_reg_cls, \
         patch("app.services.question_generator.get_spec", return_value=mock_spec), \
         patch("app.services.question_generator.upsert_chunk_embedding", new_callable=AsyncMock) as mock_upsert:

        mock_reg = MagicMock()
        mock_reg.get_active_embedding_spec_id = AsyncMock(return_value="text-embedding-3-small")
        mock_reg.get_embedding = AsyncMock(return_value=mock_emb_provider)
        mock_reg_cls.return_value = mock_reg

        count = await index_question_chunks(session, source_id, chunks)

        assert count == 1
        mock_emb_provider.embed_batch.assert_called_once()
        mock_upsert.assert_called_once()
        kwargs = mock_upsert.call_args[1]
        assert kwargs["source_id"] == source_id
        assert kwargs["page_number"] == 1
        assert "Mức phạt nồng độ cồn" in kwargs["text"]


@pytest.mark.asyncio
async def test_generate_questions_task_execution():
    """Test background worker task generate_questions_task."""
    source_id = uuid.uuid4()

    mock_source = MagicMock()
    mock_source.id = source_id
    mock_source.title = "Nghị định 100/2019/NĐ-CP"
    mock_source.full_text = "Điều 5. Xử phạt người điều khiển xe mô tô vi phạm...\n\nĐiều 6. Xử phạt..."
    mock_source.page_offsets = [0]
    mock_source.status = "ready"
    mock_source.preserve_verbatim = True

    mock_generator = AsyncMock()
    mock_generator.generate_questions_for_chunk.return_value = [
        "Mức phạt vi phạm điều khiển xe máy?"
    ]

    mock_reg = MagicMock()
    mock_reg.get_llm = AsyncMock(return_value=MagicMock())

    with patch("app.database.async_session_factory") as mock_session_factory, \
         patch("app.worker.check_task_attempt_validity", AsyncMock(return_value=True)), \
         patch("app.ai.registry.ProviderRegistry", return_value=mock_reg), \
         patch("app.services.question_generator.QuestionGenerator", return_value=mock_generator), \
         patch("app.services.question_generator.index_question_chunks", AsyncMock(return_value=1)):

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_source
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        result = await generate_questions_task({}, str(source_id))

        assert result["status"] == "success"
        assert result["questions_generated"] >= 1
        assert result["chunks_indexed"] >= 1
