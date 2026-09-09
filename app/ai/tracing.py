"""
Langfuse Tracing Integration for Arkon.

Provides centralized observability for LLM calls, embeddings, agent runs,
and background worker tasks (MRP pipeline, document ingestion, AI review).
Compatible with Langfuse Python SDK v4.x.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from loguru import logger

from app.config import settings

_langfuse_client: Optional[Any] = None
_langfuse_initialized: bool = False


def get_langfuse() -> Optional[Any]:
    """Get or initialize the Langfuse client singleton."""
    global _langfuse_client, _langfuse_initialized

    if not settings.langfuse_enabled:
        return None

    if not _langfuse_initialized:
        _langfuse_initialized = True
        pk = settings.langfuse_public_key or ""
        sk = settings.langfuse_secret_key or ""
        host = settings.effective_langfuse_host or "https://cloud.langfuse.com"

        if pk and sk:
            try:
                from langfuse import Langfuse

                _langfuse_client = Langfuse(
                    public_key=pk,
                    secret_key=sk,
                    host=host,
                )
                logger.info(f"Langfuse initialized successfully with host={host}")
            except Exception as e:
                logger.warning(f"Failed to initialize Langfuse: {e}")
                _langfuse_client = None
        else:
            _langfuse_client = None

    return _langfuse_client


def flush_langfuse() -> None:
    """Flush pending Langfuse events."""
    client = get_langfuse()
    if client:
        try:
            client.flush()
        except Exception as e:
            logger.debug(f"Langfuse flush error: {e}")


def shutdown_langfuse() -> None:
    """Shutdown Langfuse client gracefully."""
    client = get_langfuse()
    if client:
        try:
            client.shutdown()
        except Exception as e:
            logger.debug(f"Langfuse shutdown error: {e}")


@asynccontextmanager
async def trace_context(
    name: str,
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    input_data: Optional[Any] = None,
) -> AsyncGenerator[Optional[Any], None]:
    """
    Context manager to wrap an async task/operation in a Langfuse observation span.
    All inner observations and LLM generations will automatically nest inside this context.
    """
    client = get_langfuse()
    if not client:
        yield None
        return

    meta = dict(metadata or {})
    if tags:
        meta["tags"] = tags
    if trace_id:
        meta["trace_id"] = trace_id
    if user_id:
        meta["user_id"] = user_id
    if session_id:
        meta["session_id"] = session_id

    try:
        cm = client.start_as_current_observation(
            name=name,
            as_type="span",
            input=input_data,
            metadata=meta,
        )
    except Exception as e:
        logger.debug(f"Langfuse trace_context start error: {e}")
        yield None
        return

    with cm as span:
        yield span


def record_generation(
    name: str,
    model: str,
    input_data: Any,
    output_data: Any,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    usage: Optional[dict[str, int]] = None,
    metadata: Optional[dict[str, Any]] = None,
    model_parameters: Optional[dict[str, Any]] = None,
    level: str = "DEFAULT",
    status_message: Optional[str] = None,
) -> None:
    """Record an LLM generation observation in Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        obs_level = "ERROR" if level == "ERROR" else "DEFAULT"
        with client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input_data,
            metadata=metadata or {},
            model_parameters=model_parameters or {},
            level=obs_level,
            status_message=status_message,
            usage_details=usage,
        ) as gen:
            gen.update(
                output=output_data,
                usage_details=usage,
                level=obs_level,
                status_message=status_message,
            )
    except Exception as e:
        logger.debug(f"Langfuse record_generation error: {e}")


def record_embedding(
    name: str,
    model: str,
    input_texts: str | list[str],
    vector_dimension: int,
    tokens: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    level: str = "DEFAULT",
    status_message: Optional[str] = None,
) -> None:
    """Record an embedding generation observation in Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        obs_level = "ERROR" if level == "ERROR" else "DEFAULT"
        count = 1 if isinstance(input_texts, str) else len(input_texts)
        if tokens is None:
            if isinstance(input_texts, str):
                tokens = max(1, len(input_texts) // 4)
            else:
                tokens = max(1, sum(len(t) for t in input_texts) // 4)

        usage = {"input": tokens, "total": tokens}
        output_data = {"count": count, "dimension": vector_dimension}

        with client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input_texts,
            metadata=metadata or {},
            level=obs_level,
            status_message=status_message,
            usage_details=usage,
        ) as gen:
            gen.update(
                output=output_data,
                usage_details=usage,
                level=obs_level,
                status_message=status_message,
            )
    except Exception as e:
        logger.debug(f"Langfuse record_embedding error: {e}")


def sync_all_models_to_langfuse() -> int:
    """
    Sync all model specifications and pricing definitions from catalogs
    (LLM, Vision, Embedding) into Langfuse so that Langfuse automatically
    calculates usage cost and pricing metrics for all generations and embeddings.
    """
    client = get_langfuse()
    if not client:
        return 0

    from app.ai.embedding_catalog import EMBEDDING_CATALOG
    from app.ai.llm_catalog import LLM_CATALOG
    from app.ai.vision_catalog import VISION_CATALOG

    created_count = 0
    existing_model_names = set()

    try:
        # Fetch registered models from Langfuse (paginated, limit <= 50)
        for page in range(1, 10):
            models_resp = client.api.models.list(page=page, limit=50)
            if hasattr(models_resp, "data") and models_resp.data:
                for m in models_resp.data:
                    existing_model_names.add(m.model_name.lower())
                if len(models_resp.data) < 50:
                    break
            else:
                break
    except Exception as e:
        logger.debug(f"Could not list Langfuse models: {e}")

    # 1. Sync LLM Models
    for spec in LLM_CATALOG.values():
        if spec.model_id.lower() in existing_model_names:
            continue
        try:
            in_p = (spec.cost_per_1m_input_tokens or 0.0) / 1_000_000
            out_p = (spec.cost_per_1m_output_tokens or 0.0) / 1_000_000
            pattern = f"(?i)^({spec.provider}/)?{spec.model_id}.*"
            client.api.models.create(
                model_name=spec.model_id,
                match_pattern=pattern,
                unit="TOKENS",
                input_price=in_p,
                output_price=out_p,
            )
            existing_model_names.add(spec.model_id.lower())
            created_count += 1
            logger.info(f"Registered Langfuse LLM model '{spec.model_id}' (in=${in_p*1e6}/1M, out=${out_p*1e6}/1M)")
        except Exception as e:
            if "already exists" in str(e).lower():
                existing_model_names.add(spec.model_id.lower())
            else:
                logger.debug(f"Langfuse model register error for {spec.model_id}: {e}")

    # 2. Sync Embedding Models
    for spec in EMBEDDING_CATALOG.values():
        if spec.model_id.lower() in existing_model_names:
            continue
        try:
            in_p = (spec.cost_per_1m_tokens or 0.0) / 1_000_000
            pattern = f"(?i)^({spec.provider}/)?{spec.model_id}.*"
            client.api.models.create(
                model_name=spec.model_id,
                match_pattern=pattern,
                unit="TOKENS",
                input_price=in_p,
                output_price=0.0,
            )
            existing_model_names.add(spec.model_id.lower())
            created_count += 1
            logger.info(f"Registered Langfuse embedding model '{spec.model_id}' (cost=${in_p*1e6}/1M)")
        except Exception as e:
            if "already exists" in str(e).lower():
                existing_model_names.add(spec.model_id.lower())
            else:
                logger.debug(f"Langfuse embedding model register error for {spec.model_id}: {e}")

    # 3. Sync Vision Models
    for spec in VISION_CATALOG.values():
        if spec.model_id.lower() in existing_model_names:
            continue
        try:
            in_p = (spec.cost_per_1m_input_tokens or 0.0) / 1_000_000
            out_p = in_p  # standard fallback for multimodal tokens
            pattern = f"(?i)^({spec.provider}/)?{spec.model_id}.*"
            client.api.models.create(
                model_name=spec.model_id,
                match_pattern=pattern,
                unit="TOKENS",
                input_price=in_p,
                output_price=out_p,
            )
            existing_model_names.add(spec.model_id.lower())
            created_count += 1
            logger.info(f"Registered Langfuse vision model '{spec.model_id}' (in=${in_p*1e6}/1M)")
        except Exception as e:
            if "already exists" in str(e).lower():
                existing_model_names.add(spec.model_id.lower())
            else:
                logger.debug(f"Langfuse vision model register error for {spec.model_id}: {e}")

    return created_count
