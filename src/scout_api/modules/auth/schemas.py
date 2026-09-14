"""Authenticated principal and public user schemas (whitelist minimization)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Internal identity derived from a verified Supabase JWT (never serialize raw)."""

    id: UUID
    role: UserRole = UserRole.USER
    email: str | None = None
    display_name: str | None = None
    provider: str | None = None
    claims: dict[str, object] = field(default_factory=dict, repr=False)

    def has_permission(self, permission: str) -> bool:
        if self.role == UserRole.ADMIN:
            return True
        # Authenticated users: business permissions; admin-only gated separately.
        return permission in {
            "crawl",
            "match",
            "products:read",
            "products:write",
            "offers:refresh",
        }


class PublicUser(BaseModel):
    """Minimal user payload allowed across the public API boundary."""

    id: UUID
    display_name: str | None = None


class AuthSessionResponse(BaseModel):
    """Access token for API calls; refresh stays HttpOnly cookie when set by API."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    user: PublicUser


class GoogleAuthStartResponse(BaseModel):
    authorization_url: str


class AuthErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


def principal_to_public(principal: AuthenticatedPrincipal) -> PublicUser:
    return PublicUser(id=principal.id, display_name=principal.display_name)
