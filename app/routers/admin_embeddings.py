"""Settings -> Embedding: catalog, status, model switch (re-embed job), probes.

Endpoints (mounted under /api, permission org:settings:manage):
  GET  /settings/embeddings/catalog
  GET  /settings/embeddings/status
  POST /settings/embeddings/reindex-current
  POST /settings/embeddings/switch
  GET  /settings/embeddings/jobs/{job_id}
  POST /settings/embeddings/jobs/{job_id}/cancel
  POST /settings/embeddings/backfill-source-chunks
  POST /settings/embeddings/probe-dimension
  POST /settings/embeddings/test

Switching never changes the active spec directly: it creates an EmbeddingJob
and the worker flips the active spec only after everything is re-embedded.
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import custom_models as cm
from app.ai.embedding_catalog import SUPPORTED_DIMENSIONS, get_spec, list_specs
from app.database import get_db
from app.database.models import (
    EmbeddingJob,
    Employee,
    Source,
    WikiPage,
    get_source_chunk_embedding_model_for_dim,
    get_wiki_page_chunk_embedding_model_for_dim,
)
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()

_PERM = "org:settings:manage"
_ACTIVE_JOB_STATUSES = ("pending", "running")
_SKIP_SLUGS = ("_index", "_log")
_TEST_MAX_CHARS = 2000
_TEST_MAX_PASSAGES = 8
_PROBE_TEXT = "Xin chào"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EmbeddingSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    dimension: int
    label: str
    cost_per_1m_tokens: Optional[float] = None
    notes: Optional[str] = None
    api_key_configured: bool
    api_key_config_key: str
    custom: bool = False
    base_url: Optional[str] = None
    group: str = "custom"


class EmbeddingCatalogOut(BaseModel):
    active_spec_id: Optional[str] = None
    specs: list[EmbeddingSpecOut]


class EmbeddingJobOut(BaseModel):
    id: uuid.UUID
    model_spec_id: str
    status: str
    total_pages: Optional[int] = None
    done_pages: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmbeddingStatusOut(BaseModel):
    active_spec_id: Optional[str] = None
    total_pages: int
    embedded_pages: int
    total_sources: int = 0
    embedded_sources: int = 0
    wiki_chunks_count: int = 0
    source_chunks_count: int = 0
    current_job: Optional[EmbeddingJobOut] = None
    latest_job: Optional[EmbeddingJobOut] = None


class SwitchIn(BaseModel):
    model_spec_id: str


class ProbeIn(BaseModel):
    provider: str = "custom"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: str


class EmbeddingTestIn(BaseModel):
    model_spec_id: Optional[str] = None
    query: str = ""
    passages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_current_job(db: AsyncSession) -> Optional[EmbeddingJob]:
    """Newest job still pending or running, or None."""
    res = await db.execute(
        select(EmbeddingJob)
        .where(EmbeddingJob.status.in_(_ACTIVE_JOB_STATUSES))
        .order_by(EmbeddingJob.created_at.desc())
        .limit(1)
    )
    return res.scalars().first()


async def _get_latest_job(db: AsyncSession) -> Optional[EmbeddingJob]:
    res = await db.execute(select(EmbeddingJob).order_by(EmbeddingJob.created_at.desc()).limit(1))
    return res.scalars().first()


def _job_out(job: Optional[EmbeddingJob]) -> Optional[EmbeddingJobOut]:
    return EmbeddingJobOut.model_validate(job) if job is not None else None


async def _active_spec_id(db: AsyncSession) -> Optional[str]:
    from app.ai.registry import ProviderRegistry

    return await ProviderRegistry(db).get_active_embedding_spec_id()


async def _preset_key(db: AsyncSession, provider: str) -> str:
    from app.ai.registry import _legacy_key_fits
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    key = await svc.get(f"embedding_api_key__{provider}")
    if key:
        return key
    legacy = await svc.get("embedding_api_key")
    return legacy if _legacy_key_fits(legacy, provider) else ""


async def _enqueue(name: str, *args) -> Optional[str]:
    import app.worker as worker

    pool = await worker.get_arq_pool()
    job = await pool.enqueue_job(name, *args)
    return getattr(job, "job_id", None) if job is not None else None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _start_switch(db: AsyncSession, user: Employee, spec_id: str) -> dict:
    try:
        spec = get_spec(spec_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown embedding model: {spec_id}")

    current = await _get_current_job(db)
    if current is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Another embedding job is already {current.status}. "
                "Cancel it before starting a new switch."
            ),
        )

    if cm.is_custom(spec.id):
        model = await cm.get_custom(db, "embedding", spec.id)
        if model is None:
            raise HTTPException(status_code=400, detail=f"Unknown embedding model: {spec.id}")
        if model.provider != "custom" and not await cm.resolve_api_key(db, model):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No API key configured for provider '{model.provider}'. "
                    "Save the API key first, then switch."
                ),
            )
    elif not await _preset_key(db, spec.provider):
        raise HTTPException(
            status_code=400,
            detail=(
                f"No API key configured for provider '{spec.provider}'. "
                "Save the API key first, then switch."
            ),
        )

    job = EmbeddingJob(model_spec_id=spec.id, status="pending", done_pages=0)
    db.add(job)
    await db.flush()
    await log_audit(
        db, user, "switch_embedding_model", "embedding_job", str(job.id), reason=f"model={spec.id}"
    )
    await db.commit()

    try:
        await _enqueue("reembed_all_pages_task", str(job.id))
    except Exception as exc:
        logger.error(f"Could not enqueue reembed job {job.id}: {exc}")
        job.status = "failed"
        job.error_message = f"Enqueue failed: {exc}"[:2000]
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=500, detail=job.error_message)
    return {"job_id": str(job.id)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/settings/embeddings/catalog", response_model=EmbeddingCatalogOut)
async def get_embedding_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    specs: list[EmbeddingSpecOut] = []
    for s in list_specs():
        specs.append(
            EmbeddingSpecOut(
                id=s.id,
                provider=s.provider,
                model_id=s.model_id,
                dimension=s.dimension,
                label=s.label or s.model_id,
                cost_per_1m_tokens=s.cost_per_1m_tokens,
                notes=s.notes,
                api_key_configured=bool(await _preset_key(db, s.provider)),
                api_key_config_key=f"embedding_api_key__{s.provider}",
                custom=False,
                group=s.provider,
            )
        )
    for m in await cm.list_custom(db, "embedding"):
        if not m.dimension:
            continue
        key = await cm.resolve_api_key(db, m)
        specs.append(
            EmbeddingSpecOut(
                id=m.id,
                provider=m.provider,
                model_id=m.model_id,
                dimension=int(m.dimension),
                label=m.label or m.model_id,
                api_key_configured=bool(key) or m.provider == "custom",
                api_key_config_key=cm.api_key_config_key("embedding", m.id),
                custom=True,
                base_url=m.base_url,
                group=m.provider or "custom",
            )
        )
    return EmbeddingCatalogOut(active_spec_id=await _active_spec_id(db), specs=specs)


@router.get("/settings/embeddings/status", response_model=EmbeddingStatusOut)
async def get_embedding_status(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    active = await _active_spec_id(db)
    total_pages = (
        await db.execute(
            select(func.count()).select_from(WikiPage).where(WikiPage.slug.notin_(_SKIP_SLUGS))
        )
    ).scalar_one()
    total_sources = (await db.execute(select(func.count()).select_from(Source))).scalar_one()
    embedded_sources = (
        await db.execute(select(func.count()).select_from(Source).where(Source.chunk_status == "ready"))
    ).scalar_one()

    embedded_pages = wiki_chunks = source_chunks = 0
    if active:
        try:
            spec = get_spec(active)
        except KeyError:
            spec = None
        if spec is not None:
            WChunk = get_wiki_page_chunk_embedding_model_for_dim(spec.dimension)
            SChunk = get_source_chunk_embedding_model_for_dim(spec.dimension)
            embedded_pages = (
                await db.execute(
                    select(func.count(distinct(WChunk.page_id))).where(WChunk.model_spec_id == spec.id)
                )
            ).scalar_one()
            wiki_chunks = (
                await db.execute(
                    select(func.count()).select_from(WChunk).where(WChunk.model_spec_id == spec.id)
                )
            ).scalar_one()
            source_chunks = (
                await db.execute(
                    select(func.count()).select_from(SChunk).where(SChunk.model_spec_id == spec.id)
                )
            ).scalar_one()

    return EmbeddingStatusOut(
        active_spec_id=active,
        total_pages=int(total_pages or 0),
        embedded_pages=int(embedded_pages or 0),
        total_sources=int(total_sources or 0),
        embedded_sources=int(embedded_sources or 0),
        wiki_chunks_count=int(wiki_chunks or 0),
        source_chunks_count=int(source_chunks or 0),
        current_job=_job_out(await _get_current_job(db)),
        latest_job=_job_out(await _get_latest_job(db)),
    )


@router.post("/settings/embeddings/reindex-current")
async def reindex_current(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    active = await _active_spec_id(db)
    if not active:
        raise HTTPException(status_code=400, detail="Chưa có model embedding nào được kích hoạt")
    return await _start_switch(db, user, active)


@router.post("/settings/embeddings/switch")
async def switch_embedding_model(
    body: SwitchIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    return await _start_switch(db, user, body.model_spec_id.strip())


@router.get("/settings/embeddings/jobs/{job_id}", response_model=EmbeddingJobOut)
async def get_embedding_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    job = await db.get(EmbeddingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.post("/settings/embeddings/jobs/{job_id}/cancel", response_model=EmbeddingJobOut)
async def cancel_embedding_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    job = await db.get(EmbeddingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in _ACTIVE_JOB_STATUSES:
        raise HTTPException(status_code=400, detail=f"Job is {job.status}, cannot cancel")
    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    await log_audit(db, user, "cancel_embedding_job", "embedding_job", str(job.id))
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.post("/settings/embeddings/backfill-source-chunks")
async def backfill_source_chunks(
    limit: int = Query(500, ge=1, le=10000),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    stmt = select(func.count()).select_from(Source).where(
        Source.status.in_(("ready", "partial")),
        Source.full_text.isnot(None),
        Source.full_text != "",
    )
    if not force:
        stmt = stmt.where(Source.chunk_status.in_(("pending", "error")))
    candidates = min(int((await db.execute(stmt)).scalar_one() or 0), limit)
    if candidates == 0:
        return {
            "job_id": None,
            "candidates": 0,
            "enqueued": 0,
            "message": "Tất cả tài liệu đã có chunk văn bản gốc, không cần bổ sung.",
        }
    await log_audit(
        db, user, "backfill_source_chunks", "source", "*", reason=f"limit={limit} force={force}"
    )
    await db.commit()
    try:
        job_id = await _enqueue("backfill_source_chunks_task", limit, force)
    except Exception as exc:
        logger.error(f"Could not enqueue backfill_source_chunks_task: {exc}")
        raise HTTPException(status_code=500, detail=f"Enqueue failed: {exc}")
    return {
        "job_id": job_id,
        "candidates": candidates,
        "enqueued": candidates,
        "message": f"Đã xếp hàng tạo chunk văn bản gốc cho {candidates} tài liệu.",
    }


@router.post("/settings/embeddings/probe-dimension")
async def probe_dimension(
    body: ProbeIn,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    from app.ai.providers.base import ProviderConfig, ProviderType
    from app.ai.providers.openai_provider import OpenAIEmbedding

    provider = (body.provider or "custom").strip()
    model_id = (body.model_id or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
    if provider == "custom":
        base_url = (body.base_url or "").strip()
        if not base_url:
            raise HTTPException(status_code=400, detail="base_url is required")
        api_key = (body.api_key or "").strip()
    else:
        if provider not in cm.PROVIDERS or provider == "anthropic":
            raise HTTPException(status_code=400, detail=f"Unsupported embedding provider: {provider}")
        base_url, _ = cm.provider_endpoint("embedding", provider)
        api_key = (body.api_key or "").strip() or await _preset_key(db, provider)

    cfg = ProviderConfig(
        provider=ProviderType.OPENAI,
        api_key=api_key or "none",
        model_id=model_id,
        base_url=base_url,
        extra={"send_dimensions": False},
    )
    started = time.perf_counter()
    try:
        vector = await OpenAIEmbedding(cfg).embed(_PROBE_TEXT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gọi embedding thất bại: {exc}")
    latency_ms = int((time.perf_counter() - started) * 1000)
    dim = len(vector or [])
    return {"dimension": dim, "supported": dim in SUPPORTED_DIMENSIONS, "latency_ms": latency_ms}


@router.post("/settings/embeddings/test")
async def test_embedding(
    body: EmbeddingTestIn,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    from app.ai.registry import ProviderRegistry

    query = (body.query or "").strip()[:_TEST_MAX_CHARS]
    if not query:
        raise HTTPException(status_code=400, detail="Nhập câu truy vấn")
    passages = [(p or "")[:_TEST_MAX_CHARS] for p in (body.passages or [])][:_TEST_MAX_PASSAGES]
    passages = [p for p in passages if p.strip()]

    registry = ProviderRegistry(db)
    spec_id = (body.model_spec_id or "").strip() or await registry.get_active_embedding_spec_id()
    result = {
        "success": False,
        "model": spec_id,
        "dimension": None,
        "expected_dimension": None,
        "latency_ms": None,
        "similarities": [],
        "preview": [],
        "error": None,
    }
    if not spec_id:
        result["error"] = "Chưa có model embedding nào được kích hoạt"
        return result
    try:
        spec = get_spec(spec_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown embedding model: {spec_id}")
    result["expected_dimension"] = spec.dimension

    try:
        cfg = await registry._load_embedding_config(spec.id)
    except Exception as exc:
        result["error"] = str(exc)
        return result
    if not (cfg.api_key or "").strip():
        result["error"] = "Chưa có API key cho model này."
        return result

    started = time.perf_counter()
    try:
        q_provider = await registry.get_embedding(task="search_query", spec_id=spec.id)
        q_vec = list(await q_provider.embed(query))
        sims: list[float] = []
        if passages:
            d_provider = await registry.get_embedding(task="document", spec_id=spec.id)
            p_vecs = await d_provider.embed_batch(passages)
            sims = [round(_cosine(q_vec, list(v)), 4) for v in p_vecs]
    except Exception as exc:
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["error"] = str(exc)[:1000]
        return result

    result.update(
        success=True,
        dimension=len(q_vec),
        latency_ms=int((time.perf_counter() - started) * 1000),
        similarities=sims,
        preview=[round(float(x), 5) for x in q_vec[:8]],
    )
    return result
