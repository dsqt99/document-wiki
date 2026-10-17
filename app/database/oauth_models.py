"""Persistence for the MCP endpoint's OAuth 2.1 flow: registered clients and
short-lived PKCE authorization codes."""

import secrets
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)


def _unique_token(length: int) -> Mapped[str]:
    return mapped_column(String(length), nullable=False, index=True, unique=True)


def _registered_at() -> Mapped[datetime]:
    """Timezone-aware timestamp the database fills in on insert."""
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthClient(Base):
    """A dynamically registered OAuth client."""

    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[str] = _unique_token(64)
    # Human-readable label supplied at registration (optional).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Exact-match allow-list consulted when an authorization request arrives.
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = _registered_at()

    @staticmethod
    def generate_client_id() -> str:
        """Fresh public identifier: ``client_`` plus 16 random URL-safe bytes."""
        return "client_" + secrets.token_urlsafe(16)


class OAuthAuthCode(Base):
    """One-time authorization code bound to a PKCE challenge."""

    __tablename__ = "oauth_auth_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = _unique_token(64)
    client_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(10), default="S256", server_default="S256")
    scope: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
