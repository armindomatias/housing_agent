"""
Tests for Pydantic models in app.models.property.

Validates model defaults, field constraints, and enum values.
"""

import pytest
from pydantic import ValidationError

from app.models.property import (
    ImageClassification,
    PropertyData,
    RenovationEstimate,
    RenovationItem,
    RoomAnalysis,
    RoomCondition,
    RoomType,
    StreamEvent,
)


class TestRoomType:
    """Tests for the RoomType enum."""

    def test_all_room_types_have_portuguese_values(self):
        expected_values = {
            "cozinha", "sala", "quarto", "casa_de_banho", "corredor",
            "varanda", "exterior", "garagem", "arrecadacao", "outro",
        }
        actual_values = {rt.value for rt in RoomType}
        assert actual_values == expected_values

    def test_room_type_count(self):
        assert len(RoomType) == 10


class TestRoomCondition:
    """Tests for the RoomCondition enum."""

    def test_all_conditions_exist(self):
        expected = {"excelente", "bom", "razoavel", "mau", "necessita_remodelacao_total"}
        actual = {rc.value for rc in RoomCondition}
        assert actual == expected


class TestImageClassification:
    """Tests for ImageClassification model."""

    def test_valid_classification(self):
        c = ImageClassification(
            image_url="https://example.com/img.jpg",
            room_type=RoomType.KITCHEN,
            confidence=0.85,
        )
        assert c.room_number == 1  # default
        assert c.confidence == 0.85

    def test_confidence_lower_bound(self):
        with pytest.raises(ValidationError):
            ImageClassification(
                image_url="https://example.com/img.jpg",
                room_type=RoomType.KITCHEN,
                confidence=-0.1,
            )

    def test_confidence_upper_bound(self):
        with pytest.raises(ValidationError):
            ImageClassification(
                image_url="https://example.com/img.jpg",
                room_type=RoomType.KITCHEN,
                confidence=1.1,
            )

    def test_confidence_boundary_values(self):
        low = ImageClassification(
            image_url="https://example.com/img.jpg",
            room_type=RoomType.OTHER,
            confidence=0.0,
        )
        high = ImageClassification(
            image_url="https://example.com/img.jpg",
            room_type=RoomType.OTHER,
            confidence=1.0,
        )
        assert low.confidence == 0.0
        assert high.confidence == 1.0


class TestPropertyData:
    """Tests for PropertyData model."""

    def test_defaults(self):
        pd = PropertyData(url="https://www.idealista.pt/imovel/123/")
        assert pd.title == ""
        assert pd.price == 0
        assert pd.area_m2 == 0
        assert pd.num_rooms == 0
        assert pd.num_bathrooms == 0
        assert pd.floor == ""
        assert pd.location == ""
        assert pd.description == ""
        assert pd.image_urls == []
        assert pd.raw_data == {}

    def test_new_fields_defaults(self):
        pd = PropertyData(url="https://www.idealista.pt/imovel/123/")
        assert pd.operation == ""
        assert pd.property_type == ""
        assert pd.latitude is None
        assert pd.longitude is None
        assert pd.image_tags == {}
        assert pd.has_elevator is None
        assert pd.condition_status == ""

    def test_full_property(self, sample_property_data: PropertyData):
        assert sample_property_data.price == 185000.0
        assert sample_property_data.num_rooms == 2
        assert len(sample_property_data.image_urls) == 3

    def test_full_property_with_new_fields(self):
        pd = PropertyData(
            url="https://www.idealista.pt/imovel/123/",
            title="Flat T3",
            price=300000.0,
            operation="sale",
            property_type="flat",
            latitude=38.75,
            longitude=-9.20,
            image_tags={"img1.jpg": "kitchen", "img2.jpg": "bedroom"},
            has_elevator=True,
            condition_status="good",
        )
        assert pd.operation == "sale"
        assert pd.property_type == "flat"
        assert pd.latitude == 38.75
        assert pd.longitude == -9.20
        assert pd.image_tags == {"img1.jpg": "kitchen", "img2.jpg": "bedroom"}
        assert pd.has_elevator is True
        assert pd.condition_status == "good"


class TestRenovationItem:
    """Tests for RenovationItem model."""

    def test_defaults(self):
        item = RenovationItem(item="Pintura", cost_min=200, cost_max=500)
        assert item.priority == "media"
        assert item.notes == ""

    def test_cost_min_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            RenovationItem(item="Pintura", cost_min=-100, cost_max=500)

    def test_cost_max_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            RenovationItem(item="Pintura", cost_min=0, cost_max=-1)


class TestRoomAnalysis:
    """Tests for RoomAnalysis model."""

    def test_room_analysis_with_items(self, sample_room_analysis: RoomAnalysis):
        assert sample_room_analysis.room_label == "Cozinha"
        assert sample_room_analysis.condition == RoomCondition.POOR
        assert len(sample_room_analysis.renovation_items) == 3
        assert sample_room_analysis.cost_min == 4100.0

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            RoomAnalysis(
                room_type=RoomType.KITCHEN,
                room_label="Cozinha",
                condition=RoomCondition.GOOD,
                cost_min=0,
                cost_max=0,
                confidence=1.5,
            )


class TestRenovationEstimate:
    """Tests for RenovationEstimate model."""

    def test_has_default_disclaimer(self):
        est = RenovationEstimate(
            property_url="https://www.idealista.pt/imovel/123/",
            total_cost_min=0,
            total_cost_max=0,
            overall_confidence=0.5,
        )
        assert "Rehabify" in est.disclaimer
        assert len(est.disclaimer) > 50

    def test_empty_room_analyses_by_default(self):
        est = RenovationEstimate(
            property_url="https://www.idealista.pt/imovel/123/",
            total_cost_min=0,
            total_cost_max=0,
            overall_confidence=0.5,
        )
        assert est.room_analyses == []
        assert est.property_data is None


class TestStreamEvent:
    """Tests for StreamEvent model."""

    def test_defaults(self):
        event = StreamEvent(type="status", message="Starting")
        assert event.step == 0
        assert event.total_steps == 5
        assert event.data is None

    def test_with_data(self):
        event = StreamEvent(type="result", message="Done", data={"key": "value"})
        assert event.data == {"key": "value"}
