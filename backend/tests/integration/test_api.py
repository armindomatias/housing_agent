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
