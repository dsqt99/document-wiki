"""Admin-defined models (Settings → "Thêm model").

Presets live in the code catalogs (llm_catalog, vision_catalog,
embedding_catalog). Any other model an admin adds with a base URL and model
name is stored here as JSON in app_config; its API key is stored encrypted in
its own app_config row.

Ids are "custom/<model_id>" — embedding: "custom/<dim>/<model_id>" — so the
synchronous catalog lookups can rebuild a spec from the id alone (embedding
tables are chosen by dimension). base_url, protocol and API key are only needed
when a provider client is built, which happens in the async registry.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

CUSTOM_PREFIX = "custom/"
KINDS = ("llm", "vision", "embedding", "ocr")
# Wire protocol of the endpoint: "openai" = any OpenAI-compatible API
# (vLLM, Ollama, LiteLLM, Azure, ...); "anthropic" = Anthropic Messages API.
PROTOCOLS = ("openai", "anthropic")
EMBEDDING_DIMENSIONS = (768, 1024, 1536, 3072)  # tables that exist (migration 015)
MAX_MODEL_ID_LEN = 100  # spec ids land in String(128) columns

_STORE_KEY = "custom_models"
_API_KEY_PREFIX = "custom_model_api_key__"


@dataclass
class CustomModel:
    id: str
    kind: str
    model_id: str
    label: str
    base_url: str
    protocol: str = "openai"
    dimension: Optional[int] = None


def is_custom(spec_id: Optional[str]) -> bool:
    return bool(spec_id) and spec_id.startswith(CUSTOM_PREFIX)


def make_id(kind: str, model_id: str, dimension: Optional[int] = None) -> str:
    if kind == "embedding":
        return f"{CUSTOM_PREFIX}{dimension}/{model_id}"
    return f"{CUSTOM_PREFIX}{model_id}"


def parse_id(spec_id: str) -> tuple[Optional[int], str]:
    """Return (dimension, model_id) for a custom id; dimension only for
    embedding ids ("custom/<dim>/<model_id>")."""
    rest = spec_id[len(CUSTOM_PREFIX):]
    head, _, tail = rest.partition("/")
    if head.isdigit() and tail:
        return int(head), tail
    return None, rest


def api_key_config_key(kind: str, spec_id: str) -> str:
    """app_config key holding the encrypted API key of one custom model."""
    digest = hashlib.sha256(f"{kind}:{spec_id}".encode()).hexdigest()[:24]
    return f"{_API_KEY_PREFIX}{digest}"


def is_custom_api_key(config_key: str) -> bool:
    return config_key.startswith(_API_KEY_PREFIX)


async def _load(db: AsyncSession) -> list[CustomModel]:
    from app.services.config_service import ConfigService

    raw = await ConfigService(db).get(_STORE_KEY)
    if not raw:
        return []
    try:
        return [CustomModel(**item) for item in json.loads(raw)]
    except (ValueError, TypeError):
        return []


async def _store(db: AsyncSession, models: list[CustomModel]) -> None:
    from app.services.config_service import ConfigService

    await ConfigService(db).set(
        _STORE_KEY, json.dumps([asdict(m) for m in models], ensure_ascii=False)
    )


async def list_custom(db: AsyncSession, kind: Optional[str] = None) -> list[CustomModel]:
    models = await _load(db)
    return [m for m in models if kind is None or m.kind == kind]


async def get_custom(db: AsyncSession, kind: str, spec_id: str) -> Optional[CustomModel]:
    for m in await _load(db):
        if m.kind == kind and m.id == spec_id:
            return m
    return None


async def save_custom(db: AsyncSession, model: CustomModel, api_key: Optional[str]) -> None:
    """Insert or replace (by kind + id). api_key=None keeps the stored key."""
    from app.services.config_service import ConfigService

    models = [m for m in await _load(db) if not (m.kind == model.kind and m.id == model.id)]
    models.append(model)
    await _store(db, models)
    if api_key is not None:
        await ConfigService(db).set(api_key_config_key(model.kind, model.id), api_key)


async def delete_custom(db: AsyncSession, kind: str, spec_id: str) -> bool:
    from app.services.config_service import ConfigService

    models = await _load(db)
    kept = [m for m in models if not (m.kind == kind and m.id == spec_id)]
    if len(kept) == len(models):
        return False
    await _store(db, kept)
    await ConfigService(db).set(api_key_config_key(kind, spec_id), "")
    return True


async def get_api_key(db: AsyncSession, kind: str, spec_id: str) -> str:
    from app.services.config_service import ConfigService

    return await ConfigService(db).get(api_key_config_key(kind, spec_id)) or ""
