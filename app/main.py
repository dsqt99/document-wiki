"""FastAPI application: REST API under /api, OAuth for MCP clients, and the MCP endpoint at /mcp."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.mcp.server import create_mcp_server
from app.routers import (
    admin_custom_models,
    admin_embeddings,
    admin_failures,
    admin_models,
    admin_settings,
    admin_stats,
    audit,
    auth,
    knowledge_types,
    legal_docs,
    notes,
    notifications,
    oauth,
    org_sync,
    prompts,
    rbac,
    skill_contributions,
    skills,
    sources,
    sso,
    wiki,
    wiki_branches,
    wiki_drafts,
    wiki_images,
)
from app.services.trace_context import CorrelationIdMiddleware
from app.services.upload_limit import UploadSizeLimitMiddleware

logger = logging.getLogger(__name__)

VERSION = "0.1.0"
_DEFAULT_SECRET_KEY = "change-me-to-a-random-secret-string"
_UPLOAD_PATH = "/api/sources/upload"

mcp_server = create_mcp_server()
mcp_http_app = mcp_server.http_app(path="/", stateless_http=True)


async def seed_default_admin() -> None:
    if not settings.default_admin_password:
        logger.warning("DEFAULT_ADMIN_PASSWORD is empty; skipping default admin seed")
        return
    try:
        from sqlalchemy import select

        from app import database
        from app.database.models import Department, Employee, EmployeeDepartment
        from app.services.auth_service import hash_password

        async with database.async_session_factory() as session:
            existing = (
                await session.execute(select(Employee).where(Employee.role == "admin").limit(1))
            ).scalar_one_or_none()
            if existing is not None:
                return
            dept = Department(name="Administration", description="System administrators")
            session.add(dept)
            admin = Employee(
                name="Admin",
                email=settings.default_admin_email,
                password_hash=hash_password(settings.default_admin_password),
                role="admin",
            )
            session.add(admin)
            await session.flush()
            session.add(EmployeeDepartment(employee_id=admin.id, department_id=dept.id))
            await session.commit()
            logger.info("Seeded default admin %s", settings.default_admin_email)
    except Exception as e:
        logger.warning("Default admin seed failed: %s", e)


async def _step(name: str, coro_factory) -> None:
    try:
        await coro_factory()
    except Exception as e:
        logger.warning("Startup step %s failed: %s", name, e)


async def _load_role_overrides() -> None:
    from app import database
    from app.services import config_service, permissions

    async with database.async_session_factory() as session:
        value = await config_service.ConfigService(session).get("role_permissions_custom")
    if value:
        permissions.load_role_permissions_override(value)


async def _seed_knowledge_types() -> None:
    from app.scripts.seed_knowledge_types import seed_default_knowledge_types

    await seed_default_knowledge_types()


async def _seed_skills() -> None:
    from app.scripts.seed_skills import seed_builtin_skills

    await seed_builtin_skills()


async def _ensure_bucket() -> None:
    from app.services.storage_service import storage_service

    await storage_service.ensure_bucket()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp_http_app.lifespan(_app):
        await _step("ensure_bucket", _ensure_bucket)
        await _step("seed_default_admin", seed_default_admin)
        await _step("seed_knowledge_types", _seed_knowledge_types)
        await _step("seed_skills", _seed_skills)
        await _step("role_permissions_override", _load_role_overrides)
        if settings.secret_key == _DEFAULT_SECRET_KEY:
            logger.warning("SECRET_KEY is still the default value; set a random secret in production")
        try:
            yield
        finally:
            try:
                from app.ai.tracing import shutdown_langfuse

                shutdown_langfuse()
            except Exception:
                pass


app = FastAPI(title="Document Wiki API", version=VERSION, lifespan=lifespan)

# 1. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. MCP bearer gate (token validation itself happens in the MCP tools)
@app.middleware("http")
async def mcp_bearer_gate(request: Request, call_next):
    path = request.url.path
    if path == "/mcp" or path.startswith("/mcp/"):
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            base = sso._public_base(request)
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "error_description": "A Bearer access token is required for the MCP endpoint.",
                },
                headers={
                    "WWW-Authenticate": (
                        f'Bearer realm="Document Wiki MCP", '
                        f'resource_metadata="{base}/.well-known/oauth-protected-resource"'
                    )
                },
            )
    return await call_next(request)


# 3. Notification dispatch after each request
@app.middleware("http")
async def notification_dispatch(request: Request, call_next):
    from app.services import notification_service

    notification_service.init_request_dispatch_scope()
    response = await call_next(request)
    try:
        await notification_service.dispatch_pending()
    except Exception as e:
        logger.warning("Notification dispatch failed: %s", e)
    return response


# 4. Upload size limit
def _upload_limit_for(method: str, path: str):
    if method == "POST" and path == _UPLOAD_PATH:
        return settings.max_upload_size_bytes
    return None


app.add_middleware(UploadSizeLimitMiddleware, limit_for=_upload_limit_for)
# 5. Correlation id (outermost)
app.add_middleware(CorrelationIdMiddleware)

app.mount("/mcp", mcp_http_app)

app.include_router(oauth.wellknown_router)
app.include_router(oauth.router, prefix="/oauth")
for _module in (auth, sso, sources, notes, wiki_branches, wiki_drafts, legal_docs, wiki, wiki_images):
    app.include_router(_module.router, prefix="/api")
for _module in (admin_settings, admin_embeddings, admin_models, admin_custom_models, admin_stats, admin_failures):
    app.include_router(_module.router, prefix="/api")
for _module in (rbac, org_sync, knowledge_types, audit, skills, skill_contributions, prompts, notifications):
    app.include_router(_module.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": "Document Wiki",
        "description": "Enterprise Knowledge Wiki",
        "version": VERSION,
        "mcp_endpoint": "/mcp",
        "docs": "/docs",
    }


async def _check_database() -> str:
    try:
        from sqlalchemy import text

        from app import database

        async with database.async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        logger.warning("Health check: database error: %s", e)
        return "error"


@app.get("/health")
async def health():
    services = {"database": await _check_database()}
    try:
        pool = await sources.get_arq_pool()
        await pool.ping()
        services["redis"] = "healthy"
    except Exception as e:
        logger.warning("Health check: redis error: %s", e)
        services["redis"] = "error"
    try:
        await _ensure_bucket()
        services["minio"] = "healthy"
    except Exception as e:
        logger.warning("Health check: minio error: %s", e)
        services["minio"] = "error"
    status = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"
    return {"status": status, "services": services}


@app.get("/api/health")
async def api_health():
    database_status = await _check_database()
    worker_status = "error"
    try:
        import redis.asyncio as aioredis

        client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            socket_connect_timeout=2,
        )
        try:
            await client.ping()
            worker_status = "healthy"
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("Health check: worker redis error: %s", e)
    return {"api": "healthy", "database": database_status, "worker": worker_status}
