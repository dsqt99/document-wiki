"""Token counting with tiktoken (cl100k_base), falling back to the offline estimate when the dictionary can't load."""

from loguru import logger

_encoder = None
_unavailable = False


def _get_encoder():
    global _encoder, _unavailable
    if _encoder is None and not _unavailable:
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            _unavailable = True
            logger.warning(f"tiktoken cl100k_base unavailable, using estimate_tokens instead: {e}")
    return _encoder


def count_tokens(text: str) -> int:
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is None:
        from app.services.chunk_budget import estimate_tokens

        return estimate_tokens(text)
    return len(encoder.encode(text, allowed_special="all"))
