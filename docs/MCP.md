# MCP & Claude Integration

Arkon exposes a Model Context Protocol (MCP) server at `/mcp`. Employees connect Claude Desktop — or any MCP-compatible client — and Claude gets access to the compiled wiki, raw source documents, and AI skills, all filtered to the employee's permission scope.

---

## Connecting Claude Desktop

Arkon uses **OAuth 2.1 with PKCE** — employees authenticate through a browser login instead of manually copying tokens into config files.

### Step 1 — Add Arkon to Claude Desktop config

Locate the Claude Desktop config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the Arkon server — just the URL, no token needed:

```json
{
  "mcpServers": {
    "arkon": {
      "url": "https://your-arkon-server/mcp"
    }
  }
}
```

### Step 2 — Restart Claude Desktop and connect

Restart Claude Desktop. When you open a new chat, Claude will prompt you to connect to Arkon. Click **Connect** — a browser window opens with the Arkon login form.

### Step 3 — Sign in

Enter your Arkon email and password. After a successful login, the browser closes and Claude Desktop is connected. Arkon tools will appear in Claude's tool list.

> **Behind the scenes:** Arkon implements RFC 8414 (OAuth Authorization Server Metadata), RFC 7591 (Dynamic Client Registration), and Authorization Code + PKCE (RFC 7636). Claude Desktop discovers the OAuth endpoints automatically from `/.well-known/oauth-authorization-server` and handles the full flow.

---

## Connecting Claude.ai (web)

Claude.ai supports remote MCP connectors with OAuth. Go to **Claude.ai → Settings → Connectors → Add custom connector**:

| Field | Value |
|---|---|
| Name | `Arkon` |
| Remote MCP server URL | `https://your-arkon-server/mcp` |
| OAuth Client ID | *(leave blank)* |
| OAuth Client Secret | *(leave blank)* |

Click **Add** — Claude.ai will discover the OAuth endpoints and redirect you to the Arkon login form.

---

## Authentication

Every MCP request is authenticated via bearer token resolved from the OAuth flow. The token is tied to an employee identity that determines:
- Which knowledge types the employee can access
- Which departments' documents are visible
- Which workspaces they are a member of
- Whether they have write/review permissions

Tokens can be revoked at any time from the Admin Portal (**Employees → [employee] → Revoke Token**).

### Legacy: manual Bearer token (local dev / API testing)

For local development or direct API testing you can still use a token directly. Generate one from the Admin Portal (**Employees → [employee] → Generate Token**) and pass it as a header:

```
Authorization: Bearer ark_xxxxxxxxxxxxxxxxxxxx
```

Or add it to `claude_desktop_config.json` manually:

```json
{
  "mcpServers": {
    "arkon": {
      "url": "http://localhost:5055/mcp",
      "headers": {
        "Authorization": "Bearer ark_xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Connecting Cursor / Windsurf / LibreChat

#### Cursor (`~/.cursor/mcp.json` or Project `.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "arkon": {
      "url": "http://localhost:5055/mcp",
      "headers": {
        "Authorization": "Bearer ark_xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

#### Generic SSE / HTTP Client (e.g. LibreChat, LangChain, Custom Agent)
- **Endpoint**: `http://localhost:5055/mcp` (or `https://your-domain/mcp`)
- **Protocol**: Model Context Protocol (Streamable HTTP / SSE)
- **Header**: `Authorization: Bearer <mcp-token>`

---

## Getting Claude to consistently use Arkon

Claude doesn't always call MCP tools automatically. Two ways to improve this:

### 1. MCP server instructions (built-in)

Arkon's MCP server already sends instructions to Claude on connect, telling it to query Arkon first before answering company-related questions. This works automatically with no setup.

### 2. Claude Desktop Custom Instructions (recommended)

In Claude Desktop, go to **Settings → Custom Instructions** and add:

```
Whenever answering questions related to the company — its processes, products,
people, departments, policies, or projects — always search Arkon first using
the search_wiki tool before relying on general knowledge.
```

### 3. Claude Desktop Project Instructions (most effective)

Create a **Project** in Claude Desktop, add Arkon as a connector within that Project, and set Project Instructions. These act as a true system prompt scoped to that project:

```
You have access to the company knowledge base via Arkon.
Before answering any question that might have a company-specific answer,
call search_wiki to check Arkon. Always cite the wiki slug or source ID
in your answer so the user can verify.
```

---

## MCP Tool Reference

Tools are organized in two tiers by permission level: Read and Write.

### Tool visibility by identity

`tools/list` is filtered per bearer token: a tool only appears in the catalog
if the caller's `ResolvedIdentity` could actually use it. This is enforced by
`ScopedToolsMiddleware` ([app/mcp/middleware.py](../app/mcp/middleware.py)).

| Caller | Visible tiers |
|---|---|
| Admin (`role = admin`) | All tiers |
| Org perm `wiki:write:all` | Read + Write |
| Workspace editor (in any workspace) | Read + Write |
| Org perm `wiki:write:own_dept` | Read + Write |
| Workspace contributor (in any workspace) | Read + Write |
| Workspace viewer only / read-only employee | Read |
| Unauthenticated / invalid token | Read, with an "Authenticate to use" hint prepended to every description |

**Visibility is a UX gate, not a security boundary.** A client may still invoke
any tool by name regardless of whether it appeared in the catalog. Per-tool
permission checks inside tool bodies (e.g. `_can_review_page` / `_can_contribute_to_page`
for a specific wiki page) remain authoritative and MUST NOT be removed.

Role / token changes are not pushed mid-session. To pick up a new role, the
client should reconnect to the MCP server.

---

### Tier 1 — Read (all authenticated employees)

#### `search_wiki`
Hybrid search (semantic + keyword + exact document-number match) across wiki pages and verbatim source documents. Results are filtered to the employee's permission scope.

```
search_wiki(query: str, top_k: int = 10) → ranked wiki pages + source passages with scores
```

When the query contains an official document number (e.g. `136/2020/NĐ-CP`), exact matches are pinned to the top and labelled "🎯 khớp chính xác". If one of the search arms fails, the response includes a warning that results may be incomplete.

#### `read_wiki_page`
Read the full markdown content of a specific wiki page.

```
read_wiki_page(slug: str) → page content, title, summary, backlinks, version
```

#### `list_wiki_pages`
Browse wiki pages by type or knowledge category.

```
list_wiki_pages(page_type?: str, knowledge_type?: str, query?: str, limit: int = 50, offset: int = 0)
```

`limit` is capped at 50; when more pages exist the response includes an `offset` hint for the next page.

#### `read_wiki_index`
Get the full wiki catalog (all pages with slug, type, summary).

```
read_wiki_index() → catalog of all accessible pages
```

Only pages the caller can access are listed (same for the `arkon://wiki-index` resource).

#### `get_document_relations`
Relations between numbered documents/articles — amendments, supplements, replacements, repeals, guidance, legal basis, cross-references — in both directions. Works for any document with an official number (decrees, circulars, decisions, official letters, internal regulations).

```
get_document_relations(doc_number?: str, article_number?: str, slug?: str, limit: int = 50)
→ validity warnings + outgoing ("Văn bản này tác động đến") and incoming ("Bị tác động bởi") relations
```

#### `list_sources`
Browse uploaded source documents visible to this employee.

```
list_sources(knowledge_type_slug?: str, limit: int = 20)
```

#### `get_source`
Get metadata and processing status for a source document.

```
get_source(source_id: str) → title, type, status, knowledge_type
```

#### `get_source_outline`
Get the table of contents (heading tree) of a source document.

```
get_source_outline(source_id: str) → hierarchical heading structure
```

#### `get_source_pages`
Read raw text from specific pages of a source document. Useful for exact citations.

```
get_source_pages(source_id: str, pages: str) → raw text (e.g. pages="5-7")
```

#### `search_source_content`
Search inside the full text of raw source documents (`.xlsx`, `.pdf`, `.docx`, `.txt`, URLs). Supports natural language questions, exact keywords, and multi-term queries with snippet extraction and highlighting.

```
search_source_content(query: str, limit: int = 10, offset: int = 0) → matched sources, page numbers, highlighted snippets
```

#### `list_knowledge_types`
List all knowledge type categories defined in the system.

```
list_knowledge_types() → name, slug, description for each type
```

#### `get_knowledge_type_docs`
List all source documents of a specific knowledge type.

```
get_knowledge_type_docs(knowledge_type_slug: str) → documents in this category
```

---

### Tier 2 — Write (contributor+, i.e. `CAN_CONTRIBUTE_WIKI`)

Wiki edits publish immediately — there is no draft queue and no review step. Every write creates a new page version in history. **Always confirm the change with the user before calling a write tool.**

#### `edit_wiki_page`
Edit an existing wiki page. Published immediately as a new version. Allowed when the caller can review **or** contribute to the page.

```
edit_wiki_page(
  slug: str,
  content_md: str,
  note?: str,
  scope_type?: "global" | "department",
  scope_id?: str,
  base_version?: int,
  allow_row_removal: bool = False,
) → "Page `{slug}` updated to v{version}. Note: ..."
```

- Read the page with `read_wiki_page()` first and send the **full** new content (not a diff, max 50,000 chars). Pass the version you read as `base_version`; if the page changed since, the edit is refused — re-read and re-apply the change.
- **Row-removal guard:** an edit that drops table rows of the current page is refused. Set `allow_row_removal=True` only when the user explicitly asked to delete those rows.
- If the slug exists in several scopes, the call fails with the candidate scopes — re-call with `scope_type` / `scope_id`.
- Reserved pages (`_index`, `_log`) cannot be edited.

Use `search_wiki()` or `read_wiki_index()` to find the right slug first.

#### `create_wiki_page`
Create a brand-new wiki page (contributor+). Published immediately at v1.

```
create_wiki_page(
  slug, title, content_md,
  page_type="concept",          # entity | concept | source | topic
  knowledge_type_slugs?=[],
  scope_type="global",          # global | department
  scope_id?,                    # required for department
  note?,
) → "Page `{slug}` created at v1. Note: ..."
```

Fails if the slug already exists in that scope — use `edit_wiki_page()` instead. Run `search_wiki()` first to avoid duplicates.

---

## Out-of-scope discovery hint

When a non-admin caller searches or reads a slug that exists in a scope they cannot access (a different department, a workspace they aren't a member of), the tools return a hint rather than silently hiding it:

```
search_wiki → response appends:
   **Out-of-scope matches** — matching page(s) exist outside your access:
   - 3 page(s) in department **HR** — contact the HR department admin to request access.
   - 1 page(s) in workspace **Marketing** — contact the workspace admin to be added as a member.

read_wiki_page → returns:
   Wiki page `slug` exists in department **HR** but you don't have access.
   Contact the scope's admin to request access.
```

The hint deliberately leaks **only** the scope label + count. Page titles, summaries, and content are never surfaced across a permission boundary. Admins bypass the hint because they already see everything.

---

## Permission scope in MCP

When an employee connects via MCP, their token resolves to a `ResolvedIdentity` that carries:

| Field | Meaning |
|---|---|
| `employee_id`, `employee_name` | Authenticated identity |
| `department_id`, `department_name` | The employee's department |
| `allowed_knowledge_types` | KT slugs the employee can access (`None` = unrestricted) |
| `allowed_source_ids` | Source IDs reachable via department / KT scope (`None` = unrestricted) |
| `project_ids` | UUIDs of active workspaces the employee is a member of |
| `project_source_ids` | Source IDs linked to those workspaces |
| `permissions` | Effective permission strings (e.g. `wiki:write:all`) |
| `is_admin` | System-admin override — bypasses all scope filters |

The wiki layer ORs three branches when filtering pages: global + own_dept + every workspace in `project_ids`. Workspace-scoped pages are now visible to their members via `search_wiki` / `list_wiki_pages` / `read_wiki_page` — this used to be a blindspot prior to commit `7676df5`.

### Tokens are hashed at rest

The MCP token returned by `generate_token` is the only time the plaintext exists outside the caller. Storage:

| Column | Holds |
|---|---|
| `employees.mcp_token_hash` | `HMAC-SHA256(MCP_TOKEN_PEPPER, plaintext)`, hex |
| `employees.mcp_token_prefix` | First 12 chars of plaintext, for UI display |
| `employees.mcp_token_rotated_at` | When the current token was issued |

Verification recomputes the HMAC and looks up `mcp_token_hash`. A DB dump alone — without `MCP_TOKEN_PEPPER` — cannot forge tokens. Migration `027` zeroed every legacy plaintext token, so every user **must** rotate after deploying 0.7.2+.

### `last_connected` debounce

`verify_token` only writes `employees.last_connected` if the previous value is `>60s` old. The check is best-effort under concurrency — N simultaneous tool calls from one user can each decide to bump, but the spam is bounded by the single user's request rate, not Redis latency.

---

## Token management

| Action | Where |
|---|---|
| Generate token | Admin Portal → Employees → [employee] → Generate Token |
| Revoke token | Admin Portal → Employees → [employee] → Revoke Token |
| View active tokens | Admin Portal → Employees → [employee] → Tokens |

A single employee can have multiple active tokens (e.g. Claude Desktop + Claude.ai).

---

## Using Arkon with Claude.ai (remote MCP)

Claude.ai supports remote MCP servers. Add Arkon as a remote server with the same URL and token:

```
URL: https://your-arkon-server/mcp
Header: Authorization: Bearer ark_xxxxxxxxxxxxxxxxxxxx
```

The same tools and permission scoping apply.

---

## Example conversation

```
Employee: What is our fire safety evacuation procedure?

Claude: [calls search_wiki("fire safety evacuation")]
        [reads wiki page concept/fire-evacuation-procedure]

Based on your organization's SOPs, the fire safety evacuation procedure is...
[synthesized answer from the compiled wiki page]

For the exact wording from the original document, I can check:
[calls get_source_outline(source_id="...")]
[calls get_source_pages(source_id="...", pages="12-14")]
```

---

## Troubleshooting MCP connections

| Issue | Solution |
|---|---|
| "Couldn't connect" at start of OAuth flow | Arkon server not reachable, or OAuth endpoints not deployed — verify `GET /.well-known/oauth-authorization-server` returns JSON |
| Login form shows `http://` URLs instead of `https://` | Uvicorn not started with `--proxy-headers` — ensure `X-Forwarded-Proto` is forwarded by your reverse proxy |
| "Couldn't connect" after login | Token exchange failed — check server logs for errors in `/oauth/token` |
| Tools don't appear in Claude | Restart Claude Desktop after config changes |
| "Invalid or inactive token" | Token revoked — reconnect via OAuth to get a new one |
| Tools return empty results | Employee has no accessible knowledge types — check their role in the Admin Portal |
| Connection refused | Arkon API not running or not reachable from the client network |
| HTTPS certificate errors | Configure a valid TLS certificate on your Arkon server |
| Claude doesn't use Arkon tools | Add instructions in Claude Desktop Custom Instructions or Project Instructions (see above) |
