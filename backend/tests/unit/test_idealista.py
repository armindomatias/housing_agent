"""
Tests for the Idealista service — pure logic only (no API calls).

Tests _validate_url(), _extract_property_id(), _parse_ndjson_response(),
and _parse_apify_result() methods.
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


class TestParseNdjsonResponse:
    """Tests for IdealistaService._parse_ndjson_response()."""

    def test_single_line(self):
        text = '{"id": 1, "title": "Flat"}\n'
        result = IdealistaService._parse_ndjson_response(text)
        assert result == [{"id": 1, "title": "Flat"}]

    def test_multiple_lines(self):
        text = '{"id": 1}\n{"id": 2}\n{"id": 3}\n'
        result = IdealistaService._parse_ndjson_response(text)
        assert len(result) == 3
        assert result[1] == {"id": 2}

    def test_skips_empty_lines(self):
        text = '{"id": 1}\n\n\n{"id": 2}\n'
        result = IdealistaService._parse_ndjson_response(text)
        assert len(result) == 2

    def test_empty_string(self):
        result = IdealistaService._parse_ndjson_response("")
        assert result == []

    def test_whitespace_only(self):
        result = IdealistaService._parse_ndjson_response("   \n  \n   ")
        assert result == []


class TestParseApifyResult:
    """Tests for IdealistaService._parse_apify_result() with new actor schema."""

    @pytest.fixture
    def full_actor_response(self) -> dict:
        """A realistic response from dz_omar/idealista-scraper-api."""
        return {
            "title": "Apartamento T3 em Benfica",
            "operation": "sale",
            "extendedPropertyType": "flat",
            "description": "Excelente apartamento remodelado.",
            "priceInfo": {"amount": 320000},
            "moreCharacteristics": {
                "constructedArea": 95,
                "roomNumber": 3,
                "bathNumber": 2,
                "floor": "4",
                "lift": True,
                "status": "good",
            },
            "ubication": {
                "title": "Benfica, Lisboa",
                "administrativeAreaLevel2": "Lisboa",
                "administrativeAreaLevel1": "Lisboa",
                "latitude": 38.7508,
                "longitude": -9.2033,
            },
            "multimedia": {
                "images": [
                    {"url": "https://img.idealista.pt/1.jpg", "tag": "kitchen"},
                    {"url": "https://img.idealista.pt/2.jpg", "tag": "bedroom"},
                    {"url": "https://img.idealista.pt/3.jpg"},
                ]
            },
        }

    def test_title(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.title == "Apartamento T3 em Benfica"

    def test_title_fallback_to_ubication(self, service: IdealistaService, full_actor_response: dict):
        del full_actor_response["title"]
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.title == "Benfica, Lisboa"

    def test_price_from_price_info(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.price == 320000.0

    def test_price_fallback_to_price_field(self, service: IdealistaService):
        data = {"price": 250000}
        result = service._parse_apify_result("https://url", data)
        assert result.price == 250000.0

    def test_area(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.area_m2 == 95.0

    def test_rooms_and_bathrooms(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.num_rooms == 3
        assert result.num_bathrooms == 2

    def test_floor(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.floor == "4"

    def test_location_joined(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.location == "Lisboa, Lisboa"

    def test_location_city_only(self, service: IdealistaService):
        data = {"ubication": {"administrativeAreaLevel2": "Porto"}}
        result = service._parse_apify_result("https://url", data)
        assert result.location == "Porto"

    def test_description(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.description == "Excelente apartamento remodelado."

    def test_image_urls(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert len(result.image_urls) == 3
        assert result.image_urls[0] == "https://img.idealista.pt/1.jpg"

    def test_image_tags(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.image_tags == {
            "https://img.idealista.pt/1.jpg": "kitchen",
            "https://img.idealista.pt/2.jpg": "bedroom",
        }

    def test_operation(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.operation == "sale"

    def test_property_type(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.property_type == "flat"

    def test_coordinates(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.latitude == 38.7508
        assert result.longitude == -9.2033

    def test_has_elevator(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.has_elevator is True

    def test_condition_status(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.condition_status == "good"

    def test_raw_data_preserved(self, service: IdealistaService, full_actor_response: dict):
        result = service._parse_apify_result("https://url", full_actor_response)
        assert result.raw_data == full_actor_response

    def test_missing_sections_return_defaults(self, service: IdealistaService):
        result = service._parse_apify_result("https://url", {})
        assert result.title == ""
        assert result.price == 0.0
        assert result.area_m2 == 0.0
        assert result.num_rooms == 0
        assert result.image_urls == []
        assert result.image_tags == {}
        assert result.latitude is None
        assert result.longitude is None
        assert result.has_elevator is None
        assert result.condition_status == ""
        assert result.location == ""
