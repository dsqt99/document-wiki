"""
Admin-added models ("Thêm model") and OCR model selection.

Endpoints:
  GET    /api/settings/custom-models?kind=      — list admin-added models
  POST   /api/settings/custom-models            — add / update one (base URL + model name)
  DELETE /api/settings/custom-models?kind=&id=  — remove one (refused while active)
  GET    /api/settings/ocr/catalog              — OCR presets + custom OCR models
  POST   /api/settings/ocr/select               — make one the OCR model

The OCR service reads the flat keys ocr_base_url / ocr_model / ocr_api_key;
selecting a model writes those, so ocr_service needs no changes.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.custom_models import (
    EMBEDDING_DIMENSIONS,
    KINDS,
    MAX_MODEL_ID_LEN,
    PROTOCOLS,
    PROVIDERS,
    CustomModel,
    delete_custom,
    get_custom,
    is_custom,
    list_custom,
    make_id,
    provider_endpoint,
    provider_key_config_key,
    resolve_api_key,
    save_custom,
)
from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()

OCR_MODEL_SPEC_KEY = "ocr_model_spec_id"

# OCR goes through an OpenAI-compatible chat endpoint (ocr_service), so the
# Claude and Gemini presets use their providers' OpenAI-compatible base URLs.
def _ocr_preset(provider: str, model_id: str, label: str) -> tuple[str, dict]:
    base_url, _ = provider_endpoint("ocr", provider)
    return f"{provider}/{model_id}", {
        "provider": provider, "label": label, "base_url": base_url, "model_id": model_id,
    }


OCR_PRESETS: dict[str, dict] = dict([
    _ocr_preset("openai", "gpt-6-luna", "GPT-6 Luna"),
    _ocr_preset("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5"),
    _ocr_preset("anthropic", "claude-haiku-5-5", "Claude Haiku 5.5"),
    _ocr_preset("google", "gemini-3.5-flash", "Gemini 3.5 Flash"),
    _ocr_preset("google", "gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CustomModelOut(BaseModel):
    id: str
    kind: str
    model_id: str
    label: str
    base_url: str
    protocol: str
    dimension: Optional[int]
    provider: str
    api_key_configured: bool


class CustomModelIn(BaseModel):
    kind: str
    model_id: str
    # Known providers derive the endpoint; "custom" needs base_url.
    provider: str = "custom"
    base_url: Optional[str] = None
    label: Optional[str] = None
    protocol: str = "openai"
    dimension: Optional[int] = None
    # None or a masked value ("••••…") keeps the stored key.
    api_key: Optional[str] = None


class OcrModelOut(BaseModel):
    id: str
    provider: str
    label: str
    base_url: str
    model_id: str
    custom: bool
    # Provider group shown in Settings ("custom" = own endpoint).
    group: str
    api_key_configured: bool


class OcrCatalogOut(BaseModel):
    active_spec_id: Optional[str]
    specs: list[OcrModelOut]


class OcrSelectBody(BaseModel):
    model_spec_id: str
    api_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _to_out(db: AsyncSession, m: CustomModel) -> CustomModelOut:
    return CustomModelOut(
        id=m.id, kind=m.kind, model_id=m.model_id, label=m.label,
        base_url=m.base_url, protocol=m.protocol, dimension=m.dimension,
        provider=m.provider,
        api_key_configured=bool(await resolve_api_key(db, m)),
    )


def _new_key(api_key: Optional[str]) -> Optional[str]:
    if api_key is None or api_key.startswith("••••"):
        return None
    return api_key.strip()


async def _active_ids(db: AsyncSession) -> dict[str, Optional[str]]:
    from app.services.config_service import (
        ACTIVE_EMBEDDING_MODEL_KEY,
        ACTIVE_LLM_MODEL_KEY,
        ACTIVE_VISION_MODEL_KEY,
        ConfigService,
    )

    svc = ConfigService(db)
    return {
        "llm": await svc.get(ACTIVE_LLM_MODEL_KEY),
        "vision": await svc.get(ACTIVE_VISION_MODEL_KEY),
        "embedding": await svc.get(ACTIVE_EMBEDDING_MODEL_KEY),
        "ocr": await svc.get(OCR_MODEL_SPEC_KEY),
    }


async def resolve_ocr_endpoint(db: AsyncSession, spec_id: str) -> tuple[str, str, str]:
    """(base_url, model_id, api_key) of an OCR model, from its stored keys."""
    from app.services.config_service import ConfigService, vision_api_key_for

    if is_custom(spec_id):
        m = await get_custom(db, "ocr", spec_id)
        if m is None:
            raise HTTPException(status_code=400, detail=f"Unknown OCR model {spec_id!r}")
        return m.base_url, m.model_id, await resolve_api_key(db, m) or "none"
    preset = OCR_PRESETS.get(spec_id)
    if preset is None:
        raise HTTPException(status_code=400, detail=f"Unknown OCR model {spec_id!r}")
    svc = ConfigService(db)
    # The provider's OCR key, then its vision key.
    key = (
        await svc.get(provider_key_config_key("ocr", preset["provider"]))
        or await svc.get(vision_api_key_for(preset["provider"]))
    )
    if not key:
        raise HTTPException(
            status_code=400,
            detail=f"No {preset['provider']} API key. Enter the API key for this model.",
        )
    return preset["base_url"], preset["model_id"], key


async def _apply_ocr(db: AsyncSession, spec_id: str, api_key: Optional[str]) -> None:
    """Write the flat ocr_* keys ocr_service reads."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    preset = OCR_PRESETS.get(spec_id)
    if api_key and preset is not None:
        # A typed key becomes the provider's OCR key.
        await svc.set(provider_key_config_key("ocr", preset["provider"]), api_key)
    base_url, model_id, key = await resolve_ocr_endpoint(db, spec_id)
    await svc.set("ocr_base_url", base_url)
    await svc.set("ocr_model", model_id)
    await svc.set("ocr_api_key", key)
    await svc.set(OCR_MODEL_SPEC_KEY, spec_id)


# ---------------------------------------------------------------------------
# Custom model CRUD
# ---------------------------------------------------------------------------

@router.get("/settings/custom-models", response_model=list[CustomModelOut])
async def list_custom_models(
    kind: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    return [await _to_out(db, m) for m in await list_custom(db, kind)]


@router.post("/settings/custom-models", response_model=CustomModelOut)
async def save_custom_model(
    body: CustomModelIn,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    if body.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {KINDS}")
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {PROVIDERS}")
    if body.provider == "anthropic" and body.kind == "embedding":
        raise HTTPException(status_code=400, detail="Anthropic has no embedding models.")
    if body.provider == "custom":
        protocol = body.protocol
        base_url = (body.base_url or "").strip()
    else:
        base_url, protocol = provider_endpoint(body.kind, body.provider)
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=400, detail=f"protocol must be one of {PROTOCOLS}")
    if protocol == "anthropic" and body.kind != "llm":
        raise HTTPException(
            status_code=400,
            detail="Anthropic protocol is only supported for LLM; use an OpenAI-compatible URL.",
        )
    model_id = body.model_id.strip()
    if not model_id or len(model_id) > MAX_MODEL_ID_LEN:
        raise HTTPException(status_code=400, detail=f"Model name must be 1–{MAX_MODEL_ID_LEN} characters")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL must start with http:// or https://")
    dimension = None
    if body.kind == "embedding":
        if body.dimension not in EMBEDDING_DIMENSIONS:
            raise HTTPException(
                status_code=400, detail=f"dimension must be one of {EMBEDDING_DIMENSIONS}"
            )
        dimension = body.dimension

    spec_id = make_id(body.kind, model_id, dimension)
    model = CustomModel(
        id=spec_id, kind=body.kind, model_id=model_id,
        label=(body.label or "").strip() or model_id,
        base_url=base_url, protocol=protocol, dimension=dimension, provider=body.provider,
    )
    await save_custom(db, model, _new_key(body.api_key))
    # Keep the OCR keys in sync when the edited model is the OCR model in use.
    if body.kind == "ocr" and (await _active_ids(db))["ocr"] == spec_id:
        await _apply_ocr(db, spec_id, None)
    await log_audit(
        db, _user, "save_custom_model", "settings", "global",
        reason=f"Saved {body.kind} model {spec_id} ({base_url})",
    )
    await db.commit()
    return await _to_out(db, model)


@router.delete("/settings/custom-models")
async def remove_custom_model(
    kind: str = Query(...),
    id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    if (await _active_ids(db)).get(kind) == id:
        raise HTTPException(
            status_code=409, detail="This model is in use. Switch to another model first."
        )
    if kind == "embedding":
        from app.routers.admin_embeddings import _get_current_job

        job = await _get_current_job(db)
        if job is not None and job.model_spec_id == id:
            raise HTTPException(status_code=409, detail="A re-embed job is using this model.")
    if not await delete_custom(db, kind, id):
        raise HTTPException(status_code=404, detail="Model not found")
    await log_audit(
        db, _user, "delete_custom_model", "settings", "global",
        reason=f"Deleted {kind} model {id}",
    )
    await db.commit()
    return {"deleted": id}


# ---------------------------------------------------------------------------
# OCR model selection
# ---------------------------------------------------------------------------

@router.get("/settings/ocr/catalog", response_model=OcrCatalogOut)
async def get_ocr_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.services.config_service import ConfigService, vision_api_key_for

    svc = ConfigService(db)
    active = await svc.get(OCR_MODEL_SPEC_KEY)
    current_model = await svc.get("ocr_model")
    current_key = bool(await svc.get("ocr_api_key"))

    async def _provider_has_key(provider: str) -> bool:
        return bool(
            await svc.get(provider_key_config_key("ocr", provider))
            or await svc.get(vision_api_key_for(provider))
        )

    if active is None:
        # Configs from before model selection existed: match by model name.
        active = next(
            (sid for sid, p in OCR_PRESETS.items() if p["model_id"] == current_model), None
        )

    specs = []
    for spec_id, p in OCR_PRESETS.items():
        specs.append(OcrModelOut(
            id=spec_id, provider=p["provider"], label=p["label"], base_url=p["base_url"],
            model_id=p["model_id"], custom=False, group=p["provider"],
            api_key_configured=(current_key and active == spec_id)
            or await _provider_has_key(p["provider"]),
        ))
    for m in await list_custom(db, "ocr"):
        specs.append(OcrModelOut(
            id=m.id, provider="custom", label=m.label, base_url=m.base_url,
            model_id=m.model_id, custom=True, group=m.provider,
            api_key_configured=bool(await resolve_api_key(db, m)),
        ))
    return OcrCatalogOut(active_spec_id=active, specs=specs)


@router.post("/settings/ocr/select")
async def select_ocr_model(
    body: OcrSelectBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    await _apply_ocr(db, body.model_spec_id, _new_key(body.api_key))
    await log_audit(
        db, _user, "select_ocr_model", "settings", "global",
        reason=f"OCR model set to {body.model_spec_id}",
    )
    await db.commit()
    return {"active_spec_id": body.model_spec_id}


# ---------------------------------------------------------------------------
# Model discovery ("Tải danh sách model" in the add form)
# ---------------------------------------------------------------------------

class EndpointIn(BaseModel):
    kind: str
    provider: str = "custom"
    # Custom endpoints only; known providers use their own URL and stored key.
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class DiscoverOut(BaseModel):
    models: list[str]


async def resolve_probe_endpoint(db: AsyncSession, body: EndpointIn) -> tuple[str, str]:
    """(OpenAI-compatible base_url, api_key) for probing a model not saved yet."""
    from app.ai.custom_models import _OPENAI_COMPAT_URLS
    from app.services.config_service import ConfigService, vision_api_key_for

    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {PROVIDERS}")
    typed_key = _new_key(body.api_key)
    if body.provider == "custom":
        base_url = (body.base_url or "").strip()
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Base URL must start with http:// or https://")
        # Local servers (vLLM, Ollama) often need no auth; the SDK refuses an empty key.
        return base_url, typed_key or "none"
    svc = ConfigService(db)
    key = typed_key or await svc.get(provider_key_config_key(body.kind, body.provider))
    if not key and body.kind == "ocr":
        key = await svc.get(vision_api_key_for(body.provider))
    if not key:
        raise HTTPException(
            status_code=400, detail=f"Chưa có API key {body.provider}. Lưu key trước."
        )
    return _OPENAI_COMPAT_URLS[body.provider], key


@router.post("/settings/models/discover", response_model=DiscoverOut)
async def discover_models(
    body: EndpointIn,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    """List model ids served by an endpoint (GET /models)."""
    import openai

    base_url, api_key = await resolve_probe_endpoint(db, body)
    client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=15, max_retries=0)
    try:
        page = await client.models.list()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không lấy được danh sách model: {e}")
    # Gemini's OpenAI-compatible endpoint prefixes ids with "models/".
    ids = sorted({m.id.removeprefix("models/") for m in page.data if m.id})
    if body.kind == "embedding" and body.provider != "custom":
        ids = [i for i in ids if "embed" in i]
    return DiscoverOut(models=ids)
