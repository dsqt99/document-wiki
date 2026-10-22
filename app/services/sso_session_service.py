"""Bind wiki authorization to the lifetime and current state of its SSO parent."""

import base64
import hashlib
import time

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings

SESSION_VERSION = 2
_AUTH_SOURCES = {"local", "chatbot", "oidc"}


def _deadline(value) -> int:
    if type(value) is not int:
        raise ValueError("Missing session deadline")
    deadline = int(value)
    if deadline <= time.time():
        raise ValueError("Session expired")
    return deadline


def session_binding(auth_source: str, parent: dict | None) -> dict:
    if auth_source not in _AUTH_SOURCES:
        raise ValueError("Unknown authentication source")
    binding = {"session_version": SESSION_VERSION, "auth_source": auth_source}
    if auth_source == "local":
        if parent is not None:
            raise ValueError("Unexpected local session parent")
        return binding
    if not isinstance(parent, dict):
        raise ValueError("Missing SSO session binding")
    proof, subject = parent.get("proof"), parent.get("sub")
    if not isinstance(proof, str) or not 0 < len(proof) <= 16384 or not isinstance(subject, str) or not 0 < len(subject) <= 256:
        raise ValueError("Invalid SSO session binding")
    binding["parent"] = {"proof": proof, "sub": subject, "exp": _deadline(parent.get("exp"))}
    return binding


def _oidc_cipher() -> Fernet:
    key = hashlib.sha256(f"cahy-wiki-oidc-parent-session:v1:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def oidc_parent(access_token: str, verified_claims: dict) -> dict:
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Missing OIDC access token")
    proof = _oidc_cipher().encrypt(access_token.encode()).decode()
    return session_binding("oidc", {"proof": proof, "sub": verified_claims.get("sub"),
                                    "exp": verified_claims.get("exp")})["parent"]


def _invalid() -> HTTPException:
    return HTTPException(401, "Session expired or revoked")


def _unavailable() -> HTTPException:
    return HTTPException(503, "Session verification temporarily unavailable")


async def _json_response(response: httpx.Response) -> dict:
    if response.status_code in (400, 401, 403):
        raise _invalid()
    if response.status_code != 200:
        raise _unavailable()
    try:
        body = response.json()
    except (ValueError, TypeError):
        raise _unavailable() from None
    if not isinstance(body, dict) or not isinstance(body.get("active"), bool):
        raise _unavailable()
    if not body["active"]:
        raise _invalid()
    return body


async def _verify_chatbot(parent: dict) -> None:
    base = (settings.chatbot_internal_url or settings.chatbot_url).strip().rstrip("/")
    if not base:
        raise _unavailable()
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.post(f"{base}/api/v1/arkon/sso/session", json={"proof": parent["proof"]})
    body = await _json_response(response)
    if body.get("user_id") != parent["sub"] or body.get("expires_at") != parent["exp"]:
        raise _invalid()


async def _verify_oidc(parent: dict) -> None:
    from app.routers import sso

    if not settings.sso_client_secret:
        raise _unavailable()
    try:
        token = _oidc_cipher().decrypt(parent["proof"].encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise _invalid() from None
    try:
        endpoints = await sso._endpoints()
    except (KeyError, TypeError, ValueError):
        raise _unavailable() from None
    if not endpoints.introspection:
        raise _unavailable()
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.post(endpoints.introspection, data={"token": token},
                                     auth=(settings.sso_client_id, settings.sso_client_secret))
    # Invalid client configuration is a verifier outage, not an inactive user token.
    if response.status_code != 200:
        raise _unavailable()
    body = await _json_response(response)
    if body.get("sub") != parent["sub"] or body.get("exp") != parent["exp"]:
        raise _invalid()


async def validate_session_claims(claims: dict) -> None:
    """No successful-state cache: a source revocation must stop the next API call."""
    try:
        if claims.get("session_version") != SESSION_VERSION:
            raise ValueError("Legacy session requires sign-in")
        _deadline(claims.get("exp"))
        source = claims.get("auth_source")
        binding = session_binding(source, claims.get("parent"))
        if source == "local":
            return
        if claims["exp"] > binding["parent"]["exp"]:
            raise ValueError("Wiki session outlives its parent")
    except (ValueError, TypeError, KeyError):
        raise _invalid() from None
    try:
        if source == "chatbot":
            await _verify_chatbot(binding["parent"])
        else:
            await _verify_oidc(binding["parent"])
    except httpx.HTTPError:
        raise _unavailable() from None
