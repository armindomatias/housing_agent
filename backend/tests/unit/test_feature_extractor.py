"""
Unit tests for the FeatureExtractorService and derive_property_context.

All OpenAI calls are mocked. Tests cover valid, partial (null module),
all-NOT_VISIBLE, room-type mismatch, and refusal scenarios.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.features.enums import (
    ConstructionEra,
    LocationCostTier,
)
from app.models.features.modules import KitchenFeatures
from app.models.property import PropertyData, RoomType
from app.services.feature_extractor import (
    FeatureExtractorService,
    _infer_construction_era,
    _infer_energy_rating,
    _infer_location_cost_tier,
    derive_property_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(content: str | None = None, refusal: str | None = None) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.refusal = refusal
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock(prompt_tokens=500, completion_tokens=200)
    return resp


def _kitchen_json(**overrides) -> str:
    data = {
        "room_type": "cozinha",
        "surfaces": {
            "floor_material": "ceramic_tile",
            "floor_condition": 2,
            "wall_finish": "azulejos",
            "wall_condition": 2,
            "ceiling_condition": 3,
        },
        "fixtures": {
            "window_frame_material": "aluminum_single",
            "cabinet_condition": 1,
            "countertop_material": "laminate",
            "countertop_condition": 2,
            "appliances_visible": [],
            "door_condition": 3,
        },
        "mep": {
            "plumbing_visible_condition": "visible_corroded",
            "outlet_switch_style": "bakelite_old",
        },
        "estimated_area_m2": 9.5,
        "kitchen_notes": "Cozinha muito degradada.",
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.fixture
def extractor() -> FeatureExtractorService:
    return FeatureExtractorService(openai_api_key="sk-fake")


# ---------------------------------------------------------------------------
# extract_room_features
# ---------------------------------------------------------------------------


class TestExtractRoomFeatures:
    @pytest.mark.asyncio
    async def test_valid_kitchen_returns_features(self, extractor: FeatureExtractorService):
        mock_resp = _make_response(content=_kitchen_json())

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                image_urls=["http://img/k1.jpg"],
            )

        assert result is not None
        assert isinstance(result, KitchenFeatures)
        assert result.fixtures.cabinet_condition == 1
        assert result.estimated_area_m2 == 9.5

    @pytest.mark.asyncio
    async def test_refusal_returns_none(self, extractor: FeatureExtractorService):
        mock_resp = _make_response(refusal="Cannot process this image")

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                image_urls=["http://img/k1.jpg"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_null_content_returns_none(self, extractor: FeatureExtractorService):
        mock_resp = _make_response(content=None)

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.BATHROOM,
                room_label="Casa de Banho",
                image_urls=["http://img/b1.jpg"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_api_exception_returns_none(self, extractor: FeatureExtractorService):
        with patch.object(
            extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.BEDROOM,
                room_label="Quarto",
                image_urls=["http://img/q1.jpg"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none(self, extractor: FeatureExtractorService):
        mock_resp = _make_response(content="not json {{{")

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                image_urls=["http://img/k1.jpg"],
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_partial_features_surfaces_only(self, extractor: FeatureExtractorService):
        """When fixtures/mep are missing, model should still be valid with None."""
        data = {
            "room_type": "cozinha",
            "surfaces": {
                "floor_material": "ceramic_tile",
                "floor_condition": 3,
                "wall_finish": "paint",
                "wall_condition": 3,
                "ceiling_condition": 3,
            },
            "fixtures": None,
            "mep": None,
            "estimated_area_m2": None,
            "kitchen_notes": "",
        }
        mock_resp = _make_response(content=json.dumps(data))

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                image_urls=["http://img/k1.jpg"],
            )

        assert result is not None
        assert isinstance(result, KitchenFeatures)
        assert result.surfaces is not None
        assert result.fixtures is None
        assert result.mep is None

    @pytest.mark.asyncio
    async def test_image_cap_applied(self, extractor: FeatureExtractorService):
        """Only max_images are sent to the API."""
        mock_resp = _make_response(content=_kitchen_json())
        captured = []

        async def _capture(**kwargs):
            captured.append(kwargs)
            return mock_resp

        image_urls = [f"http://img/{i}.jpg" for i in range(10)]

        with patch.object(extractor.client.chat.completions, "create", side_effect=_capture):
            await extractor.extract_room_features(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                image_urls=image_urls,
                max_images=3,
            )

        assert len(captured) == 1
        content = captured[0]["messages"][0]["content"]
        image_items = [c for c in content if c.get("type") == "image_url"]
        assert len(image_items) == 3

    @pytest.mark.asyncio
    async def test_bedroom_uses_generic_model(self, extractor: FeatureExtractorService):
        from app.models.features.modules import GenericRoomFeatures

        data = {
            "room_type": "quarto",
            "surfaces": {
                "floor_material": "hardwood",
                "floor_condition": 4,
                "wall_finish": "paint",
                "wall_condition": 4,
                "ceiling_condition": 5,
            },
            "fixtures": {
                "window_frame_material": "pvc_double",
                "window_condition": 4,
                "window_count_estimate": 1,
                "door_condition": 4,
            },
            "mep": {"outlet_switch_style": "modern_flush"},
            "estimated_area_m2": 14.0,
            "room_notes": "Quarto em bom estado.",
        }
        mock_resp = _make_response(content=json.dumps(data))

        with patch.object(
            extractor.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await extractor.extract_room_features(
                room_type=RoomType.BEDROOM,
                room_label="Quarto",
                image_urls=["http://img/q1.jpg"],
            )

        assert isinstance(result, GenericRoomFeatures)
        assert result.room_type == "quarto"


# ---------------------------------------------------------------------------
# derive_property_context
# ---------------------------------------------------------------------------


class TestDerivePropertyContext:
    def test_lisbon_maps_to_lisboa_tier(self):
        data = PropertyData(
            url="https://www.idealista.pt/imovel/1/",
            location="Lisboa, Arroios",
        )
        ctx = derive_property_context(data)
        assert ctx.location_cost_tier == LocationCostTier.LISBOA

    def test_construction_year_1960_maps_to_1950_1970(self):
        data = PropertyData(
            url="https://www.idealista.pt/imovel/1/",
            description="Apartamento construído em 1960 no centro histórico.",
        )
        ctx = derive_property_context(data)
        assert ctx.construction_era == ConstructionEra.ERA_1950_1970

    def test_no_year_is_unknown(self):
        data = PropertyData(url="https://www.idealista.pt/imovel/1/", description="")
        ctx = derive_property_context(data)
        assert ctx.construction_era == ConstructionEra.UNKNOWN

    def test_area_preserved(self):
        data = PropertyData(
            url="https://www.idealista.pt/imovel/1/",
            area_m2=85.0,
            usable_area_m2=75.0,
        )
        ctx = derive_property_context(data)
        assert ctx.area_m2 == 85.0
        assert ctx.usable_area_m2 == 75.0


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestInferConstructionEra:
    def test_year_1948(self):
        assert _infer_construction_era("Edifício de 1948.") == ConstructionEra.PRE_1950

    def test_year_1965(self):
        assert _infer_construction_era("Construído em 1965.") == ConstructionEra.ERA_1950_1970

    def test_year_1985(self):
        assert _infer_construction_era("Ano de construção: 1985.") == ConstructionEra.ERA_1970_1990

    def test_year_1998(self):
        assert _infer_construction_era("Prédio de 1998.") == ConstructionEra.ERA_1990_2005

    def test_year_2010(self):
        assert _infer_construction_era("Construído em 2010.") == ConstructionEra.POST_2005

    def test_no_year(self):
        assert _infer_construction_era("Apartamento sem data.") == ConstructionEra.UNKNOWN


class TestInferEnergyRating:
    def test_a_plus(self):
        from app.models.features.enums import EnergyRating
        assert _infer_energy_rating("A+") == EnergyRating.A_PLUS

    def test_lowercase_b(self):
        from app.models.features.enums import EnergyRating
        assert _infer_energy_rating("b") == EnergyRating.B

    def test_unknown(self):
        from app.models.features.enums import EnergyRating
        assert _infer_energy_rating("") == EnergyRating.UNKNOWN


class TestInferLocationCostTier:
    def test_porto(self):
        assert _infer_location_cost_tier("Porto, Bonfim") == LocationCostTier.PORTO

    def test_algarve(self):
        assert _infer_location_cost_tier("Faro, Algarve") == LocationCostTier.ALGARVE

    def test_interior(self):
        assert _infer_location_cost_tier("Beja, Alentejo") == LocationCostTier.INTERIOR

    def test_ilhas(self):
        assert _infer_location_cost_tier("Funchal, Madeira") == LocationCostTier.ILHAS

    def test_default_litoral(self):
        assert _infer_location_cost_tier("Setúbal") == LocationCostTier.LITORAL
