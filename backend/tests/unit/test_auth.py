"""
Unit tests for the auth dependency (get_current_user).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import AuthenticatedUser, get_current_user


def _make_request(supabase_client=None):
    """Create a mock FastAPI Request with app.state.supabase set."""
    request = MagicMock()
    request.app.state.supabase = supabase_client
    return request


def _make_credentials(token: str = "valid-token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """A valid token returns an AuthenticatedUser."""
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"

        mock_response = MagicMock()
        mock_response.user = mock_user

        mock_supabase = MagicMock()
        mock_supabase.auth.get_user = AsyncMock(return_value=mock_response)

        request = _make_request(supabase_client=mock_supabase)
        credentials = _make_credentials("valid-token")

        result = await get_current_user(request, credentials)

        assert isinstance(result, AuthenticatedUser)
        assert result.id == "user-123"
        assert result.email == "test@example.com"
        mock_supabase.auth.get_user.assert_awaited_once_with("valid-token")

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """A token that returns no user raises 401."""
        mock_response = MagicMock()
        mock_response.user = None

        mock_supabase = MagicMock()
        mock_supabase.auth.get_user = AsyncMock(return_value=mock_response)

        request = _make_request(supabase_client=mock_supabase)
        credentials = _make_credentials("bad-token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        """A token that causes an exception raises 401."""
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user = AsyncMock(side_effect=Exception("Token expired"))

        request = _make_request(supabase_client=mock_supabase)
        credentials = _make_credentials("expired-token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_supabase_client_raises_503(self):
        """When Supabase client is None, raises 503."""
        request = _make_request(supabase_client=None)
        credentials = _make_credentials("any-token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, credentials)

        assert exc_info.value.status_code == 503
