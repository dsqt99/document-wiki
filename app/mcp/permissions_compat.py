"""Thin bridge to ``app.mcp.permissions``.

``app.mcp.permissions`` is the authoritative module. This bridge only exists so the
MCP server still registers its tools while that module is missing; the fallback
implements the same rules (06 §1.5).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

REQUIRES_ATTR = "__arkon_requires__"


@dataclass(frozen=True)
class _FallbackRequirement:
    predicate: Callable[[Any], bool]
    label: str = ""

    def allows(self, identity) -> bool:
        try:
            return bool(self.predicate(identity))
        except Exception:
            return False


def _perms(identity) -> set:
    try:
        return set(getattr(identity, "permissions", None) or [])
    except TypeError:
        return set()


def _is_admin(identity) -> bool:
    return getattr(identity, "is_admin", False) is True


_F_ANY = _FallbackRequirement(lambda i: True, "authenticated")
_F_CONTRIB = _FallbackRequirement(
    lambda i: _is_admin(i) or bool(_perms(i) & {"wiki:write:own_dept", "wiki:write:all"}), "wiki:write:*"
)
_F_REVIEW = _FallbackRequirement(lambda i: _is_admin(i) or "wiki:write:all" in _perms(i), "wiki:write:all")


def _module():
    try:
        return importlib.import_module("app.mcp.permissions")
    except ImportError:
        return None


def _const(name: str, fallback):
    mod = _module()
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback


def any_authenticated():
    return _const("ANY_AUTHENTICATED", _F_ANY)


def can_contribute_wiki():
    return _const("CAN_CONTRIBUTE_WIKI", _F_CONTRIB)


def can_review_wiki():
    return _const("CAN_REVIEW_WIKI", _F_REVIEW)


def requires_attr() -> str:
    return _const("REQUIRES_ATTR", REQUIRES_ATTR)


def requirement_for(fn):
    mod = _module()
    if mod is not None and hasattr(mod, "requirement_for"):
        return mod.requirement_for(fn)
    return getattr(fn, requires_attr(), None) or any_authenticated()


def kb_tool(mcp, *, requires=None, **kwargs):
    """Decorator: tag the function with its requirement, then register it on ``mcp``."""
    requires = requires if requires is not None else any_authenticated()
    mod = _module()
    if mod is not None and hasattr(mod, "kb_tool"):
        return mod.kb_tool(mcp, requires=requires, **kwargs)

    def decorator(fn):
        setattr(fn, requires_attr(), requires)
        mcp.tool(**kwargs)(fn)
        return fn

    return decorator
