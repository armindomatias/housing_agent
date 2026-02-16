"""
Tests for the ImageClassifier service — pure logic only (no OpenAI calls).

Tests _map_room_type(), group_by_room(), and get_room_label() methods.
"""

import pytest

from app.models.property import ImageClassification, RoomType
from app.services.image_classifier import ImageClassifierService


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
    """Tests for ImageClassifierService.get_room_label()."""

    def test_kitchen_label(self, classifier: ImageClassifierService):
        assert classifier.get_room_label(RoomType.KITCHEN, 1) == "Cozinha"

    def test_bedroom_with_number(self, classifier: ImageClassifierService):
        assert classifier.get_room_label(RoomType.BEDROOM, 1) == "Quarto 1"
        assert classifier.get_room_label(RoomType.BEDROOM, 2) == "Quarto 2"

    def test_bathroom_with_number(self, classifier: ImageClassifierService):
        assert classifier.get_room_label(RoomType.BATHROOM, 1) == "Casa de Banho 1"

    def test_living_room_no_number(self, classifier: ImageClassifierService):
        assert classifier.get_room_label(RoomType.LIVING_ROOM, 1) == "Sala"

    def test_hallway_no_number(self, classifier: ImageClassifierService):
        assert classifier.get_room_label(RoomType.HALLWAY, 1) == "Corredor"
