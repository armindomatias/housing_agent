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
