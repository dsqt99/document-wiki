"""Per-model circuit breaker for the AI gateway.

When the gateway stops answering, every OCR/vision/LLM call otherwise waits out its own
timeout and retries, so one scanned PDF can hold a worker slot for the whole job timeout.
After a few consecutive transport failures the breaker opens and calls fail at once with
``UpstreamUnavailable``; the failed source carries ``AI_UNAVAILABLE_MARKER`` so
``resume_ai_unavailable_cron`` can re-queue it when the gateway is back.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

AI_UNAVAILABLE_MARKER = "[ai_unavailable]"
FAILURES_TO_OPEN = 3
OPEN_SECONDS = 120.0

# key -> (consecutive transient failures, monotonic time the breaker stays open until)
_state: dict[str, tuple[int, float]] = {}


class UpstreamUnavailable(RuntimeError):
    def __init__(self, key: str, detail: str = ""):
        self.key = key
        super().__init__(
            f"{AI_UNAVAILABLE_MARKER} Dịch vụ AI '{key}' không phản hồi{': ' + detail if detail else ''}. "
            "Nguồn sẽ tự chạy lại khi dịch vụ hoạt động trở lại."
        )


def is_transient(exc: BaseException) -> bool:
    """Connection errors, timeouts and 5xx: the gateway is unhealthy, not the request."""
    if isinstance(exc, UpstreamUnavailable):
        return False
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    try:
        import openai

        if isinstance(exc, openai.APIConnectionError):  # includes APITimeoutError
            return True
    except ImportError:
        pass
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status >= 500


def record_success(key: str) -> None:
    if _state.pop(key, None) is not None:
        logger.info("AI upstream '%s' is answering again", key)


def record_failure(key: str, exc: BaseException) -> None:
    if not is_transient(exc):
        return
    failures = _state.get(key, (0, 0.0))[0] + 1
    open_until = time.monotonic() + OPEN_SECONDS if failures >= FAILURES_TO_OPEN else 0.0
    if failures == FAILURES_TO_OPEN:
        logger.warning(
            "AI upstream '%s' failed %d times in a row; failing fast for %ds: %s",
            key, failures, int(OPEN_SECONDS), exc,
        )
    _state[key] = (failures, open_until)


def is_open(key: str) -> bool:
    return _state.get(key, (0, 0.0))[1] > time.monotonic()


def ensure_available(key: str) -> None:
    if is_open(key):
        raise UpstreamUnavailable(key)


def reset() -> None:
    _state.clear()
