"""Outbound delivery of notifications: email (SMTP) and webhook (06 §9.3).

Settings come from ConfigService keys. Channels run concurrently; every failure is
logged and swallowed.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
import uuid
from email.message import EmailMessage
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 15
WEBHOOK_TIMEOUT = 10
_TRUE = {"true", "1", "yes", "on"}


async def _cfg(db, key: str, default: str = "") -> str:
    from app.services.config_service import ConfigService

    try:
        value = await ConfigService(db).get(key)
    except Exception as e:
        logger.debug("config %s unavailable: %s", key, e)
        value = None
    return default if value in (None, "") else str(value)


def _enabled(value: str) -> bool:
    return (value or "").strip().lower() in _TRUE


def _portal_url() -> str:
    try:
        from app.config import settings

        return (getattr(settings, "portal_base_url", "") or "").rstrip("/")
    except Exception:
        return ""


def build_email(name: Optional[str], items: list[dict]) -> tuple[str, str]:
    subject = items[0]["subject"] if len(items) == 1 else f"Document Wiki — {len(items)} new notifications"
    lines = [f"Xin chào {name or ''},".replace(" ,", ","), "", "Bạn có thông báo mới trên Document Wiki:", ""]
    for it in items:
        lines.append(f"- {it.get('subject') or ''}")
        body = (it.get("body") or "").strip()
        if body:
            lines.append(f"  {body}")
    lines.append("")
    url = _portal_url()
    lines.append(f"Mở Document Wiki để xem chi tiết{': ' + url if url else '.'}")
    return subject, "\n".join(lines)


def _send_smtp(cfg: dict, messages: list[EmailMessage]) -> None:
    port = int(cfg["port"] or 587)
    with smtplib.SMTP(cfg["host"], port, timeout=SMTP_TIMEOUT) as smtp:
        if _enabled(cfg["use_tls"]):
            smtp.starttls()
        if cfg["username"]:
            smtp.login(cfg["username"], cfg["password"])
        for msg in messages:
            smtp.send_message(msg)


async def send_email(db, items: list[dict]) -> int:
    if not _enabled(await _cfg(db, "smtp_enabled", "false")):
        return 0
    cfg = {
        "host": await _cfg(db, "smtp_host"),
        "port": await _cfg(db, "smtp_port", "587"),
        "username": await _cfg(db, "smtp_username"),
        "password": await _cfg(db, "smtp_password"),
        "from": await _cfg(db, "smtp_from", "arkon@localhost"),
        "use_tls": await _cfg(db, "smtp_use_tls", "true"),
    }
    if not cfg["host"]:
        logger.warning("smtp_enabled but smtp_host is empty; skipping email")
        return 0
    from app.database.models import Employee

    by_recipient: dict[str, list[dict]] = {}
    for it in items:
        if it.get("recipient_id"):
            by_recipient.setdefault(it["recipient_id"], []).append(it)
    if not by_recipient:
        return 0
    ids = []
    for rid in by_recipient:
        try:
            ids.append(uuid.UUID(rid))
        except ValueError:
            continue
    res = await db.execute(select(Employee.id, Employee.name, Employee.email).where(Employee.id.in_(ids)))
    messages = []
    for emp_id, name, email in res.all():
        if not email:
            continue
        subject, text = build_email(name, by_recipient.get(str(emp_id), []))
        msg = EmailMessage()
        msg["From"] = cfg["from"]
        msg["To"] = email
        msg["Subject"] = subject
        msg.set_content(text)
        messages.append(msg)
    if messages:
        await asyncio.to_thread(_send_smtp, cfg, messages)
    return len(messages)


def sign_body(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def send_webhook(db, items: list[dict]) -> bool:
    if not _enabled(await _cfg(db, "webhook_enabled", "false")):
        return False
    url = await _cfg(db, "webhook_url")
    if not url:
        logger.warning("webhook_enabled but webhook_url is empty; skipping webhook")
        return False
    secret = await _cfg(db, "webhook_secret")
    body = json.dumps({"events": items}, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Document Wiki-Webhook/1"}
    if secret:
        headers["X-Arkon-Signature"] = sign_body(secret, body)
    import httpx

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        resp = await client.post(url, content=body, headers=headers)
        if resp.status_code >= 400:
            logger.warning("webhook returned HTTP %s", resp.status_code)
            return False
    return True


async def dispatch(db, items: list[dict]) -> None:
    if not items:
        return

    async def _guard(coro, label):
        try:
            await coro
        except Exception as e:
            logger.warning("notification %s channel failed: %s", label, e)

    await asyncio.gather(_guard(send_email(db, items), "email"), _guard(send_webhook(db, items), "webhook"))
