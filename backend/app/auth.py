"""
Authentication dependency for FastAPI endpoints.

Provides JWT verification via Supabase auth.get_user() and a FastAPI
dependency that can be used to protect endpoints.
"""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

_bearer_scheme = HTTPBearer()


class AuthenticatedUser(BaseModel):
    """Represents a verified authenticated user."""

    id: str
    email: str | None = None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that verifies a JWT Bearer token via Supabase.

    Raises:
        HTTPException 503: Supabase client not configured.
        HTTPException 401: Token is invalid, expired, or user not found.
    """
    supabase = getattr(request.app.state, "supabase", None)
    if supabase is None:
        raise HTTPException(status_code=503, detail="Serviço de autenticação indisponível")

    token = credentials.credentials
    try:
        response = await supabase.auth.get_user(token)
        user = response.user if response else None
        if user is None:
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")
        return AuthenticatedUser(id=str(user.id), email=user.email)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("auth_token_verification_failed", error=str(e))
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
