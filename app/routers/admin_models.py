"""Settings -> LLM / Vision model catalogs and the active-model switch.

Endpoints (mounted under /api, permission org:settings:manage):
  GET  /settings/llm/catalog
  POST /settings/llm/switch
  GET  /settings/vision/catalog
  POST /settings/vision/switch
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import custom_models as cm
from app.ai import llm_catalog, vision_catalog
from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()

_PERM = "org:settings:manage"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LLMSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    context_window_tokens: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_vision: bool = False
    label: str
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_1m_output_tokens: Optional[float] = None
    notes: Optional[str] = None
    api_key_configured: bool
    api_key_config_key: str
    custom: bool = False
    base_url: Optional[str] = None
    protocol: Optional[str] = None
    group: str = "custom"


class LLMCatalogOut(BaseModel):
    active_spec_id: Optional[str] = None
    specs: list[LLMSpecOut]


class VisionSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    max_image_size_mb: int = 20
    label: str
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_image: Optional[float] = None
    notes: Optional[str] = None
    api_key_configured: bool
    api_key_config_key: str
    custom: bool = False
    base_url: Optional[str] = None
    protocol: Optional[str] = None
    group: str = "custom"


class VisionCatalogOut(BaseModel):
    active_spec_id: Optional[str] = None
    specs: list[VisionSpecOut]


class SwitchIn(BaseModel):
    model_spec_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _preset_key(db: AsyncSession, kind: str, provider: str) -> str:
    """`{kind}_api_key__{provider}`, else the legacy `{kind}_api_key` if it fits."""
    from app.ai.registry import _legacy_key_fits
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    key = await svc.get(f"{kind}_api_key__{provider}")
    if key:
        return key
    legacy = await svc.get(f"{kind}_api_key")
    return legacy if _legacy_key_fits(legacy, provider) else ""


async def _custom_key_ok(db: AsyncSession, model: cm.CustomModel) -> bool:
    return model.provider == "custom" or bool(await cm.resolve_api_key(db, model))


async def _active(db: AsyncSession, kind: str) -> Optional[str]:
    from app.ai.registry import ProviderRegistry

    reg = ProviderRegistry(db)
    try:
        if kind == "llm":
            return await reg.get_active_llm_spec_id()
        return await reg.get_active_vision_spec_id()
    except Exception:
        return None


async def _switch(db: AsyncSession, user: Employee, kind: str, spec_id: str) -> dict:
    from app.services.config_service import (
        ACTIVE_LLM_MODEL_KEY,
        ACTIVE_VISION_MODEL_KEY,
        ConfigService,
    )

    catalog = llm_catalog if kind == "llm" else vision_catalog
    spec_id = (spec_id or "").strip()
    if cm.is_custom(spec_id):
        model = await cm.get_custom(db, kind, spec_id)
        if model is None:
            raise HTTPException(status_code=400, detail=f"Unknown {kind} model: {spec_id}")
        if not await _custom_key_ok(db, model):
            raise HTTPException(
                status_code=400,
                detail=f"No {model.provider} API key configured. Save the API key first, then switch.",
            )
    else:
        try:
            spec = catalog.get_spec(spec_id)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown {kind} model: {spec_id}")
        if not await _preset_key(db, kind, spec.provider):
            raise HTTPException(
                status_code=400,
                detail=f"No {spec.provider} API key configured. Save the API key first, then switch.",
            )

    key = ACTIVE_LLM_MODEL_KEY if kind == "llm" else ACTIVE_VISION_MODEL_KEY
    await ConfigService(db).set(key, spec_id)
    await log_audit(db, user, f"switch_{kind}_model", "app_config", key, reason=f"model={spec_id}")
    await db.commit()
    return {"active_spec_id": spec_id}


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

@router.get("/settings/llm/catalog", response_model=LLMCatalogOut)
async def get_llm_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    specs: list[LLMSpecOut] = []
    for s in llm_catalog.list_specs():
        base_url, protocol = cm.provider_endpoint("llm", s.provider)
        specs.append(
            LLMSpecOut(
                id=s.id,
                provider=s.provider,
                model_id=s.model_id,
                context_window_tokens=s.context_window_tokens,
                max_output_tokens=s.max_output_tokens,
                supports_tools=s.supports_tools,
                supports_vision=s.supports_vision,
                label=s.label or s.model_id,
                cost_per_1m_input_tokens=s.cost_per_1m_input_tokens,
                cost_per_1m_output_tokens=s.cost_per_1m_output_tokens,
                notes=s.notes,
                api_key_configured=bool(await _preset_key(db, "llm", s.provider)),
                api_key_config_key=f"llm_api_key__{s.provider}",
                custom=False,
                protocol=protocol,
                group=s.provider,
            )
        )
    for m in await cm.list_custom(db, "llm"):
        try:
            base = llm_catalog.get_spec(m.id)
        except KeyError:
            base = None
        specs.append(
            LLMSpecOut(
                id=m.id,
                provider=m.provider,
                model_id=m.model_id,
                context_window_tokens=getattr(base, "context_window_tokens", 128000),
                max_output_tokens=getattr(base, "max_output_tokens", 8192),
                supports_tools=getattr(base, "supports_tools", True),
                supports_vision=getattr(base, "supports_vision", False),
                label=m.label or m.model_id,
                api_key_configured=await _custom_key_ok(db, m),
                api_key_config_key=cm.api_key_config_key("llm", m.id),
                custom=True,
                base_url=m.base_url,
                protocol=m.protocol,
                group=m.provider or "custom",
            )
        )
    return LLMCatalogOut(active_spec_id=await _active(db, "llm"), specs=specs)


@router.post("/settings/llm/switch")
async def switch_llm_model(
    body: SwitchIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    return await _switch(db, user, "llm", body.model_spec_id)


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------

@router.get("/settings/vision/catalog", response_model=VisionCatalogOut)
async def get_vision_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission(_PERM),
):
    specs: list[VisionSpecOut] = []
    for s in vision_catalog.list_specs():
        specs.append(
            VisionSpecOut(
                id=s.id,
                provider=s.provider,
                model_id=s.model_id,
                max_image_size_mb=s.max_image_size_mb,
                label=s.label or s.model_id,
                cost_per_1m_input_tokens=s.cost_per_1m_input_tokens,
                cost_per_image=s.cost_per_image,
                notes=s.notes,
                api_key_configured=bool(await _preset_key(db, "vision", s.provider)),
                api_key_config_key=f"vision_api_key__{s.provider}",
                custom=False,
                group=s.provider,
            )
        )
    for m in await cm.list_custom(db, "vision"):
        specs.append(
            VisionSpecOut(
                id=m.id,
                provider=m.provider,
                model_id=m.model_id,
                label=m.label or m.model_id,
                api_key_configured=await _custom_key_ok(db, m),
                api_key_config_key=cm.api_key_config_key("vision", m.id),
                custom=True,
                base_url=m.base_url,
                protocol=getattr(m, "protocol", None),
                group=m.provider or "custom",
            )
        )
    return VisionCatalogOut(active_spec_id=await _active(db, "vision"), specs=specs)


@router.post("/settings/vision/switch")
async def switch_vision_model(
    body: SwitchIn,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission(_PERM),
):
    return await _switch(db, user, "vision", body.model_spec_id)
