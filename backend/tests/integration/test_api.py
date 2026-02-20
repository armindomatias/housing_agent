"""
Integration tests for API endpoints using FastAPI TestClient.

Tests basic endpoints (root, health) that don't require external services.
"""

from fastapi.testclient import TestClient


class TestRootEndpoint:
    """Tests for GET /."""

    def test_returns_api_info(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Rehabify API"
        assert data["version"] == "0.1.0"
        assert "docs" in data


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_returns_healthy(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAnalyzeHealthEndpoint:
    """Tests for GET /api/v1/analyze/health."""

    def test_returns_healthy(self, client: TestClient):
        response = client.get("/api/v1/analyze/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "rehabify-analyzer"


class TestRequestContextMiddleware:
    """Tests for X-Request-ID header injected by RequestContextMiddleware."""

    def test_request_id_header_present(self, client: TestClient):
        response = client.get("/health")
        assert "x-request-id" in response.headers

    def test_request_id_is_valid_uuid(self, client: TestClient):
        import uuid

        response = client.get("/health")
        request_id = response.headers["x-request-id"]
        # Should not raise ValueError
        uuid.UUID(request_id)

    def test_request_id_unique_per_request(self, client: TestClient):
        r1 = client.get("/health")
        r2 = client.get("/health")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


class TestAuthProtection:
    """Tests verifying that analyze endpoints require authentication."""

    def test_analyze_without_token_returns_401(self, client: TestClient):
        """POST /api/v1/analyze without a Bearer token returns 401."""
        response = client.post(
            "/api/v1/analyze",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )
        assert response.status_code == 401

    def test_analyze_sync_without_token_returns_401(self, client: TestClient):
        """POST /api/v1/analyze/sync without a Bearer token returns 401."""
        response = client.post(
            "/api/v1/analyze/sync",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )
        assert response.status_code == 401

    def test_health_endpoints_no_auth_required(self, client: TestClient):
        """Health check endpoints remain public (no auth required)."""
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/analyze/health").status_code == 200
