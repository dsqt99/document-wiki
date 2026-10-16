"""Correlation id of the current request, shared with the audit chain (X-Correlation-ID)."""

import uuid
from contextvars import ContextVar, Token
from typing import Optional

_trace_id: ContextVar[Optional[str]] = ContextVar("audit_trace_id", default=None)


def set_trace_id(value: str) -> Token:
    return _trace_id.set(value)


def reset_trace_id(token: Token) -> None:
    _trace_id.reset(token)


def get_trace_id() -> Optional[str]:
    return _trace_id.get()


def new_trace_id() -> str:
    return str(uuid.uuid4())


class CorrelationIdMiddleware:
    """Pure ASGI middleware: reuse the caller's X-Correlation-ID or mint one, expose it to audit and echo it back."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for key, value in scope.get("headers", []):
            if key == b"x-correlation-id":
                incoming = value.decode("latin-1").strip()
                break
        correlation_id = incoming[:64] if incoming and incoming.isprintable() else new_trace_id()
        token = set_trace_id(correlation_id)

        async def send_with_header(message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-correlation-id"]
                headers.append((b"x-correlation-id", correlation_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            reset_trace_id(token)
