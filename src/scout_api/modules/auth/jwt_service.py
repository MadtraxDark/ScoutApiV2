"""Verify Supabase Auth JWTs (JWKS ES256/RS256 or HS256 secret for tests/legacy)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWKClient

from scout_api.core.config import Settings, get_settings
from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole

logger = logging.getLogger(__name__)

_ALLOWED_ASYMMETRIC = ("ES256", "RS256")
_ALLOWED_SYMMETRIC = ("HS256",)


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _admin_ids(settings: Settings) -> set[str]:
    raw = (settings.auth_admin_user_ids or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _role_for(sub: str, claims: dict[str, Any], settings: Settings) -> UserRole:
    if sub in _admin_ids(settings):
        return UserRole.ADMIN
    app_meta = claims.get("app_metadata")
    if isinstance(app_meta, dict):
        role = app_meta.get("role")
        if role == "admin":
            return UserRole.ADMIN
    return UserRole.USER


def _display_name(claims: dict[str, Any]) -> str | None:
    meta = claims.get("user_metadata")
    if isinstance(meta, dict):
        for key in ("full_name", "name", "preferred_username"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:128]
    return None


def _provider(claims: dict[str, Any]) -> str | None:
    app_meta = claims.get("app_metadata")
    if isinstance(app_meta, dict):
        provider = app_meta.get("provider")
        if isinstance(provider, str):
            return provider
    return None


def verify_access_token(
    token: str,
    settings: Settings | None = None,
    *,
    _jwks_retry: bool = True,
) -> AuthenticatedPrincipal:
    """Validate signature + standard claims; raise AuthError on failure."""
    cfg = settings or get_settings()
    if not token or token.count(".") != 2:
        raise AuthError("INVALID_TOKEN", "Token ausente ou malformado")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("INVALID_TOKEN", "Cabeçalho JWT inválido") from exc

    alg = header.get("alg")
    if alg is None or alg == "none" or not isinstance(alg, str):
        raise AuthError("INVALID_TOKEN", "Algoritmo JWT não permitido")

    claims: dict[str, Any]
    try:
        if alg in _ALLOWED_ASYMMETRIC:
            if not cfg.supabase_url:
                raise AuthError("AUTH_MISCONFIGURED", "SUPABASE_URL não configurada")
            jwks_url = f"{cfg.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            client = _jwks_client(jwks_url)
            signing_key = client.get_signing_key_from_jwt(token)
            issuer = f"{cfg.supabase_url.rstrip('/')}/auth/v1"
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_ALLOWED_ASYMMETRIC),
                audience=cfg.supabase_jwt_audience,
                issuer=issuer,
                options={
                    "require": ["exp", "sub", "iss", "aud"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        elif alg in _ALLOWED_SYMMETRIC:
            if not cfg.supabase_jwt_secret:
                raise AuthError(
                    "AUTH_MISCONFIGURED",
                    "SUPABASE_JWT_SECRET necessário para HS256",
                )
            decode_kwargs: dict[str, Any] = {
                "algorithms": list(_ALLOWED_SYMMETRIC),
                "audience": cfg.supabase_jwt_audience,
                "options": {
                    "require": ["exp", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                },
            }
            if cfg.supabase_url:
                decode_kwargs["issuer"] = f"{cfg.supabase_url.rstrip('/')}/auth/v1"
                decode_kwargs["options"]["require"] = ["exp", "sub", "iss", "aud"]
                decode_kwargs["options"]["verify_iss"] = True
            claims = jwt.decode(token, cfg.supabase_jwt_secret, **decode_kwargs)
        else:
            raise AuthError("INVALID_TOKEN", "Algoritmo JWT não permitido")
    except AuthError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("TOKEN_EXPIRED", "Token expirado") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("INVALID_TOKEN", "Audience JWT inválida") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("INVALID_TOKEN", "Issuer JWT inválido") from exc
    except jwt.PyJWTError as exc:
        if _jwks_retry and alg in _ALLOWED_ASYMMETRIC and cfg.supabase_url:
            _jwks_client.cache_clear()
            return verify_access_token(token, settings=cfg, _jwks_retry=False)
        raise AuthError("INVALID_TOKEN", "Token inválido") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise AuthError("INVALID_TOKEN", "Subject JWT ausente")
    try:
        user_id = UUID(sub)
    except ValueError as exc:
        raise AuthError("INVALID_TOKEN", "Subject JWT inválido") from exc

    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    return AuthenticatedPrincipal(
        id=user_id,
        role=_role_for(sub, claims, cfg),
        email=email,
        display_name=_display_name(claims),
        provider=_provider(claims),
        claims=dict(claims),
    )


def exchange_auth_code(
    *,
    code: str,
    code_verifier: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Exchange PKCE auth code with Supabase Auth (server-side only)."""
    cfg = settings or get_settings()
    if not cfg.supabase_url or not cfg.supabase_anon_key:
        raise AuthError("AUTH_MISCONFIGURED", "Supabase Auth não configurado")
    url = f"{cfg.supabase_url.rstrip('/')}/auth/v1/token?grant_type=pkce"
    headers = {
        "apikey": cfg.supabase_anon_key,
        "Authorization": f"Bearer {cfg.supabase_anon_key}",
        "Content-Type": "application/json",
    }
    payload = {"auth_code": code, "code_verifier": code_verifier}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=15.0)
    except httpx.HTTPError as exc:
        raise AuthError(
            "AUTH_PROVIDER_ERROR", "Falha ao contatar Supabase Auth"
        ) from exc
    if response.status_code >= 400:
        raise AuthError("INVALID_TOKEN", "Código de autenticação inválido")
    data = response.json()
    if not isinstance(data, dict) or "access_token" not in data:
        raise AuthError("AUTH_PROVIDER_ERROR", "Resposta Auth inválida")
    return data


def refresh_session(
    refresh_token: str, settings: Settings | None = None
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.supabase_url or not cfg.supabase_anon_key:
        raise AuthError("AUTH_MISCONFIGURED", "Supabase Auth não configurado")
    url = f"{cfg.supabase_url.rstrip('/')}/auth/v1/token?grant_type=refresh_token"
    headers = {
        "apikey": cfg.supabase_anon_key,
        "Authorization": f"Bearer {cfg.supabase_anon_key}",
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            url,
            headers=headers,
            json={"refresh_token": refresh_token},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise AuthError("AUTH_PROVIDER_ERROR", "Falha ao renovar sessão") from exc
    if response.status_code >= 400:
        raise AuthError("INVALID_TOKEN", "Refresh token inválido")
    data = response.json()
    if not isinstance(data, dict) or "access_token" not in data:
        raise AuthError("AUTH_PROVIDER_ERROR", "Resposta Auth inválida")
    return data


def build_google_authorize_url(
    *,
    redirect_to: str,
    code_challenge: str,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    if not cfg.supabase_url:
        raise AuthError("AUTH_MISCONFIGURED", "SUPABASE_URL não configurada")
    from urllib.parse import urlencode

    query = urlencode(
        {
            "provider": "google",
            "redirect_to": redirect_to,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{cfg.supabase_url.rstrip('/')}/auth/v1/authorize?{query}"
