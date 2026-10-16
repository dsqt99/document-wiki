"""
Dedicated OCR service using OpenAI-compatible vision/OCR endpoint (e.g. GLM-OCR).
Supports dynamic configuration from Database with fallback to environment variables.
"""

import asyncio
import base64
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from app.config import settings


# ---------------------------------------------------------------------------
# OCR output validation (ported from Tencent WeKnora ocr_sanitizer.go)
# ---------------------------------------------------------------------------

# Whole-reply "there is no text" answers that OCR / vision models produce for
# blank pages. Compared after lowercasing, stripping HTML tags, markdown
# emphasis and trailing punctuation.
_KNOWN_EMPTY_REPLIES = frozenset(
    {
        "no text",
        "no text content",
        "no text found",
        "no text detected",
        "no readable text",
        "no content",
        "empty",
        "none",
        "n/a",
        "không có văn bản",
        "không có nội dung",
        "không có nội dung văn bản",
        "không có chữ",
        "không có văn bản nào",
        "không tìm thấy văn bản",
        "không tìm thấy nội dung",
        "không phát hiện văn bản",
        "không nhận dạng được văn bản",
        "trang trống",
        "trang này không có văn bản",
        "hình ảnh không có văn bản",
        "ảnh không có văn bản",
        "无文字内容",
        "无法识别",
        "图片中没有文字",
        "图片中没有可识别的文字",
    }
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_FULL_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*[ \t]*\n(.*?)\n\s*```\s*$", re.DOTALL)
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")

# Repetition detection parameters (same as WeKnora).
_REP_MAX_PERIOD = 64
_REP_MIN_SPAN = 512
_REP_MIN_CYCLES = 32
_REP_REJECT_RATIO = 0.8


def _is_known_empty_reply(text: str) -> bool:
    plain = _HTML_TAG_RE.sub("", text or "")
    plain = plain.replace("&#46;", ".")
    plain = unicodedata.normalize("NFC", plain).strip().lower()
    plain = plain.strip("*_`#> \t\r\n\"'“”")
    plain = plain.rstrip(".!?。！？…")
    plain = " ".join(plain.split())
    return plain in _KNOWN_EMPTY_REPLIES


def _has_readable_char(text: str) -> bool:
    for ch in text:
        if ch.isalnum():
            return True
        # Math / currency symbols count (e.g. "±"), table delimiters do not.
        if unicodedata.category(ch).startswith("S") and ch not in "|~`":
            return True
    return False


def _repetition_coverage(text: str) -> float:
    """Fraction of (whitespace-normalized) text covered by long periodic runs.

    Counts the union of runs with period 1..64 that span >= 512 chars and
    >= 32 cycles, so split loops and loops with different periods separated
    by readable text are all counted, but each char only once. O(64*n).
    """
    runes = " ".join(text.split())
    n = len(runes)
    if n < _REP_MIN_SPAN:
        return 0.0
    coverage = [0] * (n + 1)
    for period in range(1, min(_REP_MAX_PERIOD, n // _REP_MIN_CYCLES) + 1):
        matched = 0
        for i in range(period, n + 1):
            if i < n and runes[i] == runes[i - period]:
                matched += 1
                continue
            span = matched + period
            if span >= _REP_MIN_SPAN and span >= period * _REP_MIN_CYCLES:
                coverage[i - span] += 1
                coverage[i] -= 1
            matched = 0
    active = repeated = 0
    for i in range(n):
        active += coverage[i]
        if active > 0:
            repeated += 1
    return repeated / n


def _trim_trailing_repetition(text: str) -> str:
    """Cut a long repetition loop at the end of ``text``, keeping one cycle.

    Decoding loops usually start late in the page and run until the token
    budget is exhausted. When the loop does not dominate the page (checked by
    the caller) the readable prefix is kept instead of discarding everything.
    """
    n = len(text)
    if n < _REP_MIN_SPAN:
        return text
    best_start: Optional[int] = None
    for period in range(1, min(_REP_MAX_PERIOD, n // _REP_MIN_CYCLES) + 1):
        i = n - 1
        while i - period >= 0 and text[i] == text[i - period]:
            i -= 1
        # text[i+1-period : n] is periodic with this period.
        start = i + 1 - period
        span = n - start
        if span >= _REP_MIN_SPAN and span >= period * _REP_MIN_CYCLES:
            keep_until = start + period
            if best_start is None or keep_until < best_start:
                best_start = keep_until
    if best_start is None:
        return text
    return text[:best_start].rstrip()


def validate_ocr_text(text: Optional[str], *, truncated: bool = False) -> tuple[str, Optional[str]]:
    """Validate and clean OCR / vision-LLM output for one page.

    Returns ``(cleaned_text, reason)``. ``reason`` is None when the text is
    usable; otherwise one of ``"empty_content"``, ``"no_text"``,
    ``"no_readable_content"``, ``"repetitive_content"``, ``"truncated"`` and
    the caller should treat the page as if OCR produced nothing.
    """
    cleaned = (text or "").strip()
    m = _FULL_FENCE_RE.match(cleaned)
    if m:
        cleaned = m.group(1).strip()
    cleaned = _MANY_NEWLINES_RE.sub("\n\n", cleaned.replace("\r\n", "\n")).strip()

    if not cleaned:
        return "", "empty_content"
    if _is_known_empty_reply(cleaned):
        return "", "no_text"
    if not _has_readable_char(_HTML_TAG_RE.sub("", cleaned)):
        return "", "no_readable_content"
    if _repetition_coverage(cleaned) >= _REP_REJECT_RATIO:
        return "", "repetitive_content"

    trimmed = _trim_trailing_repetition(cleaned)
    if trimmed != cleaned:
        logger.warning(
            f"OCR output ends in a repetition loop; trimmed {len(cleaned) - len(trimmed)} chars "
            f"(kept {len(trimmed)})"
        )
        if not trimmed or not _has_readable_char(trimmed):
            return "", "repetitive_content"
        cleaned = trimmed

    if truncated:
        # Partial output (finish_reason == "length") is incomplete and must not
        # be indexed as a successful page (WeKnora: ErrTruncatedCompletion).
        return cleaned, "truncated"
    return cleaned, None


def normalize_ocr_base_url(url: str) -> str:
    """Normalize base URL to ensure proper protocol and /v1 suffix."""
    url = (url or "").strip()
    if not url:
        return ""
    url = url.rstrip("/")
    if "://" in url:
        proto, path = url.split("://", 1)
        while "//" in path:
            path = path.replace("//", "/")
        url = f"{proto}://{path}"
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class OCRService:
    """Service for running dedicated OCR on document page images."""

    def __init__(self):
        self._cached_client = None
        self._cached_key: Optional[str] = None
        self._cached_url: Optional[str] = None

    def is_configured(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> bool:
        """Check if OCR base URL and API key are configured."""
        effective_url = base_url or settings.effective_ocr_base_url
        effective_key = api_key or settings.ocr_api_key
        return bool(effective_url and effective_key)

    def _get_client(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        from openai import OpenAI

        url = normalize_ocr_base_url(base_url) if base_url else settings.effective_ocr_base_url
        key = api_key or settings.ocr_api_key

        if not url or not key:
            raise ValueError("OCR Base URL and API Key must be provided.")

        # Cache default client if using settings
        if not base_url and not api_key:
            if (
                self._cached_client is not None
                and self._cached_url == url
                and self._cached_key == key
            ):
                return self._cached_client
            self._cached_client = OpenAI(
                base_url=url,
                api_key=key,
                default_headers={"User-Agent": "curl/8.5.0"},
                timeout=120.0,
            )
            self._cached_url = url
            self._cached_key = key
            return self._cached_client

        return OpenAI(
            base_url=url,
            api_key=key,
            default_headers={"User-Agent": "curl/8.5.0"},
            timeout=120.0,
        )

    def _call_ocr_stream_sync(
        self,
        b64_image: str,
        mime_type: str,
        prompt: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        with_finish_reason: bool = False,
    ) -> Any:
        """Synchronous helper executed in thread pool for streaming completion.

        Returns the text; with ``with_finish_reason=True`` returns
        ``(text, finish_reason)`` so callers can detect truncation ("length").
        """
        client = self._get_client(base_url=base_url, api_key=api_key)
        target_model = model or settings.ocr_model
        data_url = f"data:{mime_type};base64,{b64_image}"

        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            stream=True,
        )

        chunks: list[str] = []
        finish_reason: Optional[str] = None
        for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta and choice.delta.content:
                chunks.append(choice.delta.content)
            fr = getattr(choice, "finish_reason", None)
            if fr:
                finish_reason = fr

        text = "".join(chunks).strip()
        if with_finish_reason:
            return text, finish_reason
        return text

    async def test_connection(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[bool, str, int]:
        """
        Test connection to the OCR endpoint.
        Returns: (success: bool, message: str, latency_ms: int)
        """
        start_time = datetime.now(timezone.utc)
        try:
            client = self._get_client(base_url=base_url, api_key=api_key)
            target_model = model or settings.ocr_model

            # Try listing models or pinging endpoint
            def _check():
                try:
                    client.models.list()
                    return True, "Kết nối thành công tới endpoint OCR."
                except Exception as list_err:
                    logger.debug(f"models.list() failed ({list_err}), trying completion probe...")
                    try:
                        client.chat.completions.create(
                            model=target_model,
                            messages=[{"role": "user", "content": "ping"}],
                            max_tokens=1,
                            stream=False,
                        )
                        return True, f"Kết nối thành công tới OCR model '{target_model}'."
                    except Exception as comp_err:
                        raise comp_err

            success, msg = await asyncio.to_thread(_check)
            latency_ms = max(1, int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000))
            return success, msg, latency_ms

        except Exception as e:
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.warning(f"OCR test_connection failed: {e}")
            return False, f"Không thể kết nối tới OCR service: {str(e)}", latency_ms

    async def ocr_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        prompt: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Run OCR on image bytes using the configured OpenAI-compatible OCR model.
        Returns extracted text, or None if not configured or on failure.
        """
        effective_base_url = base_url
        effective_api_key = api_key
        effective_model = model
        effective_prompt = prompt

        if db is not None:
            try:
                from app.services.config_service import ConfigService

                cfg = ConfigService(db)
                if not effective_base_url:
                    effective_base_url = await cfg.get("ocr_base_url")
                if not effective_api_key:
                    effective_api_key = await cfg.get("ocr_api_key")
                if not effective_model:
                    effective_model = await cfg.get("ocr_model")
                if not effective_prompt:
                    effective_prompt = await cfg.get("ocr_prompt")
            except Exception as e:
                logger.warning(f"Error fetching dynamic OCR config from DB: {e}")

        effective_base_url = effective_base_url or settings.effective_ocr_base_url
        effective_api_key = effective_api_key or settings.ocr_api_key
        effective_model = effective_model or settings.ocr_model

        if not self.is_configured(base_url=effective_base_url, api_key=effective_api_key):
            return None

        ocr_prompt = effective_prompt or (
            "Trích xuất TOÀN BỘ văn bản từ hình ảnh trang tài liệu này một cách chính xác tuyệt đối.\n"
            "Yêu cầu nghiêm ngặt:\n"
            "1. Giữ nguyên số hiệu văn bản, tiêu đề, dấu câu, ngày tháng, các cụm từ viết tắt ngành (CAND, CSGT, PCCC, ANTT, QĐ, NĐ, TT...).\n"
            "2. Tái tạo chính xác cấu trúc bảng biểu dạng Markdown Table (| Cột 1 | Cột 2 |).\n"
            "3. Tái tạo cấu trúc thứ bậc đề mục: Phần, Chương, Mục, Điều, Khoản, Điểm.\n"
            "4. Tuyệt đối không thêm lời bình, không tóm tắt hay tự ý suy diễn từ ngữ."
        )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        start_time = datetime.now(timezone.utc)

        try:
            result = await asyncio.to_thread(
                self._call_ocr_stream_sync,
                b64_image,
                mime_type,
                ocr_prompt,
                effective_base_url,
                effective_api_key,
                effective_model,
                with_finish_reason=True,
            )
            # Tolerate mocks / overrides that still return a plain string.
            if isinstance(result, tuple):
                out_text, finish_reason = result
            else:
                out_text, finish_reason = result, None

            try:
                from app.ai.tracing import record_generation

                record_generation(
                    name="dedicated_ocr.stream",
                    model=effective_model,
                    input_data={
                        "prompt": ocr_prompt,
                        "mime_type": mime_type,
                        "image_size_bytes": len(image_bytes),
                    },
                    output_data=out_text,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                )
            except Exception:
                pass

            cleaned, reason = validate_ocr_text(
                out_text, truncated=(finish_reason == "length")
            )
            if reason:
                logger.warning(
                    f"Dedicated OCR output rejected ({reason}); raw_len={len(out_text or '')}, "
                    f"finish_reason={finish_reason}; preview: {(out_text or '')[:120]!r}"
                )
                return None
            return cleaned

        except Exception as e:
            logger.warning(f"Dedicated OCR failed: {e}")
            try:
                from app.ai.tracing import record_generation

                record_generation(
                    name="dedicated_ocr.stream",
                    model=effective_model,
                    input_data={
                        "prompt": ocr_prompt,
                        "mime_type": mime_type,
                        "image_size_bytes": len(image_bytes),
                    },
                    output_data=None,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    level="ERROR",
                    status_message=str(e),
                )
            except Exception:
                pass
            return None


ocr_service = OCRService()


OCR_REFINE_PROMPT = (
    "Bạn là người soát lỗi chính tả cho bản OCR của MỘT trang văn bản hành chính/pháp luật tiếng Việt. "
    "Ảnh đính kèm là đúng trang đó.\n\n"
    "NGUYÊN TẮC: Bản OCR bên dưới là bản gốc. Bạn chỉ sửa lỗi nhận dạng ký tự, KHÔNG viết lại văn bản.\n\n"
    "ĐƯỢC PHÉP sửa (chỉ khi nhìn rõ trên ảnh):\n"
    "- Dấu tiếng Việt sai/thiếu (\"Nghi đinh\" → \"Nghị định\").\n"
    "- Ký tự nhận dạng nhầm, chữ dính hoặc tách sai, số và ngày tháng đọc sai, số hiệu văn bản sai.\n"
    "- Dòng có trong ảnh mà bản OCR bỏ sót: chép đúng nguyên văn từ ảnh vào đúng vị trí.\n"
    "- Bảng bị vỡ cấu trúc: dựng lại thành bảng Markdown, giữ nguyên chữ trong ô.\n\n"
    "NGHIÊM CẤM:\n"
    "- Thêm bất kỳ nội dung nào KHÔNG nhìn thấy trên ảnh trang này. Không viết tiếp sang Điều/Khoản/trang sau, "
    "không bổ sung nội dung văn bản theo hiểu biết hay trí nhớ của bạn, kể cả khi trang kết thúc giữa câu.\n"
    "- Diễn đạt lại, thay từ đồng nghĩa, sửa văn phong, tóm tắt, đổi thứ tự dòng, bỏ dòng.\n"
    "- Chuẩn hóa hay \"sửa\" nội dung mà ảnh không cho thấy rõ là sai. Không chắc thì GIỮ NGUYÊN như bản OCR.\n"
    "- Thêm lời chào, lời giải thích, tiêu đề hay ghi chú của bạn.\n\n"
    "ĐẦU RA: chỉ toàn văn trang đã soát lỗi, cùng thứ tự dòng với bản OCR.\n\n"
    "=== BẢN OCR ===\n{draft}\n=== HẾT BẢN OCR ==="
)

# A refined page much shorter than the OCR draft is most likely truncated or a non-compliant summary.
_MIN_REFINE_RATIO = 0.5
# Proofreading changes characters, not content. Compared on accent-folded
# words (so diacritic fixes count as unchanged): the answer must keep most of
# the draft and add little that the draft did not have — otherwise the model
# rewrote the page or wrote text from memory.
_MAX_REFINE_RATIO = 1.6
_MIN_DRAFT_KEPT = 0.7
_MAX_NEW_WORDS = 0.35


def _fold_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"\w+", t)


def refine_drift(draft: str, refined: str) -> Optional[str]:
    """Why `refined` is not a proofread of `draft`, or None when it is."""
    from difflib import SequenceMatcher

    if len(refined) > len(draft) * _MAX_REFINE_RATIO + 200:
        return f"too_long ({len(refined)} vs draft {len(draft)} chars)"
    a, b = _fold_words(draft), _fold_words(refined)
    if not a or not b:
        return None
    same = sum(m.size for m in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    kept, new = same / len(a), (len(b) - same) / len(b)
    if kept < _MIN_DRAFT_KEPT:
        return f"draft_not_kept (kept={kept:.2f})"
    if new > _MAX_NEW_WORDS:
        return f"too_much_new_text (new={new:.2f})"
    return None


def _strip_fences(text: str) -> str:
    t = text.strip()
    if not t:
        return ""

    # Check if wrapped completely in ```markdown ... ```
    m = re.match(r"^```(?:markdown|md)?\s*\n?(.*?)\n?```$", t, re.DOTALL)
    if m:
        return m.group(1).strip()

    # If conversational text surrounds a markdown code block, extract the largest block
    blocks = re.findall(r"```(?:markdown|md)?\s*\n?(.*?)\n?```", t, re.DOTALL)
    if blocks:
        largest = max(blocks, key=len).strip()
        if largest:
            return largest

    # Fallback: strip leading / trailing fences
    if t.startswith("```"):
        lines = t.split("\n", 1)
        t = lines[1] if len(lines) > 1 else ""
    if t.rstrip().endswith("```"):
        t = t.rstrip()[:-3]
    return t.strip()


async def refine_ocr_with_llm(
    vision_provider: Any,
    image_bytes: bytes,
    mime_type: str,
    draft: str,
    max_tokens: int = 4096,
) -> Optional[str]:
    """Have the Vision LLM proofread an OCR draft against the page image.

    Returns the corrected text, or None (keep the draft) on failure or when
    the answer looks truncated.
    """
    if vision_provider is None or not draft.strip():
        return None
    try:
        import inspect

        sig = inspect.signature(vision_provider.analyze_image)
        kwargs = {}
        if "max_tokens" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            kwargs["max_tokens"] = max_tokens

        out = await vision_provider.analyze_image(
            image_bytes,
            mime_type=mime_type,
            prompt=OCR_REFINE_PROMPT.format(draft=draft.strip()),
            **kwargs,
        )
    except Exception as e:
        logger.warning(f"OCR LLM refine failed: {e}")
        return None

    refined = _strip_fences(out or "")
    draft_len = len(draft.strip())
    refined_len = len(refined)

    if refined_len < draft_len * _MIN_REFINE_RATIO:
        logger.warning(
            f"OCR LLM refine output looks truncated (refined_len={refined_len} vs draft_len={draft_len}, "
            f"ratio={refined_len / max(draft_len, 1):.2f}); preview: {refined[:200]!r}; keeping OCR draft"
        )
        return None

    drift = refine_drift(draft.strip(), refined)
    if drift:
        logger.warning(
            f"OCR LLM refine output rejected ({drift}): not a proofread of the OCR draft; "
            f"preview: {refined[:200]!r}; keeping OCR draft"
        )
        return None

    # A repetition loop makes the answer *longer* than the draft, so the
    # length check above does not catch it; validate the content itself.
    validated, reason = validate_ocr_text(refined)
    if reason:
        logger.warning(
            f"OCR LLM refine output rejected ({reason}); refined_len={refined_len}, "
            f"draft_len={draft_len}; keeping OCR draft"
        )
        return None
    refined = validated
    refined_len = len(refined)

    logger.info(
        f"OCR LLM refine successful: draft_len={draft_len} -> refined_len={refined_len}"
    )
    return refined
