"""Chia chunk theo token (1.000–2.000 token mỗi chunk), không theo ký tự.

Không có bộ tách token của mô hình nhúng khi chạy offline (tiktoken phải tải từ điển từ Internet), nên dùng ước lượng
xác định: mỗi từ tính ceil(độ dài / 4) token, mỗi dấu câu 1 token. Tiếng Việt cho kết quả sát khoảng 1,2–1,5 token mỗi
âm tiết, hơi thiên cao, nghĩa là chunk không bao giờ vượt ngân sách của mô hình nhúng (>= 2.048 token).
"""

import re

from loguru import logger

from app.config import settings

MIN_TARGET_TOKENS = 1_000
MAX_TARGET_TOKENS = 2_000

_PIECE = re.compile(r"\w+|[^\w\s]")


def _clamped_target() -> int:
    wanted = int(settings.chunk_target_tokens)
    clamped = max(MIN_TARGET_TOKENS, min(MAX_TARGET_TOKENS, wanted))
    if clamped != wanted:
        logger.warning(
            f"CHUNK_TARGET_TOKENS={wanted} nằm ngoài khoảng {MIN_TARGET_TOKENS}–{MAX_TARGET_TOKENS}; dùng {clamped}."
        )
    return clamped


CHUNK_TARGET_TOKENS = _clamped_target()
# Phần gối đầu không vượt quá một phần tư chunk để chunk luôn tiến về phía trước.
CHUNK_OVERLAP_TOKENS = max(0, min(int(settings.chunk_overlap_tokens), CHUNK_TARGET_TOKENS // 4))


def _cost(piece: str) -> int:
    return -(-len(piece) // 4) if piece[0].isalnum() or piece[0] == "_" else 1


def estimate_tokens(text: str) -> int:
    return sum(_cost(m.group()) for m in _PIECE.finditer(text or ""))


def end_for_tokens(text: str, start: int, limit: int, tokens: int = CHUNK_TARGET_TOKENS) -> int:
    """Vị trí kết thúc để text[start:end] có khoảng `tokens` token, không vượt `limit`."""
    used = 0
    for m in _PIECE.finditer(text, start, limit):
        used += _cost(m.group())
        if used >= tokens:
            return m.end()
    return limit


def overlap_chars(span_chars: int) -> int:
    """Số ký tự gối đầu tương ứng phần token gối đầu, tính theo tỷ lệ của chunk vừa cắt."""
    if CHUNK_TARGET_TOKENS <= 0:
        return 0
    return span_chars * CHUNK_OVERLAP_TOKENS // CHUNK_TARGET_TOKENS
