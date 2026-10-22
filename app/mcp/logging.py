"""Per-call logging of MCP tool invocations into ``mcp_query_log``.

Every wrapped call writes one row in a separate session, in the background.
Failures while writing are swallowed: logging must never change a tool result.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

current_identity: ContextVar[Any] = ContextVar("arkon_mcp_identity", default=None)

QUERY_TEXT_MAX = 2000
ERROR_MESSAGE_MAX = 1000

_DENIED_HINTS = (
    "authentication required",
    "invalid or inactive mcp token",
    "no http request context",
    "access denied",
    "you do not have permission",
    "not allowed",
    "forbidden",
)

_ZERO_HINTS = (
    "no wiki pages found",
    "no sources found",
    "no results",
    "no pages found",
    "no drafts pending",
    "no skills found",
)

_COUNT_PATTERNS = [
    re.compile(r"(\d+)\s+results?\b", re.IGNORECASE),
    re.compile(r"(\d+)\s+result\(s\)", re.IGNORECASE),
    re.compile(r"(\d+)\s+pages\s+found", re.IGNORECASE),
    re.compile(r"(\d+)\s+sources\s+found", re.IGNORECASE),
    re.compile(r"(\d+)\s+drafts\s+pending", re.IGNORECASE),
    re.compile(r"(\d+)\s+skill(?:\(s\)|s)?\b", re.IGNORECASE),
    re.compile(r"(\d+)\s+match(?:\(es\)|es)?\b", re.IGNORECASE),
]

_SINGLE_READ_TOOLS = {"read_wiki_page", "get_source", "read_skill", "read_skill_file"}

# Strong references to in-flight log writes so they are not garbage-collected.
_pending_writes: set[asyncio.Task] = set()


def classify_status(text: str) -> str:
    low = (text or "").lower()
    if any(h in low for h in _DENIED_HINTS):
        return "denied"
    stripped = low.lstrip()
    if stripped.startswith("error") or stripped.startswith("failed"):
        return "error"
    return "ok"


def count_results(tool_name: str, text: str) -> Optional[int]:
    low = (text or "").lower()
    if any(h in low for h in _ZERO_HINTS):
        return 0
    best: Optional[tuple[int, int]] = None
    for pat in _COUNT_PATTERNS:
        m = pat.search(text or "")
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), int(m.group(1)))
    if best is not None:
        return best[1]
    if tool_name in _SINGLE_READ_TOOLS:
        return 1
    return None


def _employee_id(identity) -> Optional[uuid.UUID]:
    value = getattr(identity, "employee_id", None) if identity is not None else None
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _scope_metadata(identity) -> Optional[dict]:
    if identity is None:
        return None
    meta: dict[str, Any] = {}
    is_admin = getattr(identity, "is_admin", None)
    if isinstance(is_admin, bool):
        meta["is_admin"] = is_admin
    clearance = getattr(identity, "clearance_level", None)
    if isinstance(clearance, str):
        meta["clearance"] = clearance
    role = getattr(identity, "delegated_role", None)
    if isinstance(role, str):
        meta["delegated_role"] = role
    depts = getattr(identity, "department_ids", None)
    if isinstance(depts, (list, tuple, set)):
        meta["department_ids"] = [str(d) for d in depts]
    return meta or None


async def _write_row(row: dict) -> None:
    try:
        from app import database
        from app.database.models import MCPQueryLog

        async with database.async_session_factory() as session:
            session.add(MCPQueryLog(**row))
            await session.commit()
    except Exception as e:  # pragma: no cover - logging must never fail a tool
        logger.debug("mcp_query_log write failed: %s", e)


def _schedule_write(row: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        task = loop.create_task(_write_row(row))
    except Exception:
        return
    _pending_writes.add(task)
    task.add_done_callback(_pending_writes.discard)


def _query_text(query_arg: Optional[str], args: tuple, kwargs: dict) -> Optional[str]:
    value = None
    if query_arg and query_arg in kwargs:
        value = kwargs.get(query_arg)
    elif args and isinstance(args[0], str):
        value = args[0]
    if value is None:
        return None
    return str(value)[:QUERY_TEXT_MAX]


def logged_tool(tool_name: str, query_arg: Optional[str] = None) -> Callable:
    """Wrap an async tool so each call leaves one ``mcp_query_log`` row."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            row: dict[str, Any] = {
                "tool_name": tool_name[:80],
                "query_text": _query_text(query_arg, args, kwargs),
            }
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                identity = current_identity.get()
                row.update(
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}"[:ERROR_MESSAGE_MAX],
                    employee_id=_employee_id(identity),
                    scope_metadata=_scope_metadata(identity),
                )
                _schedule_write(row)
                raise
            identity = current_identity.get()
            if isinstance(result, str):
                text = result
            elif hasattr(result, "content"):
                text = "\n".join(block.text for block in result.content if getattr(block,"type",None) == "text")
            else:
                text = str(result)
            status = classify_status(text)
            row.update(
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=status,
                result_count=count_results(tool_name, text) if status == "ok" else None,
                employee_id=_employee_id(identity),
                scope_metadata=_scope_metadata(identity),
            )
            _schedule_write(row)
            return result

        return wrapper

    return decorator
