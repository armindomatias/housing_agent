"""
LangGraph state definitions.

This file defines the state that flows through the renovation estimation graph.
The state accumulates data as it passes through each node:
scrape -> classify -> group -> estimate -> summarize

Each node reads what it needs from state and adds its results.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.models.property import (
    ImageClassification,
    PropertyData,
    RenovationEstimate,
    RoomAnalysis,
    StreamEvent,
)


class PropertyState(BaseModel):
    """
    State that flows through the LangGraph pipeline.

    This state is passed between nodes and accumulates results at each step.
    Using Pydantic for validation and type safety.
    """

    # === INPUT ===
    # These are provided when starting the graph
    url: str = Field(description="Idealista listing URL to analyze")
    user_id: str = Field(default="", description="User ID for tracking (optional)")

    # === SCRAPING RESULTS ===
    # Filled by the 'scrape' node
    property_data: PropertyData | None = Field(
        default=None, description="Scraped property data from Idealista"
    )
    image_urls: list[str] = Field(
        default_factory=list, description="List of image URLs from the listing"
    )

    # === CLASSIFICATION RESULTS ===
    # Filled by the 'classify' node
    classifications: list[ImageClassification] = Field(
        default_factory=list, description="Classification results for each image"
    )

    # === GROUPING RESULTS ===
    # Filled by the 'group' node
    # Maps room key (e.g., "cozinha_1") to list of classifications for that room
    grouped_images: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict, description="Images grouped by room"
    )

    # === ESTIMATION RESULTS ===
    # Filled by the 'estimate' node
    room_analyses: list[RoomAnalysis] = Field(
        default_factory=list, description="Analysis and cost estimate for each room"
    )

    # === FINAL OUTPUT ===
    # Filled by the 'summarize' node
    estimate: RenovationEstimate | None = Field(
        default=None, description="Final renovation estimate"
    )
    summary: str = Field(default="", description="Generated summary text")

    # === STREAMING ===
    # Events to send to the frontend during processing
    stream_events: list[StreamEvent] = Field(
        default_factory=list, description="Events emitted during processing"
    )

    # === ERROR HANDLING ===
    error: str | None = Field(default=None, description="Error message if something failed")
    current_step: str = Field(default="", description="Current processing step")

    class Config:
        """Pydantic config for state."""

        # Allow arbitrary types for complex objects
        arbitrary_types_allowed = True


def create_initial_state(url: str, user_id: str = "") -> dict[str, Any]:
    """
    Create the initial state for starting a new analysis.

    Args:
        url: Idealista listing URL
        user_id: Optional user ID

    Returns:
        Initial state dictionary
    """
    return {
        "url": url,
        "user_id": user_id,
        "property_data": None,
        "image_urls": [],
        "classifications": [],
        "grouped_images": {},
        "room_analyses": [],
        "estimate": None,
        "summary": "",
        "stream_events": [],
        "error": None,
        "current_step": "starting",
    }
