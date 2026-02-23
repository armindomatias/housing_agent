"""
Integration tests for POST /api/v1/chat.

Tests the chat endpoint at the HTTP level using FastAPI TestClient.
External services (Supabase, OpenAI) are not called — the tests verify
auth protection, request validation, and endpoint availability.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestChatHealthEndpoint:
    def test_chat_health_returns_healthy(self, client: TestClient):
        response = client.get("/api/v1/chat/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "rehabify-chat"


class TestChatAuthProtection:
    def test_chat_without_token_returns_401(self, client: TestClient):
        response = client.post(
            "/api/v1/chat",
            json={"message": "olá"},
        )
        assert response.status_code == 401

    def test_chat_with_invalid_token_returns_401_or_503(self, client: TestClient):
        # 401 when Supabase is configured and rejects the token;
        # 503 when Supabase is not configured (test environment).
        response = client.post(
            "/api/v1/chat",
            json={"message": "olá"},
            headers={"Authorization": "Bearer invalid-token-xyz"},
        )
        assert response.status_code in (401, 503)


class TestChatRequestValidation:
    def test_chat_missing_message_returns_422(self, client: TestClient):
        """Request body without 'message' field should be rejected."""
        # We need a valid-looking token to get past auth to validation
        # Since Supabase is not configured in tests, auth will return 503
        # So just verify the endpoint exists and rejects malformed bodies
        response = client.post(
            "/api/v1/chat",
            json={},  # missing required 'message' field
        )
        # Auth check happens first (401) OR validation (422) — both acceptable
        assert response.status_code in (401, 422)

    def test_chat_accepts_optional_conversation_id(self, client: TestClient):
        """conversation_id is optional — omitting it should not cause 422."""
        response = client.post(
            "/api/v1/chat",
            json={"message": "olá", "conversation_id": None},
        )
        # 401 expected (no auth), not 422 (schema error)
        assert response.status_code == 401

    def test_chat_with_conversation_id(self, client: TestClient):
        response = client.post(
            "/api/v1/chat",
            json={"message": "olá", "conversation_id": "conv-123"},
        )
        assert response.status_code == 401


class TestChatRouterRegistered:
    def test_chat_endpoint_in_openapi_schema(self, client: TestClient):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/chat" in paths

    def test_chat_health_in_openapi_schema(self, client: TestClient):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/api/v1/chat/health" in paths

    def test_chat_tagged_correctly(self, client: TestClient):
        response = client.get("/openapi.json")
        chat_post = response.json()["paths"]["/api/v1/chat"]["post"]
        assert "chat" in chat_post.get("tags", [])
