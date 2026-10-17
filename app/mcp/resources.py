"""MCP resources of the Document Wiki knowledge base (06 §1.8)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ABOUT_MD = """# Document Wiki knowledge base

Document Wiki is the internal knowledge base: a curated wiki compiled from official documents, plus
the original documents themselves and a library of reusable skills.

## Tool groups

- **Wiki**: `search_wiki`, `read_wiki_page`, `read_wiki_index`, `list_wiki_pages`, `get_document_relations`.
- **Original documents (deep dive)**: `get_source`, `get_source_outline`, `get_source_pages`,
  `search_source_content`, `query_table`.
- **Catalog browsing**: `list_sources`, `list_knowledge_types`, `get_knowledge_type_docs`.
- **Skills**: `list_skills`, `read_skill`, `read_skill_file`.
- **Contributor writes**: `edit_wiki_page`, `create_wiki_page` (only shown to contributors).

## Principles

1. Search before saying "I don't know": run `search_wiki` (and source tools) first.
2. Follow wikilinks: `[[slug]]` links lead to related pages worth reading.
3. Cite your evidence: give the page slug, or the source ID together with the page number.
"""


def register_resources(mcp) -> None:
    @mcp.resource("arkon://about", name="about", description="What Document Wiki is and how to use its tools.",
                  mime_type="text/markdown")
    async def about() -> str:
        return ABOUT_MD

    @mcp.resource("arkon://wiki-index", name="wiki-index",
                  description="Wiki index scoped to the caller's permissions.", mime_type="text/markdown")
    async def wiki_index() -> str:
        from app.mcp import tools as mcp_tools

        identity, err = await mcp_tools._get_identity()
        if err:
            return err
        try:
            from app import database
            from app.services import wiki_service

            async with database.async_session_factory() as session:
                return await wiki_service.render_scoped_index(
                    session,
                    allowed_kt_slugs=getattr(identity, "allowed_knowledge_types", None),
                    department_ids=getattr(identity, "department_ids", None),
                    all_scopes=getattr(identity, "is_admin", False) is True,
                    clearance=mcp_tools._clearance(identity),
                    page_filter=mcp_tools._page_filter(identity),
                )
        except Exception as e:
            logger.warning("wiki-index resource failed: %s", e)
            return "Wiki index: failed to load."
