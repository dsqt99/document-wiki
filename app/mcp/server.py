"""FastMCP server factory for Document Wiki (06 §1.1)."""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.middleware import ScopedToolsMiddleware
from app.mcp.resources import register_resources
from app.mcp.tools import register_tools

SERVER_NAME = "arkon"

INSTRUCTIONS = (
    "Document Wiki is the organisation's knowledge base. Always search Document Wiki before answering a question. "
    "Use the tools in this order: search_wiki, then read_wiki_page for the relevant hits, then "
    "read_wiki_index to browse, and finally the original-document tools (get_source_outline, "
    "get_source_pages) to confirm exact wording. For skills, call list_skills, then read_skill, then "
    "read_skill_file for bundled files. Always cite the wiki page slug or the source ID with its page number."
)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
    register_tools(mcp)
    register_resources(mcp)
    mcp.add_middleware(ScopedToolsMiddleware())
    return mcp
