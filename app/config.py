"""Application settings loaded from environment / .env.

Derived values are plain properties so that tests can mutate fields on the
``settings`` singleton and observe the change immediately.
"""

from __future__ import annotations

import re

from pydantic_settings import BaseSettings, SettingsConfigDict

_CLOUD_LANGFUSE = "https://cloud.langfuse.com"


def _split_csv(raw: str | None) -> set[str]:
    return {part.strip() for part in (raw or "").split(",") if part.strip()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    database_url: str = "postgresql+asyncpg://arkon:arkon_secret@localhost:5432/arkon"
    secret_key: str = "change-me-to-a-random-secret-string"
    default_admin_email: str = "admin@arkon.local"
    default_admin_password: str = ""
    audit_hmac_key: str = ""
    mcp_token_pepper: str = "change-me-to-a-random-pepper"

    # Object storage
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = ""
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "arkon-files"
    minio_secure: bool = False
    minio_presign_expiry_hours: int = 24

    # HTTP
    cors_origins: str = "*"
    portal_base_url: str = ""

    # SSO
    sso_enabled: bool = False
    sso_issuer: str = ""
    sso_internal_issuer: str = ""
    sso_client_id: str = "cahy-wiki"
    sso_client_secret: str = ""
    sso_scopes: str = "openid email profile"
    sso_provider_name: str = "Công an tỉnh (SSO)"
    sso_auto_redirect: bool = False
    sso_allow_password_login: bool = True
    sso_admin_roles: str = "admin"
    sso_role_global_map: str = "qt-dl:knowledge_manager,qt-nd:viewer,qt-ai:viewer,qt-ht:viewer"
    sso_default_global_role: str = "viewer"
    sso_sync_roles: bool = True
    sso_sync_departments: bool = True
    sso_group_department_map: str = ""
    sso_trust_email: bool = False
    chatbot_url: str = ""
    chatbot_wiki_sso_secret: str = ""
    sso_mcp_clients: str = "cahy-chatbot"
    mcp_trust_forwarded_identity: bool = False

    # Redis / worker
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    worker_max_jobs: int = 3
    worker_job_timeout: int = 7200

    # Pipeline
    mrp_auto_approve_plan: bool = True
    mrp_multipass_writer_enabled: bool = True
    max_upload_size_bytes: int = 52428800
    allowed_upload_extensions: str = "pdf,docx,xlsx,pptx,txt,md,csv"
    auto_approve_extraction_threshold_tokens: int = 0
    # processing_mode=verbatim_page: longer documents are split into several linked pages.
    verbatim_page_max_chars: int = 40000
    extraction_approval_ttl_hours: int = 24
    max_auto_recover_attempts: int = 3

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = _CLOUD_LANGFUSE
    langfuse_base_url: str = ""
    langfuse_enabled: bool = True

    # Milvus
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_enabled: bool = False
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_database: str = "default"

    # OCR
    ocr_base_url: str = ""
    ocr_api_key: str = ""
    ocr_model: str = "ggml-org/GLM-OCR-GGUF:f16"

    # Reranker
    reranker_enabled: bool = True
    reranker_provider: str = "http"
    reranker_base_url: str = ""
    reranker_api_key: str = ""
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_n: int = 10

    # Chunking
    chunk_target_tokens: int = 1500
    chunk_overlap_tokens: int = 150

    # ---- derived -------------------------------------------------------

    @property
    def effective_ocr_base_url(self) -> str:
        raw = (self.ocr_base_url or "").strip()
        if not raw:
            return ""
        raw = raw.rstrip("/")
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*://)(.*)$", raw)
        if m:
            scheme, rest = m.group(1), m.group(2)
        else:
            scheme, rest = "", raw
        rest = re.sub(r"/{2,}", "/", rest)
        url = scheme + rest
        if not url.endswith("/v1"):
            url = url + "/v1"
        return url

    @property
    def effective_langfuse_host(self) -> str:
        return (self.langfuse_base_url or "").strip() or (self.langfuse_host or "").strip() or _CLOUD_LANGFUSE

    @property
    def sso_admin_role_set(self) -> set[str]:
        return _split_csv(self.sso_admin_roles)

    @property
    def sso_role_map(self) -> dict[str, str]:
        from app.services.sso_roles import parse_role_map

        return parse_role_map(self.sso_role_global_map)

    @property
    def sso_mcp_client_set(self) -> set[str]:
        return _split_csv(self.sso_mcp_clients)

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if raw == "*":
            return ["*"]
        return [p.strip() for p in raw.split(",") if p.strip()]


settings = Settings()
