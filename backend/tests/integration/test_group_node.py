"""
Integration tests for group_node in main_graph.py.

Tests the group_node in isolation by mocking ImageClassifierService.group_by_room.
Verifies: state flows correctly, exterior/other images are filtered, stream events
are emitted, and grouped_images has the expected structure.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.graphs.main_graph import group_node
from app.models.property import ImageClassification, PropertyData, RoomType
from app.services.image_classifier import ImageClassifierService


@pytest.fixture
def classifier() -> ImageClassifierService:
    return ImageClassifierService(openai_api_key="sk-fake-key")


@pytest.fixture
def base_state(sample_property_data: PropertyData) -> dict:
    """Minimal graph state after classify_node."""
    return {
        "url": sample_property_data.url,
        "property_data": sample_property_data,
        "image_urls": sample_property_data.image_urls,
        "classifications": [
            ImageClassification(
                image_url="http://img/kitchen.jpg",
                room_type=RoomType.KITCHEN,
                room_number=1,
                confidence=0.9,
            ),
            ImageClassification(
                image_url="http://img/bedroom.jpg",
                room_type=RoomType.BEDROOM,
                room_number=1,
                confidence=0.85,
            ),
            ImageClassification(
                image_url="http://img/exterior.jpg",
                room_type=RoomType.EXTERIOR,
                room_number=1,
                confidence=0.95,
            ),
            ImageClassification(
                image_url="http://img/other.jpg",
                room_type=RoomType.OTHER,
                room_number=1,
                confidence=0.5,
            ),
        ],
        "stream_events": [],
        "current_step": "classified",
    }


@pytest.mark.asyncio
async def test_group_node_calls_async_group_by_room(
    classifier: ImageClassifierService, base_state: dict
):
    """group_node must call the async group_by_room (not the old sync version)."""
    fake_grouped = {
        "cozinha_1": [base_state["classifications"][0]],
        "quarto_1": [base_state["classifications"][1]],
        "exterior_1": [base_state["classifications"][2]],
        "outro_1": [base_state["classifications"][3]],
    }

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock, return_value=fake_grouped
    ) as mock_group:
        await group_node(base_state, classifier_service=classifier)

    mock_group.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_node_filters_exterior_and_other(
    classifier: ImageClassifierService, base_state: dict
):
    """exterior and outro room types must be excluded from grouped_images."""
    fake_grouped = {
        "cozinha_1": [base_state["classifications"][0]],
        "quarto_1": [base_state["classifications"][1]],
        "exterior_1": [base_state["classifications"][2]],
        "outro_1": [base_state["classifications"][3]],
    }

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock, return_value=fake_grouped
    ):
        result = await group_node(base_state, classifier_service=classifier)

    grouped = result["grouped_images"]
    assert "exterior_1" not in grouped
    assert "outro_1" not in grouped
    assert "cozinha_1" in grouped
    assert "quarto_1" in grouped


@pytest.mark.asyncio
async def test_group_node_emits_stream_events(
    classifier: ImageClassifierService, base_state: dict
):
    """group_node must append at least two stream events (status + summary)."""
    fake_grouped = {
        "cozinha_1": [base_state["classifications"][0]],
        "quarto_1": [base_state["classifications"][1]],
    }

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock, return_value=fake_grouped
    ):
        result = await group_node(base_state, classifier_service=classifier)

    events = result["stream_events"]
    assert len(events) >= 2
    event_types = [e.type for e in events]
    assert "status" in event_types


@pytest.mark.asyncio
async def test_group_node_passes_num_rooms_and_bathrooms(
    classifier: ImageClassifierService, base_state: dict
):
    """group_node must forward num_rooms and num_bathrooms from property_data."""
    fake_grouped = {"cozinha_1": [base_state["classifications"][0]]}

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock, return_value=fake_grouped
    ) as mock_group:
        await group_node(base_state, classifier_service=classifier)

    call_kwargs = mock_group.call_args.kwargs
    assert call_kwargs.get("num_rooms") == base_state["property_data"].num_rooms
    assert call_kwargs.get("num_bathrooms") == base_state["property_data"].num_bathrooms


@pytest.mark.asyncio
async def test_group_node_grouped_images_structure(
    classifier: ImageClassifierService, base_state: dict
):
    """grouped_images values must be JSON-serialisable dicts with required keys."""
    fake_grouped = {
        "cozinha_1": [base_state["classifications"][0]],
    }

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock, return_value=fake_grouped
    ):
        result = await group_node(base_state, classifier_service=classifier)

    kitchen_data = result["grouped_images"]["cozinha_1"]
    assert len(kitchen_data) == 1
    item = kitchen_data[0]
    assert "image_url" in item
    assert "room_type" in item
    assert "room_number" in item
    assert "confidence" in item


@pytest.mark.asyncio
async def test_group_node_skips_on_error_state(
    classifier: ImageClassifierService, base_state: dict
):
    """If state already has an error, group_node must return immediately without calling GPT."""
    error_state = {**base_state, "error": "previous step failed"}

    with patch.object(
        classifier, "group_by_room", new_callable=AsyncMock
    ) as mock_group:
        result = await group_node(error_state, classifier_service=classifier)

    mock_group.assert_not_called()
    assert result is error_state
