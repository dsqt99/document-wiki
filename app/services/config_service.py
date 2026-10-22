"""Runtime configuration stored in the app_config table (sensitive values encrypted)."""

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.database.models import AppConfig

logger = logging.getLogger(__name__)

ACTIVE_EMBEDDING_MODEL_KEY = "active_embedding_model_spec_id"
ACTIVE_LLM_MODEL_KEY = "active_llm_model_spec_id"
ACTIVE_VISION_MODEL_KEY = "active_vision_model_spec_id"

SENSITIVE_KEYS = {"embedding_api_key", "llm_api_key", "vision_api_key", "ocr_api_key", "reranker_api_key"}
_SENSITIVE_EXACT = SENSITIVE_KEYS | {"smtp_password", "webhook_secret"}
_SENSITIVE_PREFIXES = (
    "embedding_api_key__",
    "llm_api_key__",
    "vision_api_key__",
    "ocr_api_key__",
    "rerank_api_key__",
    "custom_model_api_key__",
)
_MASKED_PREFIX = "••••"


def _is_sensitive(key: str) -> bool:
    return key in _SENSITIVE_EXACT or key.startswith(_SENSITIVE_PREFIXES)


def _provider_value(p) -> str:
    return getattr(p, "value", p)


def embedding_api_key_for(p) -> str:
    return f"embedding_api_key__{_provider_value(p)}"


def llm_api_key_for(p) -> str:
    return f"llm_api_key__{_provider_value(p)}"


def vision_api_key_for(p) -> str:
    return f"vision_api_key__{_provider_value(p)}"


DEFAULT_OCR_PROMPT = (
    "Hãy trích xuất toàn bộ chữ trong ảnh trang tài liệu này, đúng nguyên văn từng chữ. "
    "Giữ nguyên số hiệu văn bản, ngày tháng, con số và chữ viết tắt. "
    "Nếu có bảng, dựng lại thành bảng Markdown. "
    "Dựng lại cấu trúc Phần, Chương, Mục, Điều, Khoản, Điểm thành tiêu đề Markdown tương ứng. "
    "Chỉ trả về nội dung đã trích xuất, không thêm bình luận, giải thích hay lời dẫn."
)

DEFAULT_CONFIG_VALUES: dict[str, str] = {
    "ocr_prompt": DEFAULT_OCR_PROMPT,
    "ocr_mode": "auto",
    "ocr_fallback_vision": "true",
    "ocr_llm_refine": "false",
    "pdf_parser_engine": "pdfplumber",
    "excel_parser_engine": "openpyxl",
    "pdf_strip_headers_footers": "true",
    "pdf_enhance_headings": "true",
    "wiki_rerank_enabled": "true",
    "wiki_rerank_threshold": "0.3",
}

ALL_CONFIG_KEYS: list[str] = [
    "active_reranker_model_spec_id", "wiki_rerank_enabled", "wiki_rerank_threshold",
    "rerank_api_key__openai", "rerank_api_key__anthropic", "rerank_api_key__google",
    "reranker_base_url", "reranker_api_key", "reranker_model",
    # Embedding
    ACTIVE_EMBEDDING_MODEL_KEY, "embedding_api_key__google", "embedding_api_key__openai", "embedding_base_url",
    # LLM
    ACTIVE_LLM_MODEL_KEY, "llm_api_key__openai", "llm_api_key__anthropic", "llm_api_key__google",
    "llm_api_key", "llm_base_url",
    # Vision
    ACTIVE_VISION_MODEL_KEY, "vision_api_key__openai", "vision_api_key__anthropic", "vision_api_key__google",
    "vision_api_key", "vision_base_url",
    # OCR
    "ocr_base_url", "ocr_api_key", "ocr_api_key__openai", "ocr_api_key__anthropic", "ocr_api_key__google",
    "ocr_model", "ocr_prompt", "ocr_mode", "ocr_fallback_vision", "ocr_llm_refine",
    # Parsers
    "pdf_parser_engine", "excel_parser_engine", "pdf_strip_headers_footers", "pdf_enhance_headings",
    # Legacy LLM / vision
    "llm_provider", "llm_model_id", "vision_provider", "vision_model_id",
    # Session / RBAC
    "session_timeout_minutes", "role_permissions_custom",
    # Legacy embedding
    "embedding_provider", "embedding_model_id", "embedding_api_key", "embedding_dimensions",
]

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
        _fernet = Fernet(key)
    return _fernet


def _encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


def _mask(value: str) -> str:
    if len(value) > 8:
        return "•" * 8 + value[-4:]
    return "•" * len(value)


class ConfigService:
    def __init__(self, db):
        self.db = db

    async def get(self, key: str) -> Optional[str]:
        result = await self.db.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalar_one_or_none()
        if row is not None and row.value:
            if _is_sensitive(key):
                try:
                    return _decrypt(row.value)
                except Exception:
                    logger.warning("Could not decrypt config key %s; returning stored value", key)
                    return row.value
            return row.value
        env_value = getattr(settings, key, None)
        if env_value is not None and str(env_value).strip() != "":
            return str(env_value)
        if key in DEFAULT_CONFIG_VALUES:
            return DEFAULT_CONFIG_VALUES[key]
        return None

    async def set(self, key: str, value: str) -> None:
        stored = value if value is None else str(value)
        if stored and _is_sensitive(key):
            stored = _encrypt(stored)
        result = await self.db.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalar_one_or_none()
        if row is None:
            self.db.add(AppConfig(key=key, value=stored))
        else:
            row.value = stored
            row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def get_all(self) -> dict:
        return {key: await self.get(key) for key in ALL_CONFIG_KEYS}

    async def get_all_for_ui(self) -> dict:
        out: dict = {}
        for key in ALL_CONFIG_KEYS:
            value = await self.get(key)
            if _is_sensitive(key) and value:
                out[key] = _mask(value)
            else:
                out[key] = value
            out[f"{key}_configured"] = bool(value)
        return out

    async def set_batch(self, updates: dict) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for key, value in updates.items():
            if key not in ALL_CONFIG_KEYS and not key.startswith("custom_model_api_key__"):
                results[key] = False
                continue
            if isinstance(value, str) and value.startswith(_MASKED_PREFIX):
                results[key] = True
                continue
            await self.set(key, "" if value is None else str(value))
            results[key] = True
        return results

    @staticmethod
    async def get_effective_config(db) -> dict:
        return await ConfigService(db).get_all()
