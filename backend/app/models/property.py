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
    FLOOR_PLAN = "planta"
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


class RoomCluster(BaseModel):
    """Result of clustering photos of the same room type into physical rooms."""

    room_number: int = Field(ge=1, description="Sequential room number within this type")
    image_indices: list[int] = Field(description="0-based indices into the input image list")
    confidence: float = Field(ge=0.0, le=1.0, description="Clustering confidence")
    visual_cues: str = Field(default="", description="Visual cues used for clustering")


class ClusteringResult(BaseModel):
    """GPT response for room clustering."""

    clusters: list[RoomCluster] = Field(description="List of room clusters")
    total_rooms: int = Field(ge=1, description="Total number of distinct rooms found")
    reasoning: str = Field(default="", description="Overall reasoning")


class FloorPlanIdea(BaseModel):
    """A single layout optimisation idea derived from a floor plan image."""

    title: str = Field(description="Short descriptive title, e.g. 'Abrir cozinha para a sala'")
    description: str = Field(description="Detailed explanation of the idea (2-3 sentences)")
    potential_impact: str = Field(
        description="Expected impact, e.g. 'Maior luminosidade e sensação de espaço'"
    )
    estimated_complexity: str = Field(
        description="Estimated complexity: 'baixa', 'media', or 'alta'"
    )


class FloorPlanAnalysis(BaseModel):
    """Result of analysing floor plan image(s) for layout optimisation ideas."""

    images: list[str] = Field(
        default_factory=list, description="URLs of floor plan images analysed"
    )
    ideas: list[FloorPlanIdea] = Field(
        default_factory=list, description="Layout optimisation ideas"
    )
    property_context: str = Field(
        default="", description="Brief description of current layout, e.g. 'T2 com 75m²'"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence based on quality/clarity of the floor plan"
    )


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
    # New fields (feature extraction — typed as Any to avoid circular import at model definition time)
    features: Any | None = Field(
        default=None, description="Structured features extracted from room photos (RoomFeatures)"
    )
    cost_breakdown: Any | None = Field(
        default=None, description="Materials vs labor cost breakdown (CostBreakdown)"
    )


class PropertyData(BaseModel):
    """Scraped property data from Idealista."""

    url: str = Field(description="Idealista listing URL")
    title: str = Field(default="", description="Listing title")
    price: float = Field(default=0, description="Asking price in EUR")
    area_m2: float = Field(default=0, description="Constructed area in square meters")
    usable_area_m2: float = Field(default=0, description="Usable area in square meters")
    num_rooms: int = Field(default=0, description="Number of rooms")
    num_bathrooms: int = Field(default=0, description="Number of bathrooms")
    floor: str = Field(default="", description="Floor number")
    location: str = Field(default="", description="Property location")
    description: str = Field(default="", description="Listing description")
    image_urls: list[str] = Field(default_factory=list, description="List of image URLs")
    operation: str = Field(default="", description="Listing type: sale or rent")
    property_type: str = Field(default="", description="Property type: flat, house, etc.")
    latitude: float | None = Field(default=None, description="Property latitude")
    longitude: float | None = Field(default=None, description="Property longitude")
    image_tags: dict[str, str] = Field(
        default_factory=dict, description="Map of image URL to room tag from Idealista"
    )
    has_elevator: bool | None = Field(default=None, description="Building has elevator")
    condition_status: str = Field(default="", description="Property condition: good, bad, or unknown")

    # Additional property features
    energy_certificate: str = Field(default="", description="Energy efficiency rating (A+ to F)")
    has_swimming_pool: bool = Field(default=False, description="Property has swimming pool")
    has_garden: bool = Field(default=False, description="Property has garden")
    has_boxroom: bool = Field(default=False, description="Property has storage/boxroom")
    is_duplex: bool = Field(default=False, description="Property is a duplex")
    is_penthouse: bool = Field(default=False, description="Property is a penthouse")
    is_studio: bool = Field(default=False, description="Property is a studio")
    furniture_status: str = Field(default="", description="Furniture status: furnished, unfurnished, unknown")
    orientation: str = Field(default="", description="Building orientation (north, south, east, west)")
    price_per_m2: float = Field(default=0, description="Price per square meter in EUR")

    # Rich media
    videos: list[dict[str, Any]] = Field(default_factory=list, description="Property video URLs and metadata")
    virtual_tours: list[dict[str, Any]] = Field(default_factory=list, description="3D tour links (Matterport, etc.)")

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
    floor_plan_ideas: FloorPlanAnalysis | None = Field(
        default=None, description="Layout optimisation ideas from floor plan analysis"
    )
    # New fields (feature extraction — typed as Any to avoid circular import)
    composite_indices: Any | None = Field(
        default=None, description="Composite indices (work scope, time, risk, complexity)"
    )
    user_preferences: Any | None = Field(
        default=None, description="User preferences applied to this estimate"
    )
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
