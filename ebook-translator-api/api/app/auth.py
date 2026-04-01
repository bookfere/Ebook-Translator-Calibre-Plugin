from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import Settings, get_settings


@dataclass
class AuthContext:
    user_id: str
    claims: dict[str, Any]
    is_admin: bool


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=8)
def get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {exc}",
        ) from exc

    algorithm = str(header.get("alg", "")).upper()

    if algorithm == "RS256":
        try:
            signing_key = get_jwks_client(settings.effective_supabase_jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.supabase_jwt_audience,
                issuer=settings.effective_supabase_jwt_issuer,
            )
            return payload
        except Exception:  # noqa: BLE001
            # Some Supabase projects/tokens may not validate cleanly via local JWKS.
            # Fallback to Supabase user introspection when a publishable key is available.
            pass

    publishable_key = settings.effective_supabase_publishable_key
    if not publishable_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Token algorithm is not RS256 and no publishable key is configured. "
                "Set SUPABASE_PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY."
            ),
        )

    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": publishable_key,
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: Supabase user lookup failed ({response.status_code})",
            )
        user_payload = response.json()
        if "id" not in user_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: Supabase response missing user id",
            )

        # Align shape with JWT payload keys used by AuthContext.
        payload: dict[str, Any] = {
            "sub": user_payload["id"],
            "role": user_payload.get("role"),
            "app_metadata": user_payload.get("app_metadata") or {},
            "email": user_payload.get("email"),
        }
        return payload
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    payload = decode_token(credentials.credentials, settings)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject claim")
    try:
        UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject claim") from exc

    role = payload.get("role")
    app_metadata = payload.get("app_metadata") or {}
    roles = app_metadata.get("roles") or []
    is_admin = bool(role == settings.supabase_admin_role or settings.supabase_admin_role in roles)

    return AuthContext(user_id=user_id, claims=payload, is_admin=is_admin)


async def require_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return auth
