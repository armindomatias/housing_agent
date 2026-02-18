"""
Tests for the ImageClassifier service — pure logic only (no OpenAI calls).

Tests _map_room_type(), group_by_room(), the standalone get_room_label() function,
and the Apify-tag optimisation (classify_from_tag / classify_images with tags).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.property import ImageClassification, RoomType
from app.services.image_classifier import (
    ImageClassifierService,
    classify_from_tag,
    get_room_label,
)


@pytest.fixture
def classifier() -> ImageClassifierService:
    """ImageClassifierService with a fake key (no real API calls)."""
    return ImageClassifierService(openai_api_key="sk-fake-key")


class TestMapRoomType:
    """Tests for ImageClassifierService._map_room_type()."""

    def test_maps_portuguese_kitchen(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("cozinha") == RoomType.KITCHEN

    def test_maps_english_kitchen(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("kitchen") == RoomType.KITCHEN

    def test_maps_living_room_variants(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("sala") == RoomType.LIVING_ROOM
        assert classifier._map_room_type("sala de estar") == RoomType.LIVING_ROOM
        assert classifier._map_room_type("living_room") == RoomType.LIVING_ROOM
        assert classifier._map_room_type("living room") == RoomType.LIVING_ROOM

    def test_maps_bathroom_variants(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("casa_de_banho") == RoomType.BATHROOM
        assert classifier._map_room_type("casa de banho") == RoomType.BATHROOM
        assert classifier._map_room_type("bathroom") == RoomType.BATHROOM
        assert classifier._map_room_type("wc") == RoomType.BATHROOM

    def test_maps_bedroom(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("quarto") == RoomType.BEDROOM
        assert classifier._map_room_type("bedroom") == RoomType.BEDROOM

    def test_maps_hallway(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("corredor") == RoomType.HALLWAY
        assert classifier._map_room_type("hall") == RoomType.HALLWAY

    def test_maps_balcony_and_terrace(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("varanda") == RoomType.BALCONY
        assert classifier._map_room_type("terraço") == RoomType.BALCONY
        assert classifier._map_room_type("terrace") == RoomType.BALCONY

    def test_maps_exterior(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("exterior") == RoomType.EXTERIOR
        assert classifier._map_room_type("fachada") == RoomType.EXTERIOR

    def test_maps_garage(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("garagem") == RoomType.GARAGE
        assert classifier._map_room_type("garage") == RoomType.GARAGE

    def test_maps_storage(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("arrecadacao") == RoomType.STORAGE
        assert classifier._map_room_type("despensa") == RoomType.STORAGE

    def test_unknown_defaults_to_other(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("unknown") == RoomType.OTHER
        assert classifier._map_room_type("xyz") == RoomType.OTHER

    def test_case_insensitive(self, classifier: ImageClassifierService):
        assert classifier._map_room_type("COZINHA") == RoomType.KITCHEN
        assert classifier._map_room_type("Sala") == RoomType.LIVING_ROOM


class TestGroupByRoom:
    """Tests for ImageClassifierService.group_by_room()."""

    def test_groups_same_room(self, classifier: ImageClassifierService):
        classifications = [
            ImageClassification(
                image_url="img1.jpg", room_type=RoomType.KITCHEN, room_number=1, confidence=0.9
            ),
            ImageClassification(
                image_url="img2.jpg", room_type=RoomType.KITCHEN, room_number=1, confidence=0.85
            ),
        ]
        grouped = classifier.group_by_room(classifications)
        assert "cozinha_1" in grouped
        assert len(grouped["cozinha_1"]) == 2

    def test_separates_different_rooms(self, classifier: ImageClassifierService):
        classifications = [
            ImageClassification(
                image_url="img1.jpg", room_type=RoomType.KITCHEN, room_number=1, confidence=0.9
            ),
            ImageClassification(
                image_url="img2.jpg", room_type=RoomType.BEDROOM, room_number=1, confidence=0.8
            ),
        ]
        grouped = classifier.group_by_room(classifications)
        assert len(grouped) == 2
        assert "cozinha_1" in grouped
        assert "quarto_1" in grouped

    def test_separates_same_type_different_numbers(self, classifier: ImageClassifierService):
        classifications = [
            ImageClassification(
                image_url="img1.jpg", room_type=RoomType.BEDROOM, room_number=1, confidence=0.9
            ),
            ImageClassification(
                image_url="img2.jpg", room_type=RoomType.BEDROOM, room_number=2, confidence=0.8
            ),
        ]
        grouped = classifier.group_by_room(classifications)
        assert "quarto_1" in grouped
        assert "quarto_2" in grouped

    def test_empty_list(self, classifier: ImageClassifierService):
        grouped = classifier.group_by_room([])
        assert grouped == {}


class TestGetRoomLabel:
    """Tests for the standalone get_room_label() function."""

    def test_kitchen_label(self):
        assert get_room_label(RoomType.KITCHEN, 1) == "Cozinha"

    def test_bedroom_with_number(self):
        assert get_room_label(RoomType.BEDROOM, 1) == "Quarto 1"
        assert get_room_label(RoomType.BEDROOM, 2) == "Quarto 2"

    def test_bathroom_with_number(self):
        assert get_room_label(RoomType.BATHROOM, 1) == "Casa de Banho 1"

    def test_living_room_no_number(self):
        assert get_room_label(RoomType.LIVING_ROOM, 1) == "Sala"

    def test_hallway_no_number(self):
        assert get_room_label(RoomType.HALLWAY, 1) == "Corredor"

    def test_all_room_types_return_string(self):
        for room_type in RoomType:
            label = get_room_label(room_type, 1)
            assert isinstance(label, str)
            assert len(label) > 0


class TestClassifyFromTag:
    """
    Tests for the standalone classify_from_tag() function (Branch 2).

    This function converts free Apify tag metadata into ImageClassification
    objects, saving GPT API calls for images that Idealista already labelled.
    """

    def test_known_tag_kitchen(self):
        result = classify_from_tag("http://img/1.jpg", "kitchen")
        assert result is not None
        assert result.room_type == RoomType.KITCHEN
        assert result.confidence == 0.9

    def test_known_tag_bedroom(self):
        result = classify_from_tag("http://img/2.jpg", "bedroom")
        assert result is not None
        assert result.room_type == RoomType.BEDROOM

    def test_known_tag_bathroom(self):
        result = classify_from_tag("http://img/3.jpg", "bathroom")
        assert result is not None
        assert result.room_type == RoomType.BATHROOM

    def test_known_tag_living_room_variants(self):
        """living_room, living-room and livingroom all map to LIVING_ROOM."""
        assert classify_from_tag("u", "living_room").room_type == RoomType.LIVING_ROOM
        assert classify_from_tag("u", "living-room").room_type == RoomType.LIVING_ROOM
        assert classify_from_tag("u", "livingroom").room_type == RoomType.LIVING_ROOM

    def test_known_tag_exterior(self):
        assert classify_from_tag("u", "exterior").room_type == RoomType.EXTERIOR

    def test_unknown_tag_returns_none(self):
        """Unknown tags must return None so callers fall back to GPT."""
        assert classify_from_tag("u", "unknown_room") is None
        assert classify_from_tag("u", "") is None
        assert classify_from_tag("u", "random") is None

    def test_case_insensitive_tag(self):
        """Tags are normalised to lowercase before lookup."""
        result = classify_from_tag("u", "Kitchen")
        assert result is not None
        assert result.room_type == RoomType.KITCHEN

    def test_room_number_is_always_one(self):
        """Apify tags carry no room-number info; default to 1."""
        result = classify_from_tag("u", "bedroom")
        assert result.room_number == 1

    def test_image_url_preserved(self):
        url = "https://img.idealista.pt/abc/photo.jpg"
        result = classify_from_tag(url, "kitchen")
        assert result.image_url == url


class TestClassifyImagesWithTags:
    """
    Tests for classify_images() when image_tags are provided (Branch 2).

    We mock classify_single_image to verify GPT is only called for images
    that are untagged or have an unknown tag.
    """

    @pytest.mark.asyncio
    async def test_tagged_images_skip_gpt(self, classifier: ImageClassifierService):
        """All images with known tags must NOT trigger a GPT call."""
        urls = ["http://img/kitchen.jpg", "http://img/bedroom.jpg"]
        tags = {"http://img/kitchen.jpg": "kitchen", "http://img/bedroom.jpg": "bedroom"}

        with patch.object(classifier, "classify_single_image", new_callable=AsyncMock) as mock_gpt:
            results = await classifier.classify_images(urls, image_tags=tags)

        mock_gpt.assert_not_called()
        assert len(results) == 2
        room_types = {r.room_type for r in results}
        assert RoomType.KITCHEN in room_types
        assert RoomType.BEDROOM in room_types

    @pytest.mark.asyncio
    async def test_untagged_images_go_to_gpt(self, classifier: ImageClassifierService):
        """Images with no tag entry must be sent to GPT."""
        urls = ["http://img/mystery.jpg"]
        tags: dict[str, str] = {}  # no tags at all

        gpt_result = ImageClassification(
            image_url=urls[0], room_type=RoomType.LIVING_ROOM, room_number=1, confidence=0.8
        )

        with patch.object(
            classifier, "classify_single_image", new_callable=AsyncMock, return_value=gpt_result
        ) as mock_gpt:
            results = await classifier.classify_images(urls, image_tags=tags)

        mock_gpt.assert_called_once_with(urls[0])
        assert results[0].room_type == RoomType.LIVING_ROOM

    @pytest.mark.asyncio
    async def test_unknown_tag_falls_back_to_gpt(self, classifier: ImageClassifierService):
        """Images with a tag that is not in _APIFY_TAG_MAP must go to GPT."""
        urls = ["http://img/photo.jpg"]
        tags = {"http://img/photo.jpg": "some_unknown_tag"}

        gpt_result = ImageClassification(
            image_url=urls[0], room_type=RoomType.OTHER, room_number=1, confidence=0.5
        )

        with patch.object(
            classifier, "classify_single_image", new_callable=AsyncMock, return_value=gpt_result
        ) as mock_gpt:
            results = await classifier.classify_images(urls, image_tags=tags)

        mock_gpt.assert_called_once()
        assert results[0].room_type == RoomType.OTHER

    @pytest.mark.asyncio
    async def test_mixed_tagged_and_untagged(self, classifier: ImageClassifierService):
        """Tagged images skip GPT, untagged images are sent to GPT."""
        tagged_url = "http://img/kitchen.jpg"
        untagged_url = "http://img/mystery.jpg"
        urls = [tagged_url, untagged_url]
        tags = {tagged_url: "kitchen"}  # mystery.jpg has no tag

        gpt_result = ImageClassification(
            image_url=untagged_url, room_type=RoomType.HALLWAY, room_number=1, confidence=0.7
        )

        with patch.object(
            classifier, "classify_single_image", new_callable=AsyncMock, return_value=gpt_result
        ) as mock_gpt:
            results = await classifier.classify_images(urls, image_tags=tags)

        # GPT called exactly once (for the untagged image only)
        mock_gpt.assert_called_once_with(untagged_url)
        assert len(results) == 2
        room_types = {r.room_type for r in results}
        assert RoomType.KITCHEN in room_types
        assert RoomType.HALLWAY in room_types

    @pytest.mark.asyncio
    async def test_no_tags_all_go_to_gpt(self, classifier: ImageClassifierService):
        """When image_tags=None, original behaviour — all images go to GPT."""
        urls = ["http://img/a.jpg", "http://img/b.jpg"]

        gpt_result = ImageClassification(
            image_url="", room_type=RoomType.OTHER, room_number=1, confidence=0.5
        )

        with patch.object(
            classifier, "classify_single_image", new_callable=AsyncMock, return_value=gpt_result
        ) as mock_gpt:
            await classifier.classify_images(urls, image_tags=None)

        assert mock_gpt.call_count == 2

    @pytest.mark.asyncio
    async def test_progress_callback_called_for_all_images(
        self, classifier: ImageClassifierService
    ):
        """Progress callback must fire for every image, tagged or not."""
        tagged_url = "http://img/kitchen.jpg"
        untagged_url = "http://img/mystery.jpg"
        urls = [tagged_url, untagged_url]
        tags = {tagged_url: "kitchen"}

        gpt_result = ImageClassification(
            image_url=untagged_url, room_type=RoomType.OTHER, room_number=1, confidence=0.5
        )

        calls: list[tuple] = []

        async def progress_callback(current, total, classification):
            calls.append((current, total))

        with patch.object(
            classifier, "classify_single_image", new_callable=AsyncMock, return_value=gpt_result
        ):
            await classifier.classify_images(urls, image_tags=tags, progress_callback=progress_callback)

        # Callback must have been called twice (once per image)
        assert len(calls) == 2
        # total is always the full list length
        assert all(total == 2 for _, total in calls)
