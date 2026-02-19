"""
Tests for the ImageClassifier service — pure logic only (no OpenAI calls).

Covers _map_room_type(), group_by_room_simple(), group_by_room() (async),
cluster_room_images(), _validate_clusters(), _metadata_fallback(),
the standalone get_room_label() function, classify_from_tag(), and
classify_images() tag/GPT routing.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.property import ImageClassification, RoomCluster, RoomType
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
    """Tests for ImageClassifierService.group_by_room_simple() (naive key-based grouping)."""

    def test_groups_same_room(self, classifier: ImageClassifierService):
        classifications = [
            ImageClassification(
                image_url="img1.jpg", room_type=RoomType.KITCHEN, room_number=1, confidence=0.9
            ),
            ImageClassification(
                image_url="img2.jpg", room_type=RoomType.KITCHEN, room_number=1, confidence=0.85
            ),
        ]
        grouped = classifier.group_by_room_simple(classifications)
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
        grouped = classifier.group_by_room_simple(classifications)
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
        grouped = classifier.group_by_room_simple(classifications)
        assert "quarto_1" in grouped
        assert "quarto_2" in grouped

    def test_empty_list(self, classifier: ImageClassifierService):
        grouped = classifier.group_by_room_simple([])
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


class TestValidateClusters:
    """Tests for ImageClassifierService._validate_clusters()."""

    def test_valid_clusters_pass_through(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[0, 2], confidence=0.9, visual_cues=""),
            RoomCluster(room_number=2, image_indices=[1], confidence=0.8, visual_cues=""),
        ]
        result = classifier._validate_clusters(clusters, 3)
        assert result is not None
        assert len(result) == 2
        # All indices covered
        all_indices = {i for c in result for i in c.image_indices}
        assert all_indices == {0, 1, 2}

    def test_duplicate_index_returns_none(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[0, 1], confidence=0.9, visual_cues=""),
            RoomCluster(room_number=2, image_indices=[1, 2], confidence=0.8, visual_cues=""),
        ]
        assert classifier._validate_clusters(clusters, 3) is None

    def test_out_of_range_index_returns_none(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[0, 5], confidence=0.9, visual_cues=""),
        ]
        assert classifier._validate_clusters(clusters, 3) is None

    def test_missing_images_appended_as_singletons(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[0], confidence=0.9, visual_cues=""),
            # images 1 and 2 are missing
        ]
        result = classifier._validate_clusters(clusters, 3)
        assert result is not None
        assert len(result) == 3
        all_indices = {i for c in result for i in c.image_indices}
        assert all_indices == {0, 1, 2}

    def test_empty_clusters_returns_none(self, classifier: ImageClassifierService):
        assert classifier._validate_clusters([], 3) is None

    def test_room_numbers_resequenced(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=5, image_indices=[0], confidence=0.9, visual_cues=""),
            RoomCluster(room_number=10, image_indices=[1], confidence=0.8, visual_cues=""),
        ]
        result = classifier._validate_clusters(clusters, 2)
        assert result is not None
        numbers = [c.room_number for c in result]
        assert numbers == [1, 2]

    def test_single_cluster_covering_all_images(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[0, 1, 2], confidence=0.7, visual_cues=""),
        ]
        result = classifier._validate_clusters(clusters, 3)
        assert result is not None
        assert len(result) == 1
        assert result[0].image_indices == [0, 1, 2]

    def test_negative_index_returns_none(self, classifier: ImageClassifierService):
        clusters = [
            RoomCluster(room_number=1, image_indices=[-1, 0], confidence=0.9, visual_cues=""),
        ]
        assert classifier._validate_clusters(clusters, 2) is None


class TestMetadataFallback:
    """Tests for ImageClassifierService._metadata_fallback()."""

    def test_even_distribution(self):
        result = ImageClassifierService._metadata_fallback(6, 2)
        assert len(result) == 2
        assert len(result[0].image_indices) == 3
        assert len(result[1].image_indices) == 3
        # All indices covered exactly once
        all_indices = {i for c in result for i in c.image_indices}
        assert all_indices == set(range(6))

    def test_uneven_distribution(self):
        result = ImageClassifierService._metadata_fallback(7, 3)
        assert len(result) == 3
        sizes = sorted([len(c.image_indices) for c in result], reverse=True)
        assert sizes == [3, 2, 2]
        all_indices = {i for c in result for i in c.image_indices}
        assert all_indices == set(range(7))

    def test_no_expected_rooms_one_per_image(self):
        result = ImageClassifierService._metadata_fallback(5, None)
        assert len(result) == 5
        for i, cluster in enumerate(result):
            assert cluster.image_indices == [i]

    def test_zero_images_returns_empty(self):
        result = ImageClassifierService._metadata_fallback(0, 2)
        assert result == []

    def test_confidence_is_low_for_fallback(self):
        result = ImageClassifierService._metadata_fallback(4, 2)
        for cluster in result:
            assert cluster.confidence == 0.3


class TestClusterRoomImages:
    """Tests for ImageClassifierService.cluster_room_images() (mocked OpenAI)."""

    @pytest.mark.asyncio
    async def test_single_image_no_api_call(self, classifier: ImageClassifierService):
        """Single image should return a single cluster without any API call."""
        with patch.object(classifier, "client") as mock_client:
            result = await classifier.cluster_room_images(
                RoomType.BEDROOM, ["http://img/bed1.jpg"]
            )

        mock_client.chat.completions.create.assert_not_called()
        assert len(result) == 1
        assert result[0].image_indices == [0]
        assert result[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_multiple_images_calls_gpt_and_parses_clusters(
        self, classifier: ImageClassifierService
    ):
        """Multiple images should trigger a GPT call and return parsed clusters."""
        gpt_response_json = """{
            "clusters": [
                {"room_number": 1, "image_indices": [0, 2], "confidence": 0.85, "visual_cues": "Same bed"},
                {"room_number": 2, "image_indices": [1], "confidence": 0.75, "visual_cues": "Different floor"}
            ],
            "total_rooms": 2,
            "reasoning": "Two distinct rooms"
        }"""

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = gpt_response_json
        mock_response.choices[0].message.refusal = None  # Explicit: no refusal

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await classifier.cluster_room_images(
                RoomType.BEDROOM,
                ["http://img/1.jpg", "http://img/2.jpg", "http://img/3.jpg"],
            )

        assert len(result) == 2
        assert result[0].image_indices == [0, 2]
        assert result[1].image_indices == [1]

    @pytest.mark.asyncio
    async def test_api_error_falls_back_to_single_group(
        self, classifier: ImageClassifierService
    ):
        """On API error, return a single cluster containing all images."""
        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            result = await classifier.cluster_room_images(
                RoomType.BEDROOM, ["http://img/1.jpg", "http://img/2.jpg"]
            )

        assert len(result) == 1
        assert result[0].image_indices == [0, 1]
        assert result[0].confidence == 0.3

    @pytest.mark.asyncio
    async def test_invalid_json_from_gpt_falls_back(self, classifier: ImageClassifierService):
        """Invalid JSON response should fall back to a single group."""
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "not valid json {"
        mock_response.choices[0].message.refusal = None  # Explicit: no refusal

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await classifier.cluster_room_images(
                RoomType.BATHROOM, ["http://img/1.jpg", "http://img/2.jpg"]
            )

        assert len(result) == 1
        assert result[0].confidence == 0.3

    @pytest.mark.asyncio
    async def test_valid_two_cluster_response(self, classifier: ImageClassifierService):
        """A valid 2-cluster response maps images to correct rooms."""
        gpt_response_json = """{
            "clusters": [
                {"room_number": 1, "image_indices": [0], "confidence": 0.9, "visual_cues": "Oak floor"},
                {"room_number": 2, "image_indices": [1, 2], "confidence": 0.8, "visual_cues": "Tile floor"}
            ],
            "total_rooms": 2,
            "reasoning": "Different flooring"
        }"""

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = gpt_response_json
        mock_response.choices[0].message.refusal = None  # Explicit: no refusal

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await classifier.cluster_room_images(
                RoomType.BEDROOM,
                ["http://img/1.jpg", "http://img/2.jpg", "http://img/3.jpg"],
            )

        assert len(result) == 2
        cluster_1 = next(c for c in result if c.room_number == 1)
        cluster_2 = next(c for c in result if c.room_number == 2)
        assert cluster_1.image_indices == [0]
        assert set(cluster_2.image_indices) == {1, 2}


class TestClassifySingleImageEdgeCases:
    """Tests for null content and refusal handling in classify_single_image()."""

    @pytest.mark.asyncio
    async def test_null_content_returns_other_with_zero_confidence(
        self, classifier: ImageClassifierService
    ):
        """Null message content must return OTHER/0.0 without crashing."""
        msg = AsyncMock()
        msg.content = None
        msg.refusal = None

        choice = AsyncMock()
        choice.message = msg
        choice.finish_reason = "stop"

        mock_resp = AsyncMock()
        mock_resp.choices = [choice]

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await classifier.classify_single_image("http://img/x.jpg")

        assert result.room_type == RoomType.OTHER
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_refusal_returns_other_with_zero_confidence(
        self, classifier: ImageClassifierService
    ):
        """OpenAI refusal must return OTHER/0.0 without retrying."""
        msg = AsyncMock()
        msg.content = None
        msg.refusal = "Content policy violation"

        choice = AsyncMock()
        choice.message = msg
        choice.finish_reason = "stop"

        mock_resp = AsyncMock()
        mock_resp.choices = [choice]

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_create:
            result = await classifier.classify_single_image("http://img/x.jpg")

        # Must not retry — only one API call
        mock_create.assert_awaited_once()
        assert result.room_type == RoomType.OTHER
        assert result.confidence == 0.0


class TestClusterRoomImagesEdgeCases:
    """Tests for null content and refusal handling in cluster_room_images()."""

    @pytest.mark.asyncio
    async def test_null_content_returns_single_cluster_fallback(
        self, classifier: ImageClassifierService
    ):
        """Null message content during clustering falls back to single cluster."""
        msg = AsyncMock()
        msg.content = None
        msg.refusal = None

        choice = AsyncMock()
        choice.message = msg
        choice.finish_reason = "stop"

        mock_resp = AsyncMock()
        mock_resp.choices = [choice]

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await classifier.cluster_room_images(
                RoomType.BEDROOM, ["http://img/1.jpg", "http://img/2.jpg"]
            )

        assert len(result) == 1
        assert result[0].image_indices == [0, 1]
        assert result[0].confidence == 0.3

    @pytest.mark.asyncio
    async def test_refusal_returns_single_cluster_fallback(
        self, classifier: ImageClassifierService
    ):
        """Refusal during clustering falls back to single cluster without retry."""
        msg = AsyncMock()
        msg.content = None
        msg.refusal = "Cannot cluster these images"

        choice = AsyncMock()
        choice.message = msg
        choice.finish_reason = "stop"

        mock_resp = AsyncMock()
        mock_resp.choices = [choice]

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_create:
            result = await classifier.cluster_room_images(
                RoomType.BATHROOM, ["http://img/1.jpg", "http://img/2.jpg", "http://img/3.jpg"]
            )

        mock_create.assert_awaited_once()
        assert len(result) == 1
        assert result[0].image_indices == [0, 1, 2]
        assert result[0].confidence == 0.3


class TestGroupByRoomAsync:
    """Tests for the async ImageClassifierService.group_by_room()."""

    def _make_classification(
        self,
        url: str,
        room_type: RoomType,
        room_number: int = 1,
        confidence: float = 0.9,
    ) -> ImageClassification:
        return ImageClassification(
            image_url=url,
            room_type=room_type,
            room_number=room_number,
            confidence=confidence,
        )

    @pytest.mark.asyncio
    async def test_singleton_types_skip_clustering(self, classifier: ImageClassifierService):
        """KITCHEN and LIVING_ROOM should go into room_number=1 without any API call."""
        classifications = [
            self._make_classification("k1.jpg", RoomType.KITCHEN),
            self._make_classification("k2.jpg", RoomType.KITCHEN),
            self._make_classification("s1.jpg", RoomType.LIVING_ROOM),
        ]

        with patch.object(
            classifier, "cluster_room_images", new_callable=AsyncMock
        ) as mock_cluster:
            grouped = await classifier.group_by_room(classifications)

        mock_cluster.assert_not_called()
        assert "cozinha_1" in grouped
        assert len(grouped["cozinha_1"]) == 2
        assert "sala_1" in grouped

    @pytest.mark.asyncio
    async def test_multi_room_types_trigger_clustering(self, classifier: ImageClassifierService):
        """BEDROOM bucket with >1 image must call cluster_room_images()."""
        classifications = [
            self._make_classification("b1.jpg", RoomType.BEDROOM),
            self._make_classification("b2.jpg", RoomType.BEDROOM),
            self._make_classification("b3.jpg", RoomType.BEDROOM),
        ]

        fake_clusters = [
            RoomCluster(room_number=1, image_indices=[0, 2], confidence=0.85, visual_cues=""),
            RoomCluster(room_number=2, image_indices=[1], confidence=0.75, visual_cues=""),
        ]

        with patch.object(
            classifier,
            "cluster_room_images",
            new_callable=AsyncMock,
            return_value=fake_clusters,
        ):
            grouped = await classifier.group_by_room(classifications, num_rooms=2)

        assert "quarto_1" in grouped
        assert "quarto_2" in grouped
        assert len(grouped["quarto_1"]) == 2
        assert len(grouped["quarto_2"]) == 1

    @pytest.mark.asyncio
    async def test_mixed_types_correct_routing(self, classifier: ImageClassifierService):
        """Bedroom clusters, kitchen does not."""
        classifications = [
            self._make_classification("k1.jpg", RoomType.KITCHEN),
            self._make_classification("b1.jpg", RoomType.BEDROOM),
            self._make_classification("b2.jpg", RoomType.BEDROOM),
        ]

        fake_clusters = [
            RoomCluster(room_number=1, image_indices=[0], confidence=0.8, visual_cues=""),
            RoomCluster(room_number=2, image_indices=[1], confidence=0.8, visual_cues=""),
        ]

        with patch.object(
            classifier,
            "cluster_room_images",
            new_callable=AsyncMock,
            return_value=fake_clusters,
        ) as mock_cluster:
            grouped = await classifier.group_by_room(classifications)

        # cluster_room_images called for bedrooms only
        mock_cluster.assert_called_once()
        assert "cozinha_1" in grouped
        assert "quarto_1" in grouped
        assert "quarto_2" in grouped

    @pytest.mark.asyncio
    async def test_clustering_failure_uses_metadata_fallback(
        self, classifier: ImageClassifierService
    ):
        """When cluster_room_images returns a single group (fallback), metadata fallback applies."""
        classifications = [
            self._make_classification("b1.jpg", RoomType.BEDROOM),
            self._make_classification("b2.jpg", RoomType.BEDROOM),
            self._make_classification("b3.jpg", RoomType.BEDROOM),
            self._make_classification("b4.jpg", RoomType.BEDROOM),
        ]

        # Simulate GPT returning invalid output → cluster_room_images single-group fallback
        single_cluster = [
            RoomCluster(room_number=1, image_indices=[0, 1, 2, 3], confidence=0.3, visual_cues="")
        ]

        with patch.object(
            classifier,
            "cluster_room_images",
            new_callable=AsyncMock,
            return_value=single_cluster,
        ):
            grouped = await classifier.group_by_room(classifications, num_rooms=2)

        # All images should be covered (either in one or two groups)
        all_images = {c.image_url for v in grouped.values() for c in v}
        assert all_images == {"b1.jpg", "b2.jpg", "b3.jpg", "b4.jpg"}

    @pytest.mark.asyncio
    async def test_empty_classifications_returns_empty(self, classifier: ImageClassifierService):
        grouped = await classifier.group_by_room([])
        assert grouped == {}

    @pytest.mark.asyncio
    async def test_single_bedroom_skips_clustering(self, classifier: ImageClassifierService):
        """A single image of a multi-room type should not trigger clustering."""
        classifications = [
            self._make_classification("b1.jpg", RoomType.BEDROOM),
        ]

        with patch.object(
            classifier, "cluster_room_images", new_callable=AsyncMock
        ) as mock_cluster:
            grouped = await classifier.group_by_room(classifications)

        mock_cluster.assert_not_called()
        assert "quarto_1" in grouped
