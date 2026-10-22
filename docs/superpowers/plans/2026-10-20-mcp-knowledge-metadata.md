# MCP knowledge metadata implementation plan

User approved extending MCP after the source/page audit. Keep Markdown text compatible with current chatbot clients and additionally return MCP structuredContent with schema_version, status, metadata, content, citations and pagination. Source metadata exposes document attributes, classification, management department, visibility, processing state and readable linked pages. Page metadata exposes stable ID, origin tag, complete summary, source references, scope, version and timestamps. Never export raw source metadata, storage paths or signed URLs.

- [x] Add regression tests for metadata, full summary, duplicate slug resolution, owner-only personal reads/listing, linked-source/page ACL, and compatible structured citations.
- [x] Add shared serialization/read-scope helpers; extend search, page/source reads, catalogs and source-page reads with dual text/structured output.
- [x] Support read_wiki_page by stable page_id or explicit scope; return accessible choices on ambiguous slug instead of selecting silently. Pass authenticated owner to list queries. Never trust a caller-supplied owner.
- [x] Run MCP/retrieval/permission tests and real database read-only smoke checks. Reload only the API MCP process once no relevant request is active; do not interrupt ongoing ingestion workers or change authentication code.

Use existing data and access filters. Do not create/reprocess documents, commit unrelated work, alter chatbot auth, or run subagents in this side conversation.


Validation: 73 targeted tests pass, including a native FastMCP client test, source/page metadata, owner/scope filters, array source filtering, full content/summary retention and non-mutating retrieval merges. Real database read-only smoke checks cover 9 read/catalog tools and hybrid search returning Source + Generated + Extracted with no failed arms. A rollback-only database check verifies owner-only private reads/catalogs, inaccessible source metadata and bad provenance rejection, duplicate-slug choices and explicit scope selection. Chatbot citation helpers accept MCP envelope, direct payload and JSON-string envelopes with scoped URLs preserved. No QA source/page records were committed. API restarted and /health confirms healthy database, Redis and MinIO; MCP tool schemas expose page_id/scope and origin_tag/source_id filters.

During the read-only hybrid search check, the existing sequential-chunk merger was found mutating ORM rows and causing an autoflush UPDATE. It now creates detached passage objects, preserves original chunks/hits and tracks merged page/character ranges. Actual hybrid search succeeds under SET TRANSACTION READ ONLY.
