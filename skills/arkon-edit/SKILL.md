---
name: arkon-edit
description: "Edit existing Arkon wiki pages or create new ones. Changes publish immediately as a new page version (no review queue), so always confirm with the user first. Contributor+ role required. Triggers on: update wiki, fix this page, edit wiki page, correct the KB, improve wiki, create new wiki page, add wiki page."
allowed-tools: mcp__arkon__search_wiki mcp__arkon__read_wiki_index mcp__arkon__list_wiki_pages mcp__arkon__read_wiki_page mcp__arkon__edit_wiki_page mcp__arkon__create_wiki_page
---

# arkon-edit: Edit the Knowledge Base

Edits publish **immediately** to the live KB as a new page version. There is no
draft, no editor queue and no review step — once you call the tool, every
reader sees the change. So:

- Always read the current page before changing it.
- Always confirm the exact change with the user before calling `edit_wiki_page`
  or `create_wiki_page`.

---

## Permissions

| Role | Tools | What happens |
|------|-------|--------------|
| Contributor+ (`CAN_CONTRIBUTE_WIKI`) | `edit_wiki_page`, `create_wiki_page` | Published immediately as a new version |
| Viewer / read-only | — | Write tools are refused |

`edit_wiki_page` succeeds when you can review **or** contribute to the target
page. A permission error means your token's scope doesn't cover that page —
tell the user to contact an Arkon admin; there is no fallback "propose" path.

---

## Workflow: Edit an existing page

1. **Find the page** — `search_wiki(query)`, `list_wiki_pages(query=...)` or
   `read_wiki_index()` to locate the slug.
2. **Read current content** — `read_wiki_page(slug)`. Note the page **version**.
   Never edit without reading first.
3. **Draft the edit** — produce the **full** updated Markdown (not a diff — the
   tool replaces the whole page).
4. **Confirm with user** — show a summary or diff of the changes. Get explicit
   approval.
5. **Publish** —
   `edit_wiki_page(slug, content_md, note="one-line explanation", base_version=<version read in step 2>)`.
6. Report the new version number returned.

### Version conflicts (`base_version`)

Always pass `base_version`. If someone else changed the page after you read it,
the call is refused ("page is now vN … Re-read the page and re-apply your
change"). Then: `read_wiki_page(slug)` again, re-apply the user's change on top
of the latest content, confirm again if the result differs materially, and
retry with the new `base_version`. Never blindly overwrite.

### Row-removal guard

An edit that drops table rows present in the current page is **refused**. This
protects against accidentally truncated content. If rows went missing, fix your
content so it keeps every existing row. Pass `allow_row_removal=True` **only**
when the user explicitly asked to delete those rows.

### Scope ambiguity

Pages live in `global` or `department` scope. If the same slug exists in
several scopes, `edit_wiki_page` fails and lists the candidate scopes. Ask the
user which one they mean, then re-call with `scope_type` and `scope_id`
(department UUID).

---

## Content rules

- Submit **full page content** — the tools replace, not patch.
- Max 50,000 characters per call.
- Cannot edit reserved pages: `_index`, `_log`.
- Preserve existing wikilinks `[[slug]]` unless intentionally removing them.
- Keep tables intact (see row-removal guard) and keep the page's existing
  frontmatter fields unless the change specifically needs to update them.
- Write a meaningful `note` — it is the only record of why the version changed.

---

## Creating a brand-new page

**First check whether one already exists.** Run `search_wiki(query)` and inspect
the top hits — if a matching page exists, edit it with `edit_wiki_page` instead.
`create_wiki_page` fails when the slug already exists in that scope.

```
create_wiki_page(
  slug, title, content_md,
  page_type="concept",            # entity | concept | source | topic
  knowledge_type_slugs=[...],     # taxonomy tags that drive RBAC visibility
  scope_type="global",            # global | department
  scope_id=None,                  # department UUID, required for department scope
  note="why this page should exist",
)
```

- `slug` — unique inside the chosen scope, no whitespace, not `_index`/`_log`.
- `knowledge_type_slugs` — ask the user which categories apply rather than guessing.

Workflow:
1. `search_wiki` to confirm nothing similar exists.
2. Show the user the proposed slug, title, page_type, knowledge_type_slugs,
   scope and the full content. Get explicit approval.
3. Call `create_wiki_page`. Report the created page and version (v1).

---

## When NOT to edit

- Do not edit without user instruction — even if you spot an error while
  querying. Point it out and ask.
- Do not call a write tool before the user has approved the exact change; it
  goes live immediately.
