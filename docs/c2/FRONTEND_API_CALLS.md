# Frontend → backend API calls

Inventory of every HTTP endpoint called by the c2 frontend (`frontend/src`). It was built by
statically scanning `api()`, `apiUpload()`, `apiUrl()` and `fetch()` call sites (including
paths held in same-file constants and props), then reviewing the dynamic segments by hand.

Conventions:
- `{id}`, `{slug}` etc. are path parameters. Query parameters are listed only where they
  matter.
- `POST (multipart)` means `apiUpload()` (FormData, 120 s timeout).
- `NAV` is a browser navigation built with `apiUrl()` (full-page redirect or download), not
  an XHR.
- All requests carry `Authorization: Bearer <arkon_token>` when a token exists (see 07a §5.2).

## Auth and session

| Method | Path | Called from |
|---|---|---|
| POST | `/api/auth/login` | `lib/auth.tsx` |
| GET | `/api/auth/me` | `lib/auth.tsx` |
| POST | `/api/auth/change-password` | `app/(portal)/profile/page.tsx` |
| GET | `/api/auth/sso/config` | `app/login/page.tsx` |
| NAV | `/api/auth/sso/login?next=…[&prompt=none]` | `app/login/page.tsx` |
| NAV | `/api/auth/sso/chatbot/login?next=…[&prompt=none]` | `app/login/page.tsx` |
| NAV | `/api/auth/sso/logout` | `lib/auth.tsx` |
| GET | `/api/my/mcp-token/status` | `components/profile/mcp-token-card.tsx` |
| POST | `/api/my/mcp-token` | `components/profile/mcp-token-card.tsx` |
| DELETE | `/api/my/mcp-token` | `components/profile/mcp-token-card.tsx` |

## Notifications

| Method | Path | Called from |
|---|---|---|
| GET | `/api/notifications/unread-count` | `components/layout/notification-bell.tsx` |
| GET | `/api/notifications?limit=50` | `components/layout/notification-bell.tsx` |
| POST | `/api/notifications/read-all` | `components/layout/notification-bell.tsx` |
| POST | `/api/notifications/{id}/read` | `components/layout/notification-bell.tsx` |

## Dashboard, statistics, audit, health

| Method | Path | Called from |
|---|---|---|
| GET | `/api/admin/stats/overview` | `app/(portal)/page.tsx` |
| GET | `/api/admin/stats/usage` | `app/(portal)/page.tsx` |
| GET | `/api/admin/stats/content` | `app/(portal)/page.tsx` |
| GET | `/api/admin/stats/contribution` | `app/(portal)/page.tsx` |
| GET | `/api/admin/stats/gaps` | `app/(portal)/page.tsx` |
| POST | `/api/admin/stats/rollup` | `app/(portal)/page.tsx` |
| GET (fetch, blob) | `/api/admin/stats/export/{section}.csv?…` | `components/stats/stats-parts.tsx` |
| GET | `/api/wiki/lint` | `app/(portal)/page.tsx` |
| GET | `/api/health` | `components/dashboard/system-health-card.tsx` |
| GET | `/api/audit/log?page=…&page_size=…` | `app/(portal)/audit/page.tsx` |

## Documents (sources) and knowledge types

| Method | Path | Called from |
|---|---|---|
| GET | `/api/sources` | `app/(portal)/knowledge/page.tsx`, `components/dashboard/recent-sources-card.tsx`, `components/wiki/wiki-page-tree.tsx` |
| GET | `/api/sources/{id}` | `knowledge-table/index.tsx`, `wiki/[...slug]/wiki-page-view.tsx`, `wiki/law/page.tsx`, `components/law/law-source-tab.tsx` |
| PATCH | `/api/sources/{id}` | `knowledge-table/edit-source-dialog.tsx` |
| DELETE | `/api/sources/{id}` | `knowledge-table/index.tsx`, `knowledge-table/extraction-review-dialog.tsx` |
| POST (multipart) | `/api/sources/upload` | `components/knowledge/upload-dialog.tsx` |
| POST | `/api/sources/{id}/retry[?…]` | `knowledge-table/index.tsx` |
| GET | `/api/sources/{id}/plan` | `knowledge-table/plan-review-dialog.tsx` |
| POST | `/api/sources/{id}/plan/approve` | `knowledge-table/plan-review-dialog.tsx` |
| POST | `/api/sources/{id}/plan/reject` | `knowledge-table/plan-review-dialog.tsx` |
| POST | `/api/sources/{id}/plan/regenerate` | `knowledge-table/plan-review-dialog.tsx` |
| POST | `/api/sources/{id}/approve-extraction` | `knowledge-table/extraction-review-dialog.tsx` |
| GET | `/api/knowledge-types` | `app/(portal)/knowledge/page.tsx` |
| POST | `/api/knowledge-types` | `components/types/knowledge-type-dialog.tsx` |
| PUT | `/api/knowledge-types/{id}` | `components/types/knowledge-type-dialog.tsx` |
| DELETE | `/api/knowledge-types/{id}` | `components/types/knowledge-type-cards.tsx` |
| POST | `/api/wiki/legal-docs/backfill` | `app/(portal)/knowledge/page.tsx` |
| GET | `/api/wiki/legal-doc-fields` | `knowledge-table/edit-source-dialog.tsx` |

## Organisation: departments, employees, scopes

| Method | Path | Called from |
|---|---|---|
| GET | `/api/departments` | departments, employees, knowledge, prompts, skills pages; `skills/contribute-dialog.tsx` |
| POST | `/api/departments` | `departments/department-dialog.tsx`, `employees/employee-dialog.tsx` (inline create) |
| PUT | `/api/departments/{id}` | `departments/department-dialog.tsx` |
| DELETE | `/api/departments/{id}` | `departments/department-cards.tsx` |
| GET | `/api/employees[?department_id=…&page_size=…]` | `app/(portal)/employees/page.tsx`, `departments/dept-members-dialog.tsx`, `shared/scope-members-dialog.tsx` |
| POST | `/api/employees` | `employees/employee-dialog.tsx` |
| PUT | `/api/employees/{id}` | `employees/employee-dialog.tsx` |
| DELETE | `/api/employees/{id}` | `employees/employee-table.tsx` |
| PATCH | `/api/employees/{id}/toggle` | `employees/employee-table.tsx` |
| POST | `/api/employees/{id}/token` | `employees/employee-table.tsx` |
| DELETE | `/api/employees/{id}/token` | `employees/employee-table.tsx` |
| POST | `/api/employees/{id}/departments` | `departments/dept-members-dialog.tsx` |
| DELETE | `/api/employees/{id}/departments/{deptId}` | `departments/dept-members-dialog.tsx` |
| GET | `/api/scopes/{scopeType}/{scopeId}/members` | `shared/scope-members-dialog.tsx` |
| POST | `/api/scopes/{scopeType}/{scopeId}/members` | `shared/scope-members-dialog.tsx` |
| DELETE | `/api/scopes/{scopeType}/{scopeId}/members/{employeeId}` | `shared/scope-members-dialog.tsx` |

## Wiki pages, drafts, branches, graph, images

| Method | Path | Called from |
|---|---|---|
| GET | `/api/wiki/pages[?…]` | `components/wiki/wiki-pages-loader.ts` (tree, search, backlinks), `knowledge-table/source-articles-drawer.tsx` |
| POST | `/api/wiki/pages` | `components/wiki/wiki-create-page-dialog.tsx` |
| GET | `/api/wiki/pages/{slug…}[?scope…]` | `wiki/[...slug]/wiki-page-view.tsx`, `wiki/graph/page.tsx`, `wiki/branches/[id]/rebase/page.tsx`, `components/review/review-desk.tsx` |
| PUT | `/api/wiki/pages/{slug…}` | `wiki/[...slug]/wiki-page-view.tsx` |
| DELETE | `/api/wiki/pages/{slug…}[?…]` | `components/wiki/wiki-page-tree.tsx` |
| PATCH | `/api/wiki/pages/{slug…}/status` | `wiki/[...slug]/wiki-page-view.tsx` |
| GET | `/api/wiki/pages/{slug…}/drafts[?…]` | `wiki/[...slug]/wiki-page-view.tsx` |
| POST | `/api/wiki/pages/{slug…}/drafts` | `wiki/[...slug]/wiki-page-view.tsx` |
| GET | `/api/wiki/my-scopes` | `wiki/[...slug]/wiki-page-view.tsx` |
| POST | `/api/wiki/drafts/create` | `components/wiki/wiki-create-page-dialog.tsx` |
| GET | `/api/wiki/drafts/{id}` | `components/wiki/wiki-draft-banner.tsx`, `components/review/review-desk.tsx` |
| PATCH | `/api/wiki/drafts/{id}/content` | `wiki/[...slug]/wiki-page-view.tsx` |
| POST | `/api/wiki/drafts/{id}/approve` | `components/wiki/wiki-draft-banner.tsx` |
| POST | `/api/wiki/drafts/{id}/reject` | `components/wiki/wiki-draft-banner.tsx` |
| POST | `/api/wiki/drafts/{id}/request-changes` | `components/wiki/wiki-draft-banner.tsx` |
| POST | `/api/wiki/drafts/{id}/withdraw` | `components/wiki/wiki-draft-banner.tsx` |
| GET | `/api/wiki/branches` | `wiki/[...slug]/wiki-page-view.tsx`, `components/review/review-desk.tsx` |
| POST | `/api/wiki/branches` | `wiki/[...slug]/wiki-page-view.tsx`, `wiki/[...slug]/branch-modal.tsx` |
| GET | `/api/wiki/branches/{id}` | `wiki/branches/[id]/rebase/page.tsx`, `components/review/review-desk.tsx` |
| POST | `/api/wiki/branches/{id}/merge` | `components/review/review-desk.tsx` |
| POST | `/api/wiki/branches/{id}/close` | `components/review/review-desk.tsx` |
| POST | `/api/wiki/branches/{id}/rebase/{draftId}` | `wiki/branches/[id]/rebase/page.tsx` |
| GET | `/api/wiki/graph?offset=…&limit=…` | `wiki/graph/page.tsx`, `components/law/law-graph-tab.tsx`, `components/wiki/wiki-backlinks.tsx` |
| GET | `/api/projects/{projectId}/wiki/graph?offset=…&limit=…` | `wiki/graph/page.tsx` |
| POST | `/api/wiki/images/resolve` | `lib/hooks/use-image-resolver.ts` |

## Legal documents

| Method | Path | Called from |
|---|---|---|
| GET | `/api/wiki/legal-docs` | `app/(portal)/wiki/law/page.tsx` (team-owned) |
| GET | `/api/wiki/legal-docs/{key}` | `components/law/legal-doc-detail.tsx` |

## Skills and contributions

| Method | Path | Called from |
|---|---|---|
| GET | `/api/skills` | `app/(portal)/skills/page.tsx`, `skills/contribute-dialog.tsx` |
| GET | `/api/skills/{slug}[?version=…]` | `app/(portal)/skills/[slug]/page.tsx` |
| PATCH | `/api/skills/{id}` | `skills/skill-rename-dialog.tsx` |
| DELETE | `/api/skills/{id}` | `skills/page.tsx`, `skills/[slug]/page.tsx` |
| GET | `/api/skills/{slug}/content` | `skills/page.tsx`, `skills/skill-grid.tsx`, `skills/skill-compose-dialog.tsx` |
| PUT | `/api/skills/{slug}/content` | `skills/skill-compose-dialog.tsx` |
| GET | `/api/skills/{slug}/versions` | `skills/[slug]/page.tsx` |
| POST | `/api/skills/{slug}/set-latest` | `skills/[slug]/page.tsx` |
| POST (multipart) | `/api/skills/{slug}/reupload` | `skills/[slug]/page.tsx`, `skills/skill-reupload-dialog.tsx` |
| GET | `/api/skills/{id}/files[?version…]` | `skills/skill-file-explorer.tsx` |
| GET | `/api/skills/{id}/files/content?path=…` | `skills/skill-file-explorer.tsx`, `skills/skill-editor.tsx` |
| POST | `/api/skills/compose` | `skills/skill-compose-dialog.tsx` |
| POST (multipart) | `/api/skills/upload` | `skills/skill-upload-dialog.tsx` |
| GET | `/api/skill-contributions` | `skills/my-contributions.tsx` |
| POST | `/api/skill-contributions` | `skills/contribute-dialog.tsx` |
| GET | `/api/skill-contributions/{id}` | `skills/skill-editor.tsx` |
| DELETE | `/api/skill-contributions/{id}` | `skills/my-contributions.tsx`, `skills/contribution-dialogs.tsx` |
| POST | `/api/skill-contributions/{id}/submit` | `skills/contribution-dialogs.tsx` |
| POST | `/api/skill-contributions/{id}/approve` | `skills/contribution-dialogs.tsx` |
| POST | `/api/skill-contributions/{id}/reject` | `skills/contribution-dialogs.tsx` |
| GET | `/api/skill-contributions/{id}/diff-status` | `skills/skill-editor.tsx` |
| GET | `/api/skill-contributions/{id}/files` | `skills/skill-editor.tsx` |
| PUT | `/api/skill-contributions/{id}/files` | `skills/skill-editor.tsx` |
| DELETE | `/api/skill-contributions/{id}/files?path=…` | `skills/skill-editor.tsx` |
| GET | `/api/skill-contributions/{id}/files/content?path=…` | `skills/skill-editor.tsx` |
| POST | `/api/skill-contributions/{id}/rename?old_path=…&new_path=…` | `skills/skill-editor.tsx` |
| POST (multipart) | `/api/skill-contributions/{id}/upload?path=…` | `skills/skill-editor.tsx` |
| GET | `/api/admin/skill-contributions[?…]` | `app/(portal)/admin/skill-contributions/page.tsx`, `skills/pending-reviews.tsx` |

## Prompts

| Method | Path | Called from |
|---|---|---|
| GET | `/api/prompts` | `app/(portal)/prompts/page.tsx` |
| POST | `/api/prompts` | `components/prompts/prompt-dialog.tsx` |
| PATCH | `/api/prompts/{id}` | `components/prompts/prompt-dialog.tsx` |
| DELETE | `/api/prompts/{id}` | `app/(portal)/prompts/page.tsx` |

## Settings and RBAC

| Method | Path | Called from |
|---|---|---|
| GET | `/api/settings` | document-processing, OCR, embedding and model-catalog cards |
| PUT | `/api/settings` | document-processing card, OCR card, `provider-model-picker.tsx` |
| GET | `/api/settings/llm/catalog` | `model-catalog-card.tsx` (via `settings/page.tsx` prop) |
| POST | `/api/settings/llm/switch` | `model-catalog-card.tsx` (via prop) |
| GET | `/api/settings/vision/catalog` | `model-catalog-card.tsx` (via prop) |
| POST | `/api/settings/vision/switch` | `model-catalog-card.tsx` (via prop) |
| GET | `/api/settings/embeddings/catalog` | `embedding-settings-card.tsx` |
| GET | `/api/settings/embeddings/status` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/switch` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/test` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/reindex-current` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/jobs/{jobId}/cancel` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/backfill-source-chunks?limit=500&force=…` | `embedding-settings-card.tsx` |
| POST | `/api/settings/embeddings/probe-dimension` | `custom-model-form.tsx` (team-owned) |
| POST | `/api/settings/models/discover` | `custom-model-form.tsx` (team-owned) |
| POST | `/api/settings/custom-models` | `custom-model-form.tsx` (team-owned) |
| DELETE | `/api/settings/custom-models` | `custom-model-form.tsx` (team-owned) |
| GET | `/api/settings/ocr/catalog` | `ocr-settings-card.tsx` (team-owned) |
| POST | `/api/settings/ocr/select` | `ocr-settings-card.tsx` (team-owned) |
| POST | `/api/settings/test-ocr` | `ocr-settings-card.tsx` (team-owned) |
| POST | `/api/settings/test-ocr-connection` | `ocr-settings-card.tsx` (team-owned) |
| POST | `/api/settings/test-extraction` | `document-processing-settings-card.tsx` (team-owned) |
| GET | `/api/rbac/matrix` | `roles-permissions-card.tsx` |
| PUT | `/api/rbac/matrix` | `roles-permissions-card.tsx` |

## Proxied but not called directly

`next.config.ts` also rewrites `/mcp`, `/mcp/:path*`, `/oauth/:path*` and
`/.well-known/:path*` to the backend so that MCP clients can reach them through the frontend
origin. The UI itself never calls these paths.
