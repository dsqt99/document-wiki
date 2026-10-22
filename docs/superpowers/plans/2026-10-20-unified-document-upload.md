# Unified upload pipeline and managing department

- Remove processing-mode controls. All uploads, including personal sources, run extraction -> optional metadata review -> source chunks/embedding + LLM Wiki compilation/embedding.
- Legal classification keeps Extracted article Wiki pages alongside Generated pages (confirmed by user); source chunks also respect article boundaries. Both Wiki origins remain searchable to agents in the permitted scope.
- Store one optional managing_department_id separately from department_ids (visibility). Validate its existence and caller's department permissions; expose in upload, review/edit and source information. Ownership never grants read access or changes scope.
- Rename the document classification field to “Phân loại văn bản”. Preserve the existing review gate.
- Normalize legacy processing flags to auto; do not automatically rerun all existing documents. Keep older API parameters accepted for compatibility, with no effect on pipeline selection.
- Make personal Wiki pages searchable by their owner in browser/MCP retrieval, while retaining source ACL and clearance checks.
- Verify private full-pipeline dispatch, manager/visibility separation, legal chunk boundaries, upload API, source updates and owner-only retrieval; build/reload at a safe checkpoint of the running summary job.

Verified: 166 targeted backend tests pass; TypeScript, changed-component ESLint and frontend production Docker build pass. Migration 053 is applied. Database rollback checks confirm a managing department creates no SourceDepartment visibility link, and both private Extracted/Generated pages are eligible for owner retrieval while another owner sees neither. No QA source or Wiki rows were retained. Browser confirmed personal visibility plus an independently selected PC08 manager, the new classification label and absence of the old processing selector/restriction. Existing metadata-review controls remain. API/frontend/worker were updated at the pre-existing summary job's 500-page checkpoint, with its reservation released for continuation.


## Upload review removed (2026-10-20)

Per user request, remove the post-extraction review checkbox and metadata approval pause. Ignore the deprecated upload review flag from older clients. Continue extraction, Wiki compilation and indexing automatically; metadata remains editable afterward. Existing database has no pending/awaiting upload review documents, so no data migration or automatic retries are needed.
