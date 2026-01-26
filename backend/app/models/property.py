"""
Data models for property analysis.
These models define the structure for property data, room analysis, and renovation estimates.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RoomType(str, Enum):
    """Types of rooms that can be identified in a property."""

    KITCHEN = "cozinha"
    LIVING_ROOM = "sala"
    BEDROOM = "quarto"
    BATHROOM = "casa_de_banho"
    HALLWAY = "corredor"
    BALCONY = "varanda"
    EXTERIOR = "exterior"
    GARAGE = "garagem"
    STORAGE = "arrecadacao"
    OTHER = "outro"


class RoomCondition(str, Enum):
    """Condition levels for room assessment."""

    EXCELLENT = "excelente"
    GOOD = "bom"
    FAIR = "razoavel"
    POOR = "mau"
    NEEDS_FULL_RENOVATION = "necessita_remodelacao_total"


class ImageClassification(BaseModel):
    """Result of classifying a single property image."""

    image_url: str = Field(description="URL of the analyzed image")
    room_type: RoomType = Field(description="Type of room identified")
    room_number: int = Field(default=1, description="Room number for multiple rooms of same type")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence score")


class RenovationItem(BaseModel):
    """A specific renovation item/task for a room."""

    item: str = Field(description="Description of the renovation item")
    cost_min: float = Field(ge=0, description="Minimum estimated cost in EUR")
    cost_max: float = Field(ge=0, description="Maximum estimated cost in EUR")
    priority: str = Field(default="media", description="Priority: alta, media, baixa")
    notes: str = Field(default="", description="Additional notes")


class RoomAnalysis(BaseModel):
    """Complete analysis of a single room including renovation estimates."""

    room_type: RoomType = Field(description="Type of room")
    room_number: int = Field(default=1, description="Room number")
    room_label: str = Field(description="Human-readable room label, e.g., 'Cozinha', 'Quarto 1'")
    images: list[str] = Field(default_factory=list, description="URLs of images for this room")
    condition: RoomCondition = Field(description="Overall condition assessment")
    condition_notes: str = Field(default="", description="Description of current condition")
    renovation_items: list[RenovationItem] = Field(
        default_factory=list, description="List of recommended renovations"
    )
    cost_min: float = Field(ge=0, description="Total minimum cost for this room")
    cost_max: float = Field(ge=0, description="Total maximum cost for this room")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in estimate (higher with more photos)"
    )


class PropertyData(BaseModel):
    """Scraped property data from Idealista."""

    url: str = Field(description="Idealista listing URL")
    title: str = Field(default="", description="Listing title")
    price: float = Field(default=0, description="Asking price in EUR")
    area_m2: float = Field(default=0, description="Property area in square meters")
    num_rooms: int = Field(default=0, description="Number of rooms")
    num_bathrooms: int = Field(default=0, description="Number of bathrooms")
    floor: str = Field(default="", description="Floor number")
    location: str = Field(default="", description="Property location")
    description: str = Field(default="", description="Listing description")
    image_urls: list[str] = Field(default_factory=list, description="List of image URLs")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="Raw scraped data")


class RenovationEstimate(BaseModel):
    """Complete renovation estimate for a property."""

    property_url: str = Field(description="Idealista listing URL")
    property_data: PropertyData | None = Field(default=None, description="Scraped property data")
    room_analyses: list[RoomAnalysis] = Field(
        default_factory=list, description="Analysis per room"
    )
    total_cost_min: float = Field(ge=0, description="Total minimum renovation cost")
    total_cost_max: float = Field(ge=0, description="Total maximum renovation cost")
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in estimate"
    )
    summary: str = Field(default="", description="Summary of renovation needs")
    disclaimer: str = Field(
        default=(
            "A Rehabify fornece estimativas indicativas baseadas em análise automatizada. "
            "Para decisões de investimento, consulte um advogado, contabilista ou perito "
            "em obras qualificado. Os valores apresentados podem variar significativamente "
            "da realidade."
        ),
        description="Legal disclaimer",
    )


class StreamEvent(BaseModel):
    """Event sent during streaming analysis."""

    type: str = Field(description="Event type: status, progress, error, result")
    message: str = Field(default="", description="Human-readable message")
    step: int = Field(default=0, description="Current step number")
    total_steps: int = Field(default=5, description="Total number of steps")
    data: dict[str, Any] | None = Field(default=None, description="Additional event data")
