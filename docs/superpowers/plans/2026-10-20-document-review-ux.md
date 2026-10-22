# Document management and upload review

Approved in conversation: unify source details into Original / Extracted text / Wiki pages / Information tabs; upload results show progress and open metadata review after extraction. Preserve existing Wiki editing and access rules.

- [x] Add an opt-in upload review gate stored in source metadata (no schema migration). Extract metadata, pause before indexing/compilation, resume only after explicit approval. Deferred reviews survive cleanup.
- [x] Reuse the metadata editor for upload review, with Save and continue / Review later and links to extracted text.
- [x] Show uploaded-file progress and review queue on the documents page; preserve failures and retry only failed uploads. Single uploads may open a review popup; bulk uploads never automatically open modal reviews. Display metadata in a batch table with status filters and explicit selection/approval (four concurrent approvals maximum). Poll in batches of 100 sources and preserve ids per signed-in user in sessionStorage for returning to the batch.
- [x] Add a source detail screen with four tabs, readable/raw extraction views, metadata editing, processing actions, explicit delete-impact confirmation, and scoped Wiki links.
- [x] Connect table actions to the same details and review/delete components; keep the Documents sidebar item active on source details.
- [x] Verify review gate, permissions, resumption, cleanup, frontend lint/types, and existing-document browser flows against the running development server.
- [ ] Exercise a real new bulk upload and approval in the browser. No new documents were uploaded during UI QA.

Files: app/services/upload_review_service.py, app/routers/sources.py, app/worker.py; frontend/src/components/knowledge source-detail, uploaded-documents, delete-source-dialog; upload-dialog and edit-source-dialog; existing knowledge and Wiki routes.

Work remains in the current checkout to preserve running development and parent work; no commits were created. API and the main worker were restarted after confirming zero queued/running jobs. Verified both new endpoints in the live API schema and the resume task in the worker registration. Existing documents were inspected without saving edits or deleting them. Regression tests live in tests/test_processing_mode.py and frontend/scripts/check-source-workflow.mjs.
