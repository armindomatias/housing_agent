"""
Integration test: full estimate node with mocked GPT.

Asserts both old fields (condition, cost_min/max, renovation_items)
AND new fields (features, cost_breakdown) are populated correctly.
Tests that backward-compat RoomAnalysis fields are populated from
the new feature extraction + cost calculator pipeline.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.features.enums import FinishLevel
from app.models.features.modules import PropertyContext
from app.models.features.outputs import UserPreferences
from app.models.property import RoomCondition, RoomType
from app.services.renovation_estimator import RenovationEstimatorService


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


def _kitchen_features_json() -> str:
    """Valid kitchen feature extraction response from GPT."""
    return json.dumps({
        "room_type": "cozinha",
        "surfaces": {
            "floor_material": "ceramic_tile",
            "floor_condition": 1,
            "wall_finish": "azulejos",
            "wall_condition": 1,
            "ceiling_condition": 2,
        },
        "fixtures": {
            "window_frame_material": "aluminum_single",
            "cabinet_condition": 1,
            "countertop_material": "laminate",
            "countertop_condition": 1,
            "appliances_visible": [],
            "door_condition": 2,
        },
        "mep": {
            "plumbing_visible_condition": "visible_corroded",
            "outlet_switch_style": "bakelite_old",
        },
        "estimated_area_m2": 9.0,
        "kitchen_notes": "Cozinha muito degradada.",
    })


@pytest.fixture
def estimator() -> RenovationEstimatorService:
    return RenovationEstimatorService(openai_api_key="sk-fake")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEstimateBackwardCompat:
    @pytest.mark.asyncio
    async def test_feature_extraction_populates_new_fields(
        self, estimator: RenovationEstimatorService
    ):
        """Feature extraction path populates features + cost_breakdown."""
        mock_resp = _make_response(content=_kitchen_features_json())

        with patch.object(
            estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_room(
                RoomType.KITCHEN,
                1,
                ["http://img/k1.jpg"],
                property_context=PropertyContext(),
            )

        # New fields populated
        assert result.features is not None
        assert result.cost_breakdown is not None

    @pytest.mark.asyncio
    async def test_feature_extraction_populates_backward_compat_fields(
        self, estimator: RenovationEstimatorService
    ):
        """Old fields (condition, cost_min/max, renovation_items) are populated."""
        mock_resp = _make_response(content=_kitchen_features_json())

        with patch.object(
            estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_room(
                RoomType.KITCHEN,
                1,
                ["http://img/k1.jpg"],
                property_context=PropertyContext(),
            )

        # Backward compat fields
        assert result.room_type == RoomType.KITCHEN
        assert result.room_number == 1
        assert result.condition in list(RoomCondition)
        assert result.cost_min >= 0
        assert result.cost_max >= result.cost_min
        assert isinstance(result.renovation_items, list)

    @pytest.mark.asyncio
    async def test_poor_kitchen_condition_is_poor_or_worse(
        self, estimator: RenovationEstimatorService
    ):
        """A kitchen with all condition scores 1 should map to POOR or NEEDS_FULL_RENOVATION."""
        mock_resp = _make_response(content=_kitchen_features_json())

        with patch.object(
            estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_room(
                RoomType.KITCHEN,
                1,
                ["http://img/k1.jpg"],
                property_context=PropertyContext(),
            )

        assert result.condition in (RoomCondition.POOR, RoomCondition.NEEDS_FULL_RENOVATION)

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_when_feature_extraction_fails(
        self, estimator: RenovationEstimatorService
    ):
        """When feature extraction returns None, legacy GPT analysis is used."""
        # Feature extractor returns null content → None
        feature_null_resp = _make_response(content=None)

        # Legacy estimator returns valid JSON
        legacy_json = json.dumps({
            "condition": "mau",
            "condition_notes": "Mau estado.",
            "renovation_items": [
                {"item": "Remodelação geral", "cost_min": 5000, "cost_max": 12000,
                 "priority": "alta", "notes": ""}
            ],
            "cost_min": 5000,
            "cost_max": 12000,
            "confidence": 0.6,
        })
        legacy_resp = _make_response(content=legacy_json)

        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            # First call = feature extractor (returns null to trigger fallback)
            if call_count == 1:
                return feature_null_resp
            # Second call = legacy estimator
            return legacy_resp

        with patch.object(
            estimator._feature_extractor.client.chat.completions,
            "create",
            side_effect=_side_effect,
        ):
            with patch.object(
                estimator.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=legacy_resp,
            ):
                result = await estimator.analyze_room(
                    RoomType.KITCHEN,
                    1,
                    ["http://img/k1.jpg"],
                )

        # Legacy path: no new fields
        assert result.features is None
        assert result.condition == RoomCondition.POOR  # "mau" → POOR
        assert result.cost_min == 5000.0
        assert result.cost_max == 12000.0

    @pytest.mark.asyncio
    async def test_diy_reduces_total_cost(self, estimator: RenovationEstimatorService):
        """Setting diy=True reduces total cost vs non-diy."""
        mock_resp = _make_response(content=_kitchen_features_json())

        std_estimator = RenovationEstimatorService(
            openai_api_key="sk-fake",
            user_preferences=UserPreferences(diy=False, finish_level=FinishLevel.STANDARD),
        )
        diy_estimator = RenovationEstimatorService(
            openai_api_key="sk-fake",
            user_preferences=UserPreferences(diy=True, finish_level=FinishLevel.STANDARD),
        )

        with patch.object(
            std_estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            std_result = await std_estimator.analyze_room(
                RoomType.KITCHEN, 1, ["http://img/k1.jpg"], property_context=PropertyContext()
            )

        with patch.object(
            diy_estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            diy_result = await diy_estimator.analyze_room(
                RoomType.KITCHEN, 1, ["http://img/k1.jpg"], property_context=PropertyContext()
            )

        assert diy_result.cost_max <= std_result.cost_max

    @pytest.mark.asyncio
    async def test_create_estimate_has_composite_indices(
        self, estimator: RenovationEstimatorService
    ):
        """create_estimate populates composite_indices when features are present."""
        mock_resp = _make_response(content=_kitchen_features_json())

        with patch.object(
            estimator._feature_extractor.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            room_analysis = await estimator.analyze_room(
                RoomType.KITCHEN, 1, ["http://img/k1.jpg"], property_context=PropertyContext()
            )

        summary_resp = _make_response(content="Resumo de teste.")
        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=summary_resp,
        ):
            summary = await estimator.generate_summary(None, [room_analysis], room_analysis.cost_min, room_analysis.cost_max)

        estimate = estimator.create_estimate(
            "https://www.idealista.pt/imovel/test/",
            None,
            [room_analysis],
            summary,
        )

        assert estimate.user_preferences is not None
        # composite_indices populated only when features are present
        if room_analysis.features is not None:
            assert estimate.composite_indices is not None
