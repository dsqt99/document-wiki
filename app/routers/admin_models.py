"""
Admin model-selection router for LLM and Vision capabilities.

Endpoints:
  GET  /api/settings/llm/catalog       — preset + admin-added LLMs + active spec
  POST /api/settings/llm/switch        — set the active LLM spec
  GET  /api/settings/vision/catalog    — preset + admin-added vision models + active spec
  POST /api/settings/vision/switch     — set the active vision spec

Presets come from the code catalogs; admin-added models ("custom/...") from
app/ai/custom_models.py (managed by admin_custom_models.py). Preset API keys
are stored per provider (`llm_api_key__<provider>`), custom keys per model.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LLMSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    context_window_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    label: str
    cost_per_1m_input_tokens: Optional[float]
    cost_per_1m_output_tokens: Optional[float]
    notes: Optional[str]
    api_key_configured: bool
    # app_config key the UI saves this model's API key under; None for custom
    # models (their key is saved with the model itself).
    api_key_config_key: Optional[str] = None
    custom: bool = False
    base_url: Optional[str] = None
    protocol: Optional[str] = None
    # Provider group shown in Settings: openai | anthropic | google | custom.
    group: str = "custom"


class LLMCatalogOut(BaseModel):
    active_spec_id: Optional[str]
    specs: list[LLMSpecOut]


class VisionSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    max_image_size_mb: int
    label: str
    cost_per_1m_input_tokens: Optional[float]
    cost_per_image: Optional[float]
    notes: Optional[str]
    api_key_configured: bool
    api_key_config_key: Optional[str] = None
    custom: bool = False
    base_url: Optional[str] = None
    protocol: Optional[str] = None
    # Provider group shown in Settings: openai | anthropic | google | custom.
    group: str = "custom"


class VisionCatalogOut(BaseModel):
    active_spec_id: Optional[str]
    specs: list[VisionSpecOut]


class SwitchBody(BaseModel):
    model_spec_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _preset_key_configured(db: AsyncSession, kind: str, provider: str) -> bool:
    from app.ai.registry import _legacy_key_fits
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    if await svc.get(f"{kind}_api_key__{provider}"):
        return True
    return _legacy_key_fits(provider, await svc.get(f"{kind}_api_key"))


async def _catalog_entries(db: AsyncSession, kind: str, specs, get_spec) -> list[dict]:
    """Preset specs followed by custom specs, as dicts of spec fields plus
    the key/custom metadata shared by both output schemas."""
    from dataclasses import asdict

    from app.ai.custom_models import list_custom, resolve_api_key

    out = []
    for s in specs:
        out.append({
            **asdict(s),
            "api_key_configured": await _preset_key_configured(db, kind, s.provider),
            "api_key_config_key": f"{kind}_api_key__{s.provider}",
            "group": s.provider,
        })
    for m in await list_custom(db, kind):
        spec = get_spec(m.id)
        out.append({
            **asdict(spec),
            "label": m.label or m.model_id,
            "api_key_configured": bool(await resolve_api_key(db, m)),
            "custom": True,
            "group": m.provider,
            "base_url": m.base_url,
            "protocol": m.protocol,
        })
    return out


async def _check_switchable(db: AsyncSession, kind: str, spec) -> None:
    from app.ai.custom_models import get_custom, is_custom, resolve_api_key

    if is_custom(spec.id):
        model = await get_custom(db, kind, spec.id)
        if model is None:
            raise HTTPException(status_code=400, detail=f"Unknown model {spec.id!r}")
        if model.provider != "custom" and not await resolve_api_key(db, model):
            raise HTTPException(
                status_code=400,
                detail=f"No {model.provider} API key configured. Save the API key first, then switch.",
            )
        return  # keyless local endpoints are allowed
    if not await _preset_key_configured(db, kind, spec.provider):
        raise HTTPException(
            status_code=400,
            detail=f"No {spec.provider} API key configured. Save the API key first, then switch.",
        )


# ---------------------------------------------------------------------------
# LLM endpoints
# ---------------------------------------------------------------------------

@router.get("/settings/llm/catalog", response_model=LLMCatalogOut)
async def get_llm_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.llm_catalog import get_spec, list_specs
    from app.ai.registry import ProviderRegistry

    active = await ProviderRegistry(db).get_active_llm_spec_id()
    entries = await _catalog_entries(db, "llm", list_specs(), get_spec)
    return LLMCatalogOut(active_spec_id=active, specs=[LLMSpecOut(**e) for e in entries])


@router.post("/settings/llm/switch")
async def switch_llm_model(
    body: SwitchBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.llm_catalog import UnknownLLMModel, get_spec
    from app.services.config_service import ACTIVE_LLM_MODEL_KEY, ConfigService

    try:
        spec = get_spec(body.model_spec_id)
    except UnknownLLMModel as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _check_switchable(db, "llm", spec)

    await ConfigService(db).set(ACTIVE_LLM_MODEL_KEY, spec.id)
    await log_audit(
        db, _user, "switch_llm_model", "settings", "global",
        reason=f"Switching active LLM to {spec.id}",
    )
    await db.commit()
    return {"active_spec_id": spec.id}


# ---------------------------------------------------------------------------
# Vision endpoints
# ---------------------------------------------------------------------------

@router.get("/settings/vision/catalog", response_model=VisionCatalogOut)
async def get_vision_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.registry import ProviderRegistry
    from app.ai.vision_catalog import get_spec, list_specs

    active = await ProviderRegistry(db).get_active_vision_spec_id()
    entries = await _catalog_entries(db, "vision", list_specs(), get_spec)
    return VisionCatalogOut(active_spec_id=active, specs=[VisionSpecOut(**e) for e in entries])


@router.post("/settings/vision/switch")
async def switch_vision_model(
    body: SwitchBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.vision_catalog import UnknownVisionModel, get_spec
    from app.services.config_service import ACTIVE_VISION_MODEL_KEY, ConfigService

    try:
        spec = get_spec(body.model_spec_id)
    except UnknownVisionModel as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _check_switchable(db, "vision", spec)

    await ConfigService(db).set(ACTIVE_VISION_MODEL_KEY, spec.id)
    await log_audit(
        db, _user, "switch_vision_model", "settings", "global",
        reason=f"Switching active vision model to {spec.id}",
    )
    await db.commit()
    return {"active_spec_id": spec.id}
