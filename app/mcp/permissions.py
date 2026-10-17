"""Per-tool permission requirements for the MCP server.

Requirements drive tool-list filtering (display only); every tool still checks
permissions itself when it runs.
"""

from typing import Any, Callable

REQUIRES_ATTR = "__arkon_requires__"


class ToolRequirement:
    def __init__(self, predicate: Callable[[Any], bool], label: str = ""):
        self.predicate = predicate
        self.label = label

    def allows(self, identity) -> bool:
        if identity is None:
            return False
        try:
            return bool(self.predicate(identity))
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"ToolRequirement({self.label!r})"


def _is_admin(identity) -> bool:
    return bool(getattr(identity, "is_admin", False))


def _perms(identity) -> set:
    return set(getattr(identity, "permissions", None) or [])


ANY_AUTHENTICATED = ToolRequirement(lambda identity: True, "authenticated")
CAN_CONTRIBUTE_WIKI = ToolRequirement(
    lambda identity: _is_admin(identity) or bool(_perms(identity) & {"wiki:write:own_dept", "wiki:write:all"}),
    "wiki:write:*",
)
CAN_REVIEW_WIKI = ToolRequirement(
    lambda identity: _is_admin(identity) or "wiki:write:all" in _perms(identity),
    "wiki:write:all",
)
CAN_CREATE_WIKI_DIRECT = CAN_REVIEW_WIKI


def kb_tool(mcp, *, requires: ToolRequirement = ANY_AUTHENTICATED, **kwargs):
    """Register ``fn`` as an MCP tool and record its requirement on the function."""

    def decorator(fn):
        setattr(fn, REQUIRES_ATTR, requires)
        return mcp.tool(**kwargs)(fn)

    return decorator


def requirement_for(fn) -> ToolRequirement:
    for candidate in (fn, getattr(fn, "fn", None), getattr(fn, "__wrapped__", None)):
        if candidate is None:
            continue
        req = getattr(candidate, REQUIRES_ATTR, None)
        if isinstance(req, ToolRequirement):
            return req
    return ANY_AUTHENTICATED
