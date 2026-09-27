# 07 · Bản đồ mã nguồn WeKnora

Đường dẫn tính từ `temp_uploads/WeKnora/`. Dùng để đọc sâu khi triển khai từng hạng mục.

## Ingestion pipeline

| Chủ đề | File | Hàm/điểm chính |
|---|---|---|
| Tạo knowledge | `internal/application/service/knowledge_create.go` | `CreateKnowledgeFromFile`, `CreateKnowledgeFromURL`, `CreateKnowledgeFromPassage`, `CreateKnowledgeFromManual` |
| Xử lý chính | `internal/application/service/knowledge_process.go` | `ProcessDocument` (~3490), `convert()` (~4007), `processChunks` (~342), `ProcessQuestionGeneration` (~1626), `ProcessSummaryGeneration` |
| Hậu xử lý / fan-out | `internal/application/service/knowledge_post_process.go` | `Handle`, `selectGraphChunks`, `FinalizeSubtask` |
| Task types, queue | `internal/types/task.go` | danh sách queue và task type |
| Worker pool | `internal/router/task.go` | Core / PostProcess / Enrichment / Maintenance / Shared / Wiki |
| Chế độ không Redis | `internal/router/sync_task.go` | `SyncTaskExecutor`, `TaskRetryMetadata` |
| Sweep kẹt | `internal/application/service/knowledge_housekeeping.go` | |
| Reset khi khởi động | `internal/container/reset_pending_tasks.go` | |
| Dead-letter | `internal/middleware/asynqdl/`, `internal/types/task_dead_letter.go` | |
| Span theo bước | `internal/application/service/knowledge_span_tracker.go` | |
| Trạng thái | `internal/types/knowledge.go` | pending/processing/finalizing/completed/failed/deleting/cancelled |

## Parser (Go)

| Chủ đề | File |
|---|---|
| Đăng ký engine | `internal/infrastructure/docparser/engines.go` |
| gọi docreader gRPC | `internal/infrastructure/docparser/grpc_parser.go`, `docreader/proto/docreader.proto` |
| Engine `simple` (md/txt/csv/json) | `internal/infrastructure/docparser/builtin_converter.go` |
| MinerU | `mineru_converter.go`, `mineru_cloud_converter.go`, `mineru_layout.go` |
| PaddleOCR-VL | `paddleocr_vl_converter.go` |
| anydoc (Rust, cgo) | `internal/infrastructure/docparser/anydoc/` |
| HTML table → Markdown | `internal/infrastructure/docparser/html_table_normalizer.go` (`NormalizeHTMLTables`) |
| Lưu ảnh | `internal/infrastructure/docparser/image_resolver.go` (`ResolveAndStore`, `ResolveRemoteImages`) |
| OCR / caption VLM | `internal/application/service/image_multimodal.go` (`buildVLMOCRPrompt`, `buildImageAttrsPrompt`, `DecideOCR`) |
| Storage backends | `internal/application/service/file/` (local, MinIO, S3, COS, OSS, OBS, TOS, KS3) |

## docreader (Python)

| Định dạng | File |
|---|---|
| Registry/định tuyến | `docreader/parser/registry.py` |
| PDF (pypdfium2, XY-cut, heading, scan detect) | `docreader/parser/pdf_parser.py` (`SCAN_IMAGE_AREA_RATIO`, `SCAN_MIN_CHARS_PER_PAGE`, `_PDFIUM_LOCK`) |
| MarkItDown | `docreader/parser/markitdown_parser.py` |
| DOCX | `docreader/parser/docx2_parser.py` (chain), `docx_parser.py`, `docx_merge.py` |
| DOC | `docreader/parser/doc_parser.py` (LibreOffice → antiword) |
| PPT/PPTX | `ppt_convert.py`, `pptx_media.py` |
| Excel | `excel_parser.py`, `excel_convert.py`, `xlsx_repair.py`, `xlsx_merge.py` |
| Web | `web_parser.py` (Playwright + trafilatura), `docreader/utils/ssrf_proxy.py` |
| Splitter cũ (không dùng nữa) | `docreader/splitter/splitter.py` |

## Chunking (Go)

| Chủ đề | File |
|---|---|
| Mặc định, `SplitText`, bảo vệ span, overlap | `internal/infrastructure/chunker/splitter.go` |
| Chiến lược auto/heading/heuristic/legacy | `internal/infrastructure/chunker/strategy.go`, `profiler.go` (`ProfileDocument`, `SelectStrategy`) |
| Heading | `heading_splitter.go`, `heading_hierarchy.go`, `header_tracker.go` (lặp header bảng) |
| Heuristic | `heuristic_splitter.go` |
| Parent-child | `DeriveParentChildConfigs`, `SplitParentChild` |
| Prompt sinh câu hỏi | `config/prompt_templates/generate_questions.yaml` |
| Prompt tóm tắt | `config/prompt_templates/generate_summary.yaml` |

## Graph

| Chủ đề | File |
|---|---|
| Trích xuất | `internal/application/service/extract.go` (`ChunkExtractService.Handle`), `internal/application/service/chat_pipeline/extract_entity.go` |
| Prompt | `config/prompt_templates/graph_extraction.yaml` |
| Kiểu dữ liệu | `internal/types/extract_graph.go` |
| Neo4j | `internal/application/repository/retriever/neo4j/repository.go` |
| Truy vấn | `internal/application/service/chat_pipeline/search_entity.go`, `search_parallel.go` |
| Code chết | `internal/application/service/graph.go` (`NewGraphBuilder` không được gọi) |

## Truy xuất

| Chủ đề | File |
|---|---|
| Hybrid search | `internal/application/service/knowledgebase_search.go` (`HybridSearch`) |
| Fan-out nhiều KB/store | `knowledgebase_search_fanout.go`, `knowledgebase_search_storegroup.go` |
| RRF có trọng số | `knowledgebase_search_fusion.go` (`fuseWithRRF`) |
| Mở rộng query | `query_expansion.go` |
| FAQ search | `knowledgebase_search_faq.go` |
| Rerank + MMR | `internal/reranking/rerank.go`, `mmr.go`; client `internal/models/rerank/` |
| Vector stores | `internal/application/repository/retriever/` (postgres, elasticsearch, opensearch, milvus, qdrant, weaviate, …) |
| Pipeline chat | `internal/types/chat_manage.go` (`rag_stream`), `internal/application/service/chat_pipeline/` |
| Hiểu câu hỏi | `chat_pipeline/query_understand.go` |
| Parent/neighbor expand | `chat_pipeline/merge_expand.go` |
| Phân tích dữ liệu bảng | `chat_pipeline/data_analysis.go`; tool `internal/agent/tools/data_analysis.go`, `database_query.go` |

## Agent, MCP, khác

| Chủ đề | File |
|---|---|
| ReAct engine | `internal/agent/engine.go` |
| Tools | `internal/agent/tools/` |
| MCP client | `internal/mcp/` |
| MCP server | `internal/mcpserver/`, `mcp-server/weknora_mcp_server.py` |
| Wiki | `internal/application/service/wiki_ingest*.go` |
| Eval | `internal/application/service/evaluation.go`, `service/metric/`, `dataset/qa_dataset.py` |
| Connector | `internal/datasource/connector/` |
| Model provider | `internal/models/providers/`, `config/builtin_models.yaml.example` |

## Thứ tự đọc gợi ý

1. `pdf_parser.py` → `image_multimodal.go`: học nhận diện scan và OCR (cho Sprint 2).
2. `chunker/splitter.go` → `strategy.go` → `heading_splitter.go`: bảo vệ bảng, breadcrumb, parent-child (Sprint 3).
3. `reranking/rerank.go` + `mmr.go` + `knowledgebase_search_fusion.go` (Sprint 4).
4. `ExcelParser` + `extract.go` (`DataTableSummaryService`) + `data_analysis.go` (Sprint 5).
5. `knowledge_process.go` (`ProcessDocument` guards) + `asynqdl` (Sprint 1, 6).
