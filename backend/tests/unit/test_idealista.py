"""
Tests for the Idealista service — pure logic only (no API calls).

Tests _validate_url() and _extract_property_id() methods.
"""

import pytest

from app.services.idealista import IdealistaService


@pytest.fixture
def service() -> IdealistaService:
    """IdealistaService with a fake token (no real API calls)."""
    return IdealistaService(apify_token="fake-token")


class TestValidateUrl:
    """Tests for IdealistaService._validate_url()."""

    def test_valid_url(self, service: IdealistaService):
        assert service._validate_url("https://www.idealista.pt/imovel/12345678/") is True

    def test_valid_url_without_trailing_slash(self, service: IdealistaService):
        assert service._validate_url("https://www.idealista.pt/imovel/12345678") is True

    def test_rejects_non_idealista_domain(self, service: IdealistaService):
        assert service._validate_url("https://www.example.com/imovel/12345678/") is False

    def test_rejects_idealista_spain(self, service: IdealistaService):
        assert service._validate_url("https://www.idealista.com/imovel/12345678/") is False

    def test_rejects_search_page(self, service: IdealistaService):
        assert service._validate_url("https://www.idealista.pt/comprar-casas/lisboa/") is False

    def test_rejects_empty_string(self, service: IdealistaService):
        assert service._validate_url("") is False

    def test_rejects_invalid_url(self, service: IdealistaService):
        assert service._validate_url("not a url") is False

    def test_accepts_subdomain(self, service: IdealistaService):
        assert service._validate_url("https://img.idealista.pt/imovel/123/") is True


class TestExtractPropertyId:
    """Tests for IdealistaService._extract_property_id()."""

    def test_extracts_numeric_id(self, service: IdealistaService):
        result = service._extract_property_id("https://www.idealista.pt/imovel/12345678/")
        assert result == "12345678"

    def test_extracts_id_without_trailing_slash(self, service: IdealistaService):
        result = service._extract_property_id("https://www.idealista.pt/imovel/99887766")
        assert result == "99887766"

    def test_returns_none_for_no_id(self, service: IdealistaService):
        result = service._extract_property_id("https://www.idealista.pt/comprar-casas/")
        assert result is None

    def test_returns_none_for_empty_string(self, service: IdealistaService):
        result = service._extract_property_id("")
        assert result is None

    def test_extracts_id_with_extra_path(self, service: IdealistaService):
        result = service._extract_property_id(
            "https://www.idealista.pt/imovel/12345678/fotos"
        )
        assert result == "12345678"
