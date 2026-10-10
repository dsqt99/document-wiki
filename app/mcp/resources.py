"""
Arkon MCP Resources — static/semi-static data exposed to Claude.

Resources provide context Claude can read at session start without calling a tool.
"""

from fastmcp import FastMCP
from loguru import logger


def register_resources(mcp: FastMCP):
    """Register MCP resources on the server."""

    @mcp.resource("arkon://about")
    async def about_arkon() -> str:
        """About this Arkon instance — capabilities and instructions."""
        return (
            "# Arkon Knowledge Base\n\n"
            "You are connected to an Arkon enterprise LLM Wiki. Knowledge is organized "
            "as interlinked markdown wiki pages, compiled from source documents by an "
            "LLM and kept up to date over time. Wiki pages contain the synthesis; raw "
            "sources are available for precise citations.\n\n"
            "## Wiki tools (use first)\n\n"
            "- **search_wiki**: Hybrid search (semantic + keyword + exact document "
            "number) over wiki pages and verbatim source passages\n"
            "- **read_wiki_index**: Catalog of the pages you can access\n"
            "- **read_wiki_page**: Read one wiki page by slug + its links\n"
            "- **list_wiki_pages**: Browse pages with filters (paginated)\n"
            "- **get_document_relations**: Amendments, replacements, repeals, "
            "guidance and references of a document/article, both directions\n\n"
            "## Raw source drill-down\n\n"
            "- **search_source_content**: Search inside source documents\n"
            "- **get_source**: Source metadata (title, type, page count, contributor)\n"
            "- **get_source_outline**: Heading-based table of contents\n"
            "- **get_source_pages**: Raw text of specific page ranges\n"
            "- **query_table**: Read-only SQL over an uploaded spreadsheet\n\n"
            "## Browsing & directory\n\n"
            "- **list_sources**: Browse all available source documents\n"
            "- **list_knowledge_types**: See classification scheme\n"
            "- **get_knowledge_type_docs**: Browse documents by knowledge type\n\n"
            "## Writing (contributors)\n\n"
            "- **edit_wiki_page** / **create_wiki_page**: Published immediately as "
            "a new version — confirm with the user first\n\n"
            "## Guidelines\n\n"
            "1. Always search the wiki before saying you don't know\n"
            "2. Follow `[[wikilinks]]` between pages to discover context\n"
            "3. Cite slugs for wiki facts, source IDs (and page numbers) for raw quotes\n"
        )

    @mcp.resource("arkon://wiki-index")
    async def wiki_index_resource() -> str:
        """Current wiki catalog — same content as the `read_wiki_index` tool."""
        from app.database import async_session_factory
        from app.mcp.tools import _get_identity
        from app.services import wiki_service

        identity, err = await _get_identity()
        if err:
            return err

        assert identity is not None
        try:
            async with async_session_factory() as session:
                return await wiki_service.render_scoped_index(
                    session,
                    allowed_kt_slugs=identity.allowed_knowledge_types,
                    department_ids=identity.department_ids,
                    all_scopes=identity.is_admin,
                )
        except Exception as e:
            logger.warning(f"Failed to load wiki index resource: {e}")
            return "Wiki index: failed to load."
