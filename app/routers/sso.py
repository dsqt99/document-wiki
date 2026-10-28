"""
SSO router — đăng nhập Google qua OpenID Connect.

  GET /api/auth/sso/login     — chuyển sang Google (Authorization Code + PKCE)
  GET /api/auth/sso/callback  — đổi code, xác thực id_token, cấp JWT cục bộ

  GET /api/auth/sso/config    — cấu hình công khai cho trang /login
  GET /api/auth/sso/logout    — đăng xuất phiên OIDC, rồi quay về /login

Sau khi xác thực, JWT wiki bị giới hạn bởi hạn phiên nguồn; mỗi API xác thực lại
trạng thái phiên nguồn. Tài khoản được tạo/liên kết theo cột external_id (sub OIDC), rồi theo email.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import NamedTuple, Optional
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Department, Employee, EmployeeDepartment
from app.services import audit_chain
from app.services.sso_roles import SOURCE_SSO, derived_global_role, load_role_map, sync_employee_roles
from app.services.auth_service import JWT_EXPIRE_HOURS, create_access_token

router = APIRouter()

PROVIDER = "oidc"
TX_COOKIE = "arkon_sso_tx"
IDT_COOKIE = "arkon_sso_idt"
COOKIE_PATH = "/api/auth/sso"
TX_TTL_SECONDS = 600
TX_AUDIENCE = "arkon-sso-tx"
DISCOVERY_TTL_SECONDS = 3600
MAX_COOKIE_BYTES = 3800
SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]

_discovery_cache: dict = {}
_jwk_clients: dict[str, jwt.PyJWKClient] = {}


class _Endpoints(NamedTuple):
    authorization: str
    token: str
    jwks: str
    end_session: Optional[str]
    issuers: frozenset[str]
    introspection: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enabled() -> bool:
    return bool(settings.sso_enabled and settings.sso_issuer and settings.sso_client_id)


def _public_issuer() -> str:
    return settings.sso_issuer.rstrip("/")


def _internal_issuer() -> str:
    return (settings.sso_internal_issuer or settings.sso_issuer).rstrip("/")


def _public_base(request: Request) -> str:
    """Gốc URL công khai của wiki (PORTAL_BASE_URL, nếu trống thì suy từ header proxy)."""
    if settings.portal_base_url:
        return settings.portal_base_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto.split(',')[0].strip()}://{host.split(',')[0].strip()}"


def _callback_url(request: Request) -> str:
    return f"{_public_base(request)}/api/auth/sso/callback"


def _secure(request: Request) -> bool:
    return _public_base(request).startswith("https://")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _safe_next(value: Optional[str]) -> str:
    """Chỉ nhận đường dẫn nội bộ, tránh open redirect và vòng lặp về /login."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if value == "/login" or value.startswith(("/login/", "/login?")):
        return "/"
    return value[:500]


def _swap_prefix(url: str, src: str, dst: str) -> str:
    if url and src and dst and src != dst and (url == src or url.startswith(src + "/")):
        return dst + url[len(src):]
    return url


async def _endpoints() -> _Endpoints:
    """Đọc discovery qua mạng nội bộ; endpoint cho trình duyệt đổi về issuer công khai,
    endpoint gọi từ server đổi về issuer nội bộ."""
    now = time.monotonic()
    doc = _discovery_cache.get("doc")
    if doc is None or now - _discovery_cache.get("at", 0) > DISCOVERY_TTL_SECONDS:
        url = f"{_internal_issuer()}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            doc = resp.json()
        _discovery_cache.update(at=now, doc=doc)

    public, internal = _public_issuer(), _internal_issuer()
    discovered = str(doc.get("issuer", "")).rstrip("/")

    def to_public(url: Optional[str]) -> Optional[str]:
        for src in (discovered, internal):
            url = _swap_prefix(url, src, public) if url else url
        return url

    def to_internal(url: Optional[str]) -> Optional[str]:
        for src in (discovered, public):
            url = _swap_prefix(url, src, internal) if url else url
        return url

    return _Endpoints(
        authorization=to_public(doc["authorization_endpoint"]),
        token=to_internal(doc["token_endpoint"]),
        jwks=to_internal(doc["jwks_uri"]),
        end_session=to_public(doc.get("end_session_endpoint")),
        issuers=frozenset(i for i in (public, internal, discovered) if i),
        introspection=to_internal(doc.get("introspection_endpoint")),
    )


def _jwk_client(jwks_uri: str) -> jwt.PyJWKClient:
    client = _jwk_clients.get(jwks_uri)
    if client is None:
        client = jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=DISCOVERY_TTL_SECONDS)
        _jwk_clients[jwks_uri] = client
    return client


async def _verify_jwt(
    ep: _Endpoints, token: str, *, audience: Optional[str] = None, nonce: Optional[str] = None,
) -> dict:
    signing_key = await asyncio.to_thread(_jwk_client(ep.jwks).get_signing_key_from_jwt, token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=SIGNING_ALGORITHMS,
        audience=audience,
        leeway=30,
        options={
            "verify_aud": audience is not None,
            "verify_iss": False,  # kiểm tra bên dưới: chấp nhận issuer công khai hoặc nội bộ
            "require": ["exp", "iat", "sub"],
        },
    )
    if str(claims.get("iss", "")).rstrip("/") not in ep.issuers:
        raise jwt.InvalidIssuerError("unexpected issuer")
    aud = claims.get("aud")
    if audience and isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != audience:
        raise jwt.InvalidAudienceError("azp mismatch")
    if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce mismatch")
    return claims


async def _exchange_code(ep: _Endpoints, code: str, verifier: str, redirect_uri: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "client_id": settings.sso_client_id,
    }
    if settings.sso_client_secret:
        data["client_secret"] = settings.sso_client_secret
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(ep.token, data=data)
    if resp.status_code != 200:
        # Không ghi thân phản hồi: có thể chứa thông tin nhạy cảm.
        raise RuntimeError(f"token endpoint HTTP {resp.status_code}")
    body = resp.json()
    if not body.get("id_token"):
        raise RuntimeError("token response has no id_token")
    return body


def _realm_roles(claims: dict) -> list[str]:
    realm_access = claims.get("realm_access")
    roles = realm_access.get("roles") if isinstance(realm_access, dict) else claims.get("roles")
    return [str(r) for r in roles] if isinstance(roles, list) else []


def _groups(claims: dict) -> list[str]:
    raw = claims.get("groups")
    if not isinstance(raw, list):
        return []
    # full.path=false trả "PA08"; nếu bật full.path thì lấy đoạn cuối "/CAHY/PA08".
    return [str(g).strip("/").rsplit("/", 1)[-1] for g in raw if str(g).strip("/")]


def _group_department_map() -> dict[str, str]:
    raw = settings.sso_group_department_map.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("SSO_GROUP_DEPARTMENT_MAP is not valid JSON — ignored")
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _login_redirect(request: Request, error: str, next: Optional[str] = None) -> RedirectResponse:
    params = {"error": error}
    if next and _safe_next(next) != "/":
        params["next"] = _safe_next(next)
    resp = RedirectResponse(f"{_public_base(request)}/login?{urlencode(params)}", status_code=302)
    resp.delete_cookie(TX_COOKIE, path=COOKIE_PATH)
    return resp


def _read_tx(request: Request) -> Optional[dict]:
    raw = request.cookies.get(TX_COOKIE)
    if not raw:
        return None
    try:
        return jwt.decode(raw, settings.secret_key, algorithms=["HS256"], audience=TX_AUDIENCE)
    except jwt.InvalidTokenError:
        return None


async def _provision(
    db: AsyncSession,
    claims: dict,
    roles: Optional[list[str]],
    groups: list[str],
    *,
    is_admin: Optional[bool] = None,
    provider: str = PROVIDER,
    unit_ids: Optional[list[str]] = None,
):
    """Tìm hoặc tạo Employee cho tài khoản SSO. Trả Employee hoặc mã lỗi (str).

    is_admin=None → suy từ role claim của OIDC (SSO_ADMIN_ROLES).
    roles=None → không biết vai trò: không đổi global_role của tài khoản đã có.
    unit_ids = id nhóm từ OIDC: phòng ban đồng bộ được đặt đúng theo
    danh sách này (thêm và gỡ). Không có unit_ids thì chỉ thêm phòng ban theo groups.
    """
    sub = str(claims["sub"])
    email = str(claims.get("email") or "").strip().lower()
    username = str(claims.get("preferred_username") or sub)
    full_name = str(
        claims.get("name")
        or " ".join(p for p in (claims.get("given_name"), claims.get("family_name")) if p)
        or username
    )
    if is_admin is None:
        is_admin = bool(set(roles or []) & settings.sso_admin_role_set)
    role_map = await load_role_map(db)

    employee = (
        await db.execute(select(Employee).where(Employee.external_id == sub))
    ).scalar_one_or_none()

    if employee is None and email:
        candidate = (
            await db.execute(select(Employee).where(func.lower(Employee.email) == email))
        ).scalars().first()
        if candidate is not None:
            if candidate.external_id and candidate.external_id != sub:
                return "sso_email_conflict"
            if not (claims.get("email_verified") or settings.sso_trust_email):
                return "sso_email_unverified"
            candidate.external_id = sub
            candidate.auth_provider = provider
            employee = candidate
            logger.info(f"SSO: linked existing employee {employee.id} to OIDC subject")

    created = False
    if employee is None:
        employee = Employee(
            name=full_name[:200],
            email=email or f"{username}@sso.invalid",
            password_hash=None,
            role="admin" if is_admin else "employee",
            global_role=(
                "admin" if is_admin
                else (derived_global_role(roles or [], role_map) or settings.sso_default_global_role)
            ),
            global_role_source=SOURCE_SSO,
            external_id=sub,
            auth_provider=provider,
            is_active=True,
        )
        try:
            async with db.begin_nested():
                db.add(employee)
                await db.flush()
        except IntegrityError:
            # Lần đăng nhập đầu, giao diện gọi song song nhiều API: yêu cầu khác vừa tạo cùng sub.
            employee = (
                await db.execute(select(Employee).where(Employee.external_id == sub))
            ).scalar_one_or_none()
            if employee is None:
                raise
            logger.info(f"SSO: concurrent provision for employee {employee.id}, reusing existing row")
        else:
            created = True
            logger.info(f"SSO: provisioned employee {employee.id} (admin={is_admin})")

    if not employee.is_active:
        return "sso_inactive"

    if settings.sso_sync_roles and not created:
        before, _ = sync_employee_roles(
            employee, roles, is_admin, role_map, settings.sso_default_global_role, settings.default_admin_email,
        )
        after = (employee.global_role, employee.global_role_source)
        if after != before:
            await audit_chain.record(
                principal_id=employee.id,
                action="SSO_GLOBAL_ROLE_SYNC",
                resource_type="employee",
                resource_id=str(employee.id),
                reason="đồng bộ vai trò Keycloak lúc SSO",
                metadata={
                    "before": {"global_role": before[0], "source": before[1]},
                    "after": {"global_role": after[0], "source": after[1]},
                    "realm_roles": sorted(set(roles or [])),
                },
            )

    if settings.sso_sync_departments and (groups or unit_ids is not None):
        current = set(
            (
                await db.execute(
                    select(EmployeeDepartment.department_id).where(
                        EmployeeDepartment.employee_id == employee.id
                    )
                )
            ).scalars().all()
        )
        wanted: set = set()
        if groups:
            mapping = _group_department_map()
            names = {mapping.get(g, g) for g in groups}
            conds = [Department.name.in_(names)]
            if unit_ids is None:
                # Keycloak trả tên nhóm hoặc đường dẫn /CHA/CON: khớp cả mã phòng ban đồng bộ.
                codes = {g.rstrip("/").rsplit("/", 1)[-1].strip().upper() for g in groups} - {""}
                conds.append(Department.code.in_(codes))
            stmt = select(Department.id).where(Department.is_active.is_(True), or_(*conds))
            if unit_ids is not None:
                stmt = stmt.where(Department.external_id.is_(None))
            wanted |= set((await db.execute(stmt)).scalars().all())
        if unit_ids is not None:
            managed = (
                await db.execute(
                    select(Department.id, Department.external_id, Department.is_active).where(
                        Department.external_id.is_not(None)
                    )
                )
            ).all()
            target_ext = set(unit_ids)
            target = {d_id for d_id, ext, active in managed if active and ext in target_ext}
            stale = (current & {d_id for d_id, _, _ in managed}) - target
            if stale:
                await db.execute(
                    delete(EmployeeDepartment).where(
                        EmployeeDepartment.employee_id == employee.id,
                        EmployeeDepartment.department_id.in_(stale),
                    )
                )
            wanted |= target
        for dept_id in wanted - current:
            db.add(EmployeeDepartment(employee_id=employee.id, department_id=dept_id))

    await db.flush()
    return employee


async def employee_from_access_token(db: AsyncSession, token: str):
    """Access token OIDC do MCP client chuyển tiếp (auth_type system_oauth).

    Chỉ nhận access token (typ=Bearer, không nhận id_token) do client trong
    SSO_MCP_CLIENTS cấp. Trả Employee (tạo/đồng bộ như khi đăng nhập SSO) hoặc mã lỗi (str).
    """
    if not _enabled() or not settings.sso_mcp_client_set:
        return "sso_disabled"
    try:
        ep = await _endpoints()
        claims = await _verify_jwt(ep, token)
    except jwt.ExpiredSignatureError:
        return "sso_token_expired"
    except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
        logger.info(f"SSO MCP: access token rejected ({type(exc).__name__})")
        return "sso_token_invalid"
    if str(claims.get("typ", "")).lower() != "bearer":
        return "sso_token_invalid"
    if claims.get("azp") not in settings.sso_mcp_client_set:
        return "sso_client_not_allowed"
    employee = await _provision(db, claims, _realm_roles(claims), _groups(claims))
    if not isinstance(employee, str):
        from app.services.sso_session_service import oidc_parent, session_binding
        employee._wiki_session_claims = {**session_binding("oidc", oidc_parent(token, claims)), "exp": claims["exp"]}
    return employee


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/auth/sso/config")
async def sso_config():
    """Cấu hình công khai để trang /login chọn đường đăng nhập."""
    enabled = _enabled()
    return {
        "enabled": enabled,
        "provider_name": settings.sso_provider_name,
        "auto_redirect": enabled and settings.sso_auto_redirect,
        "allow_password_login": (not enabled) or settings.sso_allow_password_login,
    }


def _session_redirect(request: Request, employee: Employee, nxt: Optional[str], *, auth_source: str, parent: dict) -> RedirectResponse:
    """Cấp JWT wiki và trả về /login/sso (token nằm trong fragment, không tới server nào)."""
    token = create_access_token(
        employee_id=str(employee.id), role=employee.role, name=employee.name,
        auth_source=auth_source, parent=parent,
    )
    fragment = urlencode({"token": token, "next": _safe_next(nxt)})
    resp = RedirectResponse(f"{_public_base(request)}/login/sso#{fragment}", status_code=302)
    resp.delete_cookie(TX_COOKIE, path=COOKIE_PATH)
    return resp


@router.get("/auth/sso/login")
async def sso_login(request: Request, next: Optional[str] = None, prompt: Optional[str] = None):
    if not _enabled():
        return _login_redirect(request, "sso_disabled")
    try:
        ep = await _endpoints()
    except Exception as e:
        logger.warning(f"SSO discovery failed: {e}")
        return _login_redirect(request, "sso_unavailable")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())

    tx = jwt.encode(
        {
            "aud": TX_AUDIENCE,
            "st": state,
            "nn": nonce,
            "cv": verifier,
            "nx": _safe_next(next),
            "exp": int(time.time()) + TX_TTL_SECONDS,
        },
        settings.secret_key,
        algorithm="HS256",
    )
    params = {
        "response_type": "code",
        "client_id": settings.sso_client_id,
        "redirect_uri": _callback_url(request),
        "scope": settings.sso_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if prompt == "none":
        # Đăng nhập im lặng: nhà cung cấp OIDC không hiện form nếu đã có phiên.
        params["prompt"] = "none"
    resp = RedirectResponse(f"{ep.authorization}?{urlencode(params)}", status_code=302)
    resp.set_cookie(
        TX_COOKIE, tx, max_age=TX_TTL_SECONDS, httponly=True,
        secure=_secure(request), samesite="lax", path=COOKIE_PATH,
    )
    return resp


@router.get("/auth/sso/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if not _enabled():
        return _login_redirect(request, "sso_disabled")
    tx = _read_tx(request)
    nxt = tx.get("nx") if tx else None
    if error:
        logger.info(f"SSO: IdP returned error '{error[:60]}'")
        if error in ("login_required", "interaction_required", "consent_required"):
            # Kết quả của prompt=none: chưa có phiên OIDC, trang /login chuyển sang đăng nhập.
            return _login_redirect(request, "sso_login_required", nxt)
        return _login_redirect(request, "sso_denied", nxt)

    if not tx or not code or not state or not secrets.compare_digest(state, str(tx.get("st", ""))):
        return _login_redirect(request, "sso_state")

    try:
        ep = await _endpoints()
        tokens = await _exchange_code(ep, code, tx["cv"], _callback_url(request))
        id_token = tokens["id_token"]
        claims = await _verify_id_token(ep, id_token, tx["nn"])
        access_token = tokens.get("access_token")
        access_claims = await _verify_jwt(ep, access_token) if access_token else None
        if not access_claims or access_claims.get("sub") != claims.get("sub"):
            raise jwt.InvalidTokenError("OIDC access-token subject mismatch")
        from app.services.sso_session_service import oidc_parent
        parent = oidc_parent(access_token, access_claims)
        roles = _realm_roles(claims)
        if not roles:
            roles = _realm_roles(access_claims)
    except Exception as e:
        logger.warning(f"SSO callback failed: {e}")
        return _login_redirect(request, "sso_token")

    result = await _provision(db, claims, roles, _groups(claims))
    if isinstance(result, str):
        await db.rollback()
        return _login_redirect(request, result)
    employee = result
    # Commit trước khi chuyển hướng: trang /login/sso gọi /api/auth/me ngay sau đó.
    await db.commit()

    resp = _session_redirect(request, employee, tx.get("nx"), auth_source="oidc", parent=parent)
    if len(id_token) <= MAX_COOKIE_BYTES:
        # Giữ id_token để đăng xuất Keycloak không phải hỏi xác nhận.
        resp.set_cookie(
            IDT_COOKIE, id_token, max_age=JWT_EXPIRE_HOURS * 3600, httponly=True,
            secure=_secure(request), samesite="lax", path=COOKIE_PATH,
        )
    return resp


async def _verify_id_token(ep: _Endpoints, id_token: str, nonce: str) -> dict:
    return await _verify_jwt(ep, id_token, audience=settings.sso_client_id, nonce=nonce)


@router.get("/auth/sso/logout")
async def sso_logout(request: Request):
    """Kết thúc phiên đăng nhập Google, rồi quay về /login."""
    target = f"{_public_base(request)}/login?logged_out=1"
    if _enabled():
        try:
            ep = await _endpoints()
            if ep.end_session:
                params = {"client_id": settings.sso_client_id, "post_logout_redirect_uri": target}
                id_token = request.cookies.get(IDT_COOKIE)
                if id_token:
                    params["id_token_hint"] = id_token
                target = f"{ep.end_session}?{urlencode(params)}"
        except Exception as e:
            logger.warning(f"SSO logout discovery failed: {e}")
    resp = RedirectResponse(target, status_code=302)
    resp.delete_cookie(IDT_COOKIE, path=COOKIE_PATH)
    resp.delete_cookie(TX_COOKIE, path=COOKIE_PATH)
    return resp
