"""
Tests for the RenovationEstimatorService.

All OpenAI API calls are mocked. No real HTTP traffic.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.property import FloorPlanAnalysis, RoomCondition, RoomType
from app.services.renovation_estimator import RenovationEstimatorService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    content: str | None = None,
    refusal: str | None = None,
    finish_reason: str = "stop",
) -> MagicMock:
    """Build a minimal fake OpenAI chat completion response."""
    msg = MagicMock()
    msg.content = content
    msg.refusal = refusal

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _room_response_json(
    condition: str = "razoavel",
    cost_min: float = 2000,
    cost_max: float = 5000,
    confidence: float = 0.7,
) -> str:
    return json.dumps(
        {
            "condition": condition,
            "condition_notes": "Test notes",
            "renovation_items": [
                {
                    "item": "Pintura",
                    "cost_min": cost_min,
                    "cost_max": cost_max,
                    "priority": "media",
                    "notes": "",
                }
            ],
            "cost_min": cost_min,
            "cost_max": cost_max,
            "confidence": confidence,
        }
    )


@pytest.fixture
def estimator() -> RenovationEstimatorService:
    return RenovationEstimatorService(openai_api_key="sk-fake-key")


# ---------------------------------------------------------------------------
# TestAnalyzeRoom
# ---------------------------------------------------------------------------


class TestAnalyzeRoom:
    """Tests for RenovationEstimatorService.analyze_room()."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_room_analysis(self, estimator: RenovationEstimatorService):
        """Valid JSON response is parsed into a RoomAnalysis with correct values."""
        mock_resp = _make_mock_response(content=_room_response_json("bom", 1000, 3000, 0.8))

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await estimator.analyze_room(RoomType.KITCHEN, 1, ["http://img/k1.jpg"])

        assert result.room_type == RoomType.KITCHEN
        assert result.room_number == 1
        assert result.condition == RoomCondition.GOOD
        assert result.cost_min == 1000.0
        assert result.cost_max == 3000.0
        assert result.confidence > 0  # boosted by image count

    @pytest.mark.asyncio
    async def test_null_content_retries_once_and_succeeds(
        self, estimator: RenovationEstimatorService
    ):
        """When first call returns null content, it retries once and uses the successful result."""
        null_resp = _make_mock_response(content=None)
        good_resp = _make_mock_response(content=_room_response_json())

        call_count = 0

        async def _side_effect(**_):
            nonlocal call_count
            call_count += 1
            return null_resp if call_count == 1 else good_resp

        with patch.object(estimator.client.chat.completions, "create", side_effect=_side_effect):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await estimator.analyze_room(RoomType.BEDROOM, 1, ["http://img/b1.jpg"])

        assert call_count == 2
        assert result.confidence > 0  # not fallback

    @pytest.mark.asyncio
    async def test_null_content_retry_also_fails_returns_fallback(
        self, estimator: RenovationEstimatorService
    ):
        """When both API calls return null content, fallback analysis is returned."""
        null_resp = _make_mock_response(content=None)

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=null_resp
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await estimator.analyze_room(RoomType.BATHROOM, 1, ["http://img/bath.jpg"])

        assert result.confidence == 0.3  # fallback marker
        assert result.room_type == RoomType.BATHROOM

    @pytest.mark.asyncio
    async def test_refusal_no_retry_returns_fallback(
        self, estimator: RenovationEstimatorService
    ):
        """When OpenAI refuses the request, no retry is attempted and fallback is returned."""
        refusal_resp = _make_mock_response(refusal="Content policy violation")

        call_count = 0

        async def _side_effect(**_):
            nonlocal call_count
            call_count += 1
            return refusal_resp

        with patch.object(estimator.client.chat.completions, "create", side_effect=_side_effect):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await estimator.analyze_room(RoomType.KITCHEN, 1, ["http://img/k.jpg"])

        # No retry should happen for refusals
        assert call_count == 1
        mock_sleep.assert_not_called()
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_fallback(
        self, estimator: RenovationEstimatorService
    ):
        """Malformed JSON from OpenAI triggers fallback without crashing."""
        bad_json_resp = _make_mock_response(content="not { valid json {{{")

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=bad_json_resp
        ):
            result = await estimator.analyze_room(RoomType.LIVING_ROOM, 1, ["http://img/s.jpg"])

        assert result.confidence == 0.3
        assert result.room_type == RoomType.LIVING_ROOM

    @pytest.mark.asyncio
    async def test_api_exception_returns_fallback(
        self, estimator: RenovationEstimatorService
    ):
        """Any API exception (network, auth, etc.) triggers fallback."""
        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API unavailable"),
        ):
            result = await estimator.analyze_room(RoomType.HALLWAY, 1, ["http://img/h.jpg"])

        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_image_cap_at_4(self, estimator: RenovationEstimatorService):
        """Only the first 4 images are sent to the API, regardless of input length."""
        good_resp = _make_mock_response(content=_room_response_json())
        image_urls = [f"http://img/{i}.jpg" for i in range(10)]

        captured_messages = []

        async def _capture(**kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return good_resp

        with patch.object(estimator.client.chat.completions, "create", side_effect=_capture):
            await estimator.analyze_room(RoomType.BEDROOM, 1, image_urls)

        assert len(captured_messages) >= 1
        content = captured_messages[0][0]["content"]
        # Count image_url entries in content
        image_entries = [item for item in content if item.get("type") == "image_url"]
        assert len(image_entries) == 4


# ---------------------------------------------------------------------------
# TestGetFallbackAnalysis
# ---------------------------------------------------------------------------


class TestGetFallbackAnalysis:
    """Tests for RenovationEstimatorService._get_fallback_analysis()."""

    def test_kitchen_fallback_costs(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.KITCHEN, 1, "Cozinha", [])
        assert result.cost_min == 5000
        assert result.cost_max == 15000

    def test_bathroom_fallback_costs(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.BATHROOM, 1, "Casa de Banho 1", [])
        assert result.cost_min == 3000
        assert result.cost_max == 8000

    def test_bedroom_fallback_costs(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.BEDROOM, 1, "Quarto 1", [])
        assert result.cost_min == 1000
        assert result.cost_max == 3000

    def test_unknown_room_defaults_to_other_costs(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.OTHER, 1, "Outro", [])
        assert result.cost_min == 500
        assert result.cost_max == 2000

    def test_condition_is_fair(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.KITCHEN, 1, "Cozinha", [])
        assert result.condition == RoomCondition.FAIR

    def test_confidence_is_low(self, estimator: RenovationEstimatorService):
        result = estimator._get_fallback_analysis(RoomType.KITCHEN, 1, "Cozinha", [])
        assert result.confidence == 0.3

    def test_images_preserved(self, estimator: RenovationEstimatorService):
        urls = ["http://img/a.jpg", "http://img/b.jpg"]
        result = estimator._get_fallback_analysis(RoomType.BEDROOM, 1, "Quarto 1", urls)
        assert result.images == urls


# ---------------------------------------------------------------------------
# TestMapCondition
# ---------------------------------------------------------------------------


class TestMapCondition:
    """Tests for RenovationEstimatorService._map_condition()."""

    def test_portuguese_conditions(self, estimator: RenovationEstimatorService):
        assert estimator._map_condition("excelente") == RoomCondition.EXCELLENT
        assert estimator._map_condition("bom") == RoomCondition.GOOD
        assert estimator._map_condition("razoavel") == RoomCondition.FAIR
        assert estimator._map_condition("razoável") == RoomCondition.FAIR
        assert estimator._map_condition("mau") == RoomCondition.POOR

    def test_english_conditions(self, estimator: RenovationEstimatorService):
        assert estimator._map_condition("excellent") == RoomCondition.EXCELLENT
        assert estimator._map_condition("good") == RoomCondition.GOOD
        assert estimator._map_condition("fair") == RoomCondition.FAIR
        assert estimator._map_condition("poor") == RoomCondition.POOR
        assert estimator._map_condition("needs_full_renovation") == RoomCondition.NEEDS_FULL_RENOVATION

    def test_unknown_defaults_to_fair(self, estimator: RenovationEstimatorService):
        assert estimator._map_condition("unknown_state") == RoomCondition.FAIR
        assert estimator._map_condition("") == RoomCondition.FAIR

    def test_case_insensitive(self, estimator: RenovationEstimatorService):
        assert estimator._map_condition("EXCELENTE") == RoomCondition.EXCELLENT
        assert estimator._map_condition("BOM") == RoomCondition.GOOD


# ---------------------------------------------------------------------------
# TestGenerateSummary
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    """Tests for RenovationEstimatorService.generate_summary()."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_stripped_text(
        self, estimator: RenovationEstimatorService, sample_room_analysis
    ):
        """Valid response returns the stripped content string."""
        mock_resp = _make_mock_response(content="  Resumo da estimativa.  ")

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await estimator.generate_summary(None, [sample_room_analysis], 1000, 5000)

        assert result == "Resumo da estimativa."

    @pytest.mark.asyncio
    async def test_null_content_returns_hardcoded_fallback(
        self, estimator: RenovationEstimatorService, sample_room_analysis
    ):
        """Null content triggers the hardcoded fallback summary."""
        mock_resp = _make_mock_response(content=None)

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await estimator.generate_summary(None, [sample_room_analysis], 1000, 5000)

        assert "1.000" in result or "1,000" in result  # min total appears
        assert "5.000" in result or "5,000" in result  # max total appears

    @pytest.mark.asyncio
    async def test_refusal_returns_hardcoded_fallback(
        self, estimator: RenovationEstimatorService, sample_room_analysis
    ):
        """Refusal response triggers the hardcoded fallback summary."""
        mock_resp = _make_mock_response(refusal="Cannot summarise this content")

        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await estimator.generate_summary(None, [sample_room_analysis], 2000, 8000)

        assert "2.000" in result or "2,000" in result
        assert "8.000" in result or "8,000" in result

    @pytest.mark.asyncio
    async def test_api_error_returns_hardcoded_fallback(
        self, estimator: RenovationEstimatorService, sample_room_analysis
    ):
        """Any exception falls back to the hardcoded summary string."""
        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit"),
        ):
            result = await estimator.generate_summary(None, [sample_room_analysis], 500, 1500)

        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestAnalyzeFloorPlan
# ---------------------------------------------------------------------------


def _floor_plan_response_json(
    ideas: list[dict] | None = None,
    property_context: str = "T2 com 75m², layout tradicional",
    confidence: float = 0.8,
) -> str:
    if ideas is None:
        ideas = [
            {
                "title": "Abrir cozinha para a sala",
                "description": "Remover parede entre cozinha e sala para conceito open-plan.",
                "potential_impact": "Maior luminosidade e sensação de espaço",
                "estimated_complexity": "media",
            }
        ]
    return json.dumps(
        {"ideas": ideas, "property_context": property_context, "confidence": confidence}
    )


class TestAnalyzeFloorPlan:
    """Tests for RenovationEstimatorService.analyze_floor_plan()."""

    @pytest.mark.asyncio
    async def test_returns_floor_plan_analysis_with_ideas(
        self, estimator: RenovationEstimatorService
    ):
        """Valid JSON response is parsed into a FloorPlanAnalysis with ideas."""
        mock_resp = _make_mock_response(content=_floor_plan_response_json())

        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_floor_plan(["http://img/planta.jpg"])

        assert isinstance(result, FloorPlanAnalysis)
        assert len(result.ideas) == 1
        assert result.ideas[0].title == "Abrir cozinha para a sala"
        assert result.ideas[0].estimated_complexity == "media"
        assert result.confidence == 0.8
        assert result.images == ["http://img/planta.jpg"]

    @pytest.mark.asyncio
    async def test_failure_returns_none(self, estimator: RenovationEstimatorService):
        """Any exception during floor plan analysis returns None gracefully."""
        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await estimator.analyze_floor_plan(["http://img/planta.jpg"])

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_urls_returns_none(self, estimator: RenovationEstimatorService):
        """Empty image list returns None without making any API call."""
        with patch.object(
            estimator.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            result = await estimator.analyze_floor_plan([])

        mock_create.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_refusal_returns_none(self, estimator: RenovationEstimatorService):
        """OpenAI refusal returns None without crashing."""
        mock_resp = _make_mock_response(refusal="Cannot analyse this content")

        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_floor_plan(["http://img/planta.jpg"])

        assert result is None

    @pytest.mark.asyncio
    async def test_null_content_returns_none(self, estimator: RenovationEstimatorService):
        """Null content response returns None gracefully."""
        mock_resp = _make_mock_response(content=None)

        with patch.object(
            estimator.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await estimator.analyze_floor_plan(["http://img/planta.jpg"])

        assert result is None

    @pytest.mark.asyncio
    async def test_property_context_included_in_prompt(
        self, estimator: RenovationEstimatorService
    ):
        """When property_data is provided, context is included in the API request."""
        from app.models.property import PropertyData

        mock_resp = _make_mock_response(content=_floor_plan_response_json())
        captured: list[dict] = []

        async def _capture(**kwargs):
            captured.append(kwargs)
            return mock_resp

        property_data = PropertyData(
            url="https://www.idealista.pt/imovel/12345678/",
            num_rooms=2,
            area_m2=75.0,
            price=185000.0,
        )

        with patch.object(
            estimator.client.chat.completions, "create", side_effect=_capture
        ):
            await estimator.analyze_floor_plan(
                ["http://img/planta.jpg"], property_data=property_data
            )

        assert len(captured) == 1
        content = captured[0]["messages"][0]["content"]
        text_block = next(b for b in content if b["type"] == "text")
        assert "T2" in text_block["text"]
        assert "75" in text_block["text"]
