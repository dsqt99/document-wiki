import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.models import Source, WikiPage
from app.services.verbatim_service import (
    SourceChunk,
    VerbatimChunk,
    CHUNK_TARGET_CHARS,
    build_source_chunks,
    build_verbatim_chunks,
)
from app.worker import compute_source_dual_status
from app.services.reranker_service import RerankerService
from app.services.retrieval_service import (
    merge_sequential_chunks,
    unified_search,
)


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _mock_session():
    """AsyncSession stand-in: begin_nested() is a sync call returning an async CM."""
    session = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _Savepoint())
    return session



# ---------------------------------------------------------------------------
# 1. Heading Hierarchy & Table Boundary Protection in Chunking
# ---------------------------------------------------------------------------

def test_build_source_chunks_heading_hierarchy():
    """Verify build_source_chunks detects and attaches breadcrumb heading hierarchy."""
    text = (
        "# Văn bản Mẫu\n\n"
        "Đoạn mở đầu của văn bản mẫu.\n\n"
        "## Chương I. Quy định chung\n\n"
        "Nội dung chương 1.\n\n"
        "### Điều 1. Phạm vi áp dụng\n\n"
        "Nội dung quy định chi tiết về phạm vi áp dụng của văn bản.\n\n"
        "### Điều 2. Đối tượng áp dụng\n\n"
        "Nội dung quy định chi tiết về đối tượng áp dụng của văn bản.\n"
    )
    chunks = build_source_chunks(text, page_offsets=[], doc_title="Văn bản Mẫu")
    assert len(chunks) >= 1
    # Check that alias works
    assert VerbatimChunk is SourceChunk

    # Verify heading paths
    paths = [c.heading_path for c in chunks]
    assert any("Chương I" in p or "Điều" in p for p in paths)


def test_build_source_chunks_table_protection():
    """Verify chunk boundary does not slice through markdown table rows."""
    table = "\n".join([f"| Cột {i} | Giá trị {i} |" for i in range(10)])
    text = f"## Bảng số liệu\n\n{table}\n\nĐoạn văn kết thúc sau bảng."
    chunks = build_source_chunks(text, page_offsets=[])
    for c in chunks:
        # Check that table rows are intact (no dangling | at chunk edges)
        lines = [l.strip() for l in c.text.splitlines() if l.strip().startswith("|")]
        for l in lines:
            assert l.endswith("|"), f"Table line was cut: {l}"


def test_build_source_chunks_long_table_row_wise_with_header():
    """A table longer than one chunk (e.g. an Excel sheet) is split on rows and
    every chunk repeats the header so column names stay with the values."""
    header = "| STT | Họ tên | Địa chỉ |\n| --- | --- | --- |\n"
    rows = "\n".join(f"| {i} | Nguyễn Văn {i} | Phường {i}, Hưng Yên |" for i in range(300))
    text = f"## Bảng tính: DanhSach\n\n{header}{rows}\n\nGhi chú: dữ liệu tổng hợp từ các phường trên địa bàn tỉnh."
    chunks = build_source_chunks(text, page_offsets=[])

    table_chunks = [c for c in chunks if "| STT |" in c.text]
    assert len(table_chunks) > 1
    seen_rows = []
    for c in table_chunks:
        assert c.text.startswith(header)
        assert len(c.text) <= CHUNK_TARGET_CHARS + 200
        assert c.heading_path == "Bảng tính: DanhSach"
        body = c.text[len(header):]
        assert body == text[c.start_char:c.end_char]
        seen_rows += body.splitlines()
    # Every row lands in exactly one chunk (no overlap, nothing lost).
    assert seen_rows == rows.splitlines()
    assert "Ghi chú" in chunks[-1].text


def test_build_source_chunks_short_table_unchanged():
    """Tables that fit in one chunk keep the normal verbatim windowing."""
    text = "## Bảng\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nĐoạn văn sau bảng đủ dài để vượt ngưỡng tối thiểu của chunk."
    chunks = build_source_chunks(text, page_offsets=[])
    assert len(chunks) == 1
    assert chunks[0].text == text[chunks[0].start_char:chunks[0].end_char]


# ---------------------------------------------------------------------------
# 2. Dual Pipeline Branch Status Computation
# ---------------------------------------------------------------------------

def test_compute_source_dual_status_verbatim():
    """Verbatim source: ready as soon as chunk_status is ready, skipping wiki."""
    src = Source(
        id=uuid.uuid4(),
        preserve_verbatim=True,
        chunk_status="ready",
        chunk_progress=100,
        chunk_progress_message="Indexed 15 chunks",
        wiki_status="skipped",
    )
    st, prog, msg = compute_source_dual_status(src)
    assert st == "ready"
    assert prog == 100
    assert "Indexed 15 chunks" in msg


def test_compute_source_dual_status_both_ready():
    """General source: ready when both chunk_status and wiki_status are ready."""
    src = Source(
        id=uuid.uuid4(),
        preserve_verbatim=False,
        chunk_status="ready",
        chunk_progress=100,
        wiki_status="ready",
        wiki_progress=100,
    )
    st, prog, msg = compute_source_dual_status(src)
    assert st == "ready"
    assert prog == 100
    assert "Ready" in msg


def test_compute_source_dual_status_gated_approval():
    """General source: awaiting_approval for wiki, but chunk_status is ready."""
    src = Source(
        id=uuid.uuid4(),
        preserve_verbatim=False,
        chunk_status="ready",
        chunk_progress=100,
        wiki_status="awaiting_approval",
        wiki_progress=55,
        wiki_progress_message="Awaiting approval: 45,000 tokens",
    )
    st, prog, msg = compute_source_dual_status(src)
    assert st == "awaiting_approval"
    assert "Raw chunks already searchable" in msg


def test_compute_source_dual_status_partial():
    """When wiki fails but chunks are ready, status is partial (usable raw chunks)."""
    src = Source(
        id=uuid.uuid4(),
        preserve_verbatim=False,
        chunk_status="ready",
        chunk_progress=100,
        wiki_status="error",
        wiki_error_message="LLM context limit exceeded",
    )
    st, prog, msg = compute_source_dual_status(src)
    assert st == "partial"
    assert "Raw chunks searchable" in msg


# ---------------------------------------------------------------------------
# 3. Adjacent Chunk Merging
# ---------------------------------------------------------------------------

def test_merge_sequential_chunks():
    """Verify sequential chunks from the same source are merged."""
    src_id = uuid.uuid4()
    mock_src = MagicMock()
    mock_src.id = src_id

    mock_c0 = MagicMock()
    mock_c0.chunk_index = 0
    mock_c0.text = "Phần đầu của nội dung điều khoản."

    mock_c1 = MagicMock()
    mock_c1.chunk_index = 1
    mock_c1.text = "Phần tiếp theo của cùng điều khoản."

    mock_c5 = MagicMock()
    mock_c5.chunk_index = 5
    mock_c5.text = "Một đoạn độc lập ở trang sau."

    hits = [
        {"source": mock_src, "chunk": mock_c0, "rrf": 0.05},
        {"source": mock_src, "chunk": mock_c1, "rrf": 0.04},
        {"source": mock_src, "chunk": mock_c5, "rrf": 0.03},
    ]

    merged = merge_sequential_chunks(hits)
    assert len(merged) == 2
    # First merged hit should contain both c0 and c1 text
    first_chunk = merged[0]["chunk"]
    assert "Phần đầu" in first_chunk.text
    assert "Phần tiếp theo" in first_chunk.text
    # Non-adjacent c5 remains separate
    assert merged[1]["chunk"].chunk_index == 5


# ---------------------------------------------------------------------------
# 4. Reranker Auto-Degradation Floor and MMR Diversification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reranker_threshold_and_degrade_floor():
    """Verify reranker filters low scores and auto-degrades when all are borderline."""
    service = RerankerService(base_url="", enabled=True)
    query = "phòng cháy chữa cháy"

    # Moderate match documents
    docs = [
        {"id": "d1", "text": "Quy định về chữa cháy cơ sở", "rerank_score": 0.18},
        {"id": "d2", "text": "Thời tiết mùa hè nóng bức", "rerank_score": 0.02},
    ]

    # If threshold=0.25 and degrade_floor=0.15:
    # d1 has 0.18, so with auto-degrade to 0.15, d1 is kept while d2 is dropped
    results = await service.rerank(
        query=query,
        documents=docs,
        threshold=0.25,
        degrade_floor=0.15,
        apply_mmr=False,
    )
    assert len(results) == 1
    assert results[0]["id"] == "d1"


# ---------------------------------------------------------------------------
# 5. Fault-Tolerant Unified Search & Winning-Chunk Extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unified_search_fault_tolerant_wiki_error():
    """Verify unified_search does not crash if wiki hybrid search raises an error."""
    session = _mock_session()
    mock_source = MagicMock()
    mock_source.id = uuid.uuid4()
    mock_source.title = "Nghị định PCCC"

    mock_chunk = MagicMock()
    mock_chunk.chunk_index = 0
    mock_chunk.text = "Quy định an toàn PCCC đối với nhà cao tầng."

    source_hits = [{"source": mock_source, "chunk": mock_chunk, "rrf": 0.04, "cosine": 0.82}]

    with patch("app.services.legal_route_service.route_exact_legal_query", new_callable=AsyncMock) as mock_route, \
         patch("app.services.wiki_service.search_pages_hybrid", side_effect=RuntimeError("Milvus cluster down")), \
         patch("app.services.wiki_service.search_source_chunks_hybrid", new_callable=AsyncMock, return_value=source_hits):

        mock_route.return_value = {"matched": False}

        res = await unified_search(
            session=session,
            query="an toàn PCCC nhà cao tầng",
            query_embedding=[0.1] * 768,
            top_k=5,
            apply_reranker=False,
        )

        assert res is not None
        assert len(res["ranked_results"]) == 1
        kind, score, hit = res["ranked_results"][0]
        assert kind == "source"
        assert hit["source"].title == "Nghị định PCCC"
        assert "wiki" in res["failed_arms"]


if __name__ == "__main__":
    import asyncio
    print("Running test_build_source_chunks_heading_hierarchy...")
    test_build_source_chunks_heading_hierarchy()
    print("  PASS")

    print("Running test_build_source_chunks_table_protection...")
    test_build_source_chunks_table_protection()
    print("  PASS")

    print("Running test_compute_source_dual_status_verbatim...")
    test_compute_source_dual_status_verbatim()
    print("  PASS")

    print("Running test_compute_source_dual_status_both_ready...")
    test_compute_source_dual_status_both_ready()
    print("  PASS")

    print("Running test_compute_source_dual_status_gated_approval...")
    test_compute_source_dual_status_gated_approval()
    print("  PASS")

    print("Running test_compute_source_dual_status_partial...")
    test_compute_source_dual_status_partial()
    print("  PASS")

    print("Running test_merge_sequential_chunks...")
    test_merge_sequential_chunks()
    print("  PASS")

    print("Running test_reranker_threshold_and_degrade_floor...")
    asyncio.run(test_reranker_threshold_and_degrade_floor())
    print("  PASS")

    print("Running test_unified_search_fault_tolerant_wiki_error...")
    asyncio.run(test_unified_search_fault_tolerant_wiki_error())
    print("  PASS")

    print("\nALL 9 TESTS IN test_dual_pipeline_retrieval PASSED!")
