"""Hide MCP tools the caller cannot use from ``tools/list``.

This is a convenience only: every tool still checks permissions itself.
"""

from __future__ import annotations

import logging

from fastmcp.server.middleware import Middleware

logger = logging.getLogger(__name__)

AUTH_HINT = "[Authenticate to use]"


def _requirement_of(tool):
    from app.mcp import permissions_compat

    fn = getattr(tool, "fn", None)
    return permissions_compat.requirement_for(fn) if fn is not None else permissions_compat.any_authenticated()


class ScopedToolsMiddleware(Middleware):
    async def on_list_tools(self, context, call_next):
        tools = list(await call_next(context))
        from app.mcp import permissions_compat
        from app.mcp import tools as mcp_tools

        try:
            identity, _err = await mcp_tools._get_identity()
        except Exception as e:
            logger.debug("tools/list identity lookup failed: %s", e)
            identity = None

        anyone = permissions_compat.any_authenticated()
        out = []
        for tool in tools:
            req = _requirement_of(tool)
            if identity is None:
                if req is not anyone and getattr(req, "label", None) != getattr(anyone, "label", None):
                    continue
                desc = (tool.description or "").strip()
                new_desc = f"{AUTH_HINT} {desc}" if desc else AUTH_HINT
                try:
                    tool = tool.model_copy(update={"description": new_desc})
                except Exception:
                    pass
                out.append(tool)
                continue
            try:
                allowed = req.allows(identity)
            except Exception:
                allowed = False
            if allowed:
                out.append(tool)
        return out
