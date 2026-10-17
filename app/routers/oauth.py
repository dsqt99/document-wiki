"""OAuth 2.0 authorization server (auth code + PKCE S256) for MCP clients.

``wellknown_router`` is mounted at the root, ``router`` under ``/oauth``.
A successful token exchange issues (rotates) the employee's ``ark_`` MCP token.
"""

import base64
import hashlib
import hmac
import html
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.oauth_models import OAuthAuthCode, OAuthClient
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter()
wellknown_router = APIRouter()

AUTH_CODE_TTL_MINUTES = 10
SUPPORTED_METHOD = "S256"


def _base(request: Request) -> str:
    from app.routers import sso

    return sso._public_base(request)


def _error(code: str, http_status: int = status.HTTP_400_BAD_REQUEST, description: Optional[str] = None):
    body = {"error": code}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=http_status)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@wellknown_router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata(request: Request):
    base = _base(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": [SUPPORTED_METHOD],
        "token_endpoint_auth_methods_supported": ["none"],
    }


def _protected_resource(request: Request) -> dict:
    base = _base(request)
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [],
        "resource_name": "Document Wiki MCP",
        "resource_documentation": f"{base}/docs",
    }


@wellknown_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata(request: Request):
    return _protected_resource(request)


@wellknown_router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata_mcp(request: Request):
    return _protected_resource(request)


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    client_name: Optional[str] = "Claude Desktop"
    redirect_uris: list[str] = Field(default_factory=list)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_client(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    uris = [u for u in (body.redirect_uris or []) if isinstance(u, str) and u.strip()]
    if not uris:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "redirect_uris required")
    name = body.client_name or "Claude Desktop"
    client = OAuthClient(client_id=OAuthClient.generate_client_id(), name=name, redirect_uris=uris)
    db.add(client)
    await db.commit()
    return {
        "client_id": client.client_id,
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "registration_client_uri": f"{_base(request)}/oauth/register/{client.client_id}",
    }


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def _get_client(db: AsyncSession, client_id: Optional[str]) -> Optional[OAuthClient]:
    if not client_id:
        return None
    result = await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
    return result.scalar_one_or_none()


def _login_page(params: dict, client_name: str, error: Optional[str] = None, email: str = "") -> str:
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v or "")}">'
        for k, v in params.items()
    )
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Document Wiki - Sign in</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #f5f6f8; margin: 0; }}
main {{ max-width: 360px; margin: 10vh auto; background: #fff; padding: 24px; border-radius: 8px;
       box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
label {{ display: block; margin-top: 12px; font-size: 14px; }}
input[type=email], input[type=password] {{ width: 100%; padding: 8px; box-sizing: border-box; }}
button {{ margin-top: 16px; width: 100%; padding: 10px; }}
.error {{ color: #b00020; }}
</style>
</head>
<body>
<main>
<h1>Document Wiki</h1>
<p>Sign in to allow <strong>{html.escape(client_name or "this client")}</strong> to access Document Wiki MCP.</p>
{error_html}
<form method="post" action="/oauth/authorize">
{hidden}
<label>Email <input type="email" name="email" value="{html.escape(email)}" required autofocus></label>
<label>Password <input type="password" name="password" required></label>
<button type="submit">Sign in</button>
</form>
</main>
</body>
</html>"""


@router.get("/authorize")
async def authorize_form(
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "",
    code_challenge: str = "",
    code_challenge_method: str = SUPPORTED_METHOD,
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    if response_type != "code":
        return _error("unsupported_response_type")
    if (code_challenge_method or SUPPORTED_METHOD) != SUPPORTED_METHOD:
        return _error("unsupported_code_challenge_method")
    client = await _get_client(db, client_id)
    if client is None:
        return _error("invalid_client")
    if redirect_uri not in (client.redirect_uris or []):
        return _error("invalid_redirect_uri")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method or SUPPORTED_METHOD,
        "state": state,
    }
    return HTMLResponse(_login_page(params, client.name or client_id))


def _with_query(url: str, extra: dict) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend((k, v) for k, v in extra.items() if v is not None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@router.post("/authorize")
async def authorize_submit(
    client_id: str = Form(""),
    redirect_uri: str = Form(""),
    code_challenge: str = Form(""),
    code_challenge_method: str = Form(SUPPORTED_METHOD),
    state: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, client_id)
    if client is None:
        return _error("invalid_client")
    if redirect_uri not in (client.redirect_uris or []):
        return _error("invalid_redirect_uri")
    method = code_challenge_method or SUPPORTED_METHOD
    if method != SUPPORTED_METHOD:
        return _error("unsupported_code_challenge_method")

    employee = await auth_service.authenticate_employee(db, email, password)
    if employee is None:
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": method,
            "state": state,
        }
        return HTMLResponse(
            _login_page(params, client.name or client_id, error="Invalid email or password", email=email),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    code = secrets.token_urlsafe(32)
    db.add(
        OAuthAuthCode(
            code=code,
            client_id=client_id,
            employee_id=employee.id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=method,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=AUTH_CODE_TTL_MINUTES),
            used=False,
        )
    )
    await db.commit()
    return RedirectResponse(_with_query(redirect_uri, {"code": code, "state": state}), status_code=status.HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256((verifier or "").encode("ascii", errors="ignore")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@router.post("/token")
async def token(
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    code_verifier: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if grant_type != "authorization_code":
        return _error("unsupported_grant_type")
    result = await db.execute(select(OAuthAuthCode).where(OAuthAuthCode.code == code))
    auth_code = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if auth_code is None or auth_code.used or auth_code.client_id != client_id:
        return _error("invalid_grant")
    expires = auth_code.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or expires <= now:
        return _error("invalid_grant")
    if auth_code.redirect_uri != redirect_uri:
        return _error("invalid_grant")
    if not code_verifier or not hmac.compare_digest(pkce_s256(code_verifier), auth_code.code_challenge or ""):
        return _error("invalid_grant")

    auth_code.used = True
    from app.services import mcp_auth_service

    access_token = await mcp_auth_service.MCPAuthService(db).generate_token(auth_code.employee_id)
    await db.commit()
    return {"access_token": access_token, "token_type": "bearer"}
