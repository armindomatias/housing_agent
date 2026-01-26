"""
Property analysis API endpoints.

This module provides the main API endpoint for analyzing properties.
It supports both streaming (SSE) and non-streaming responses.

Endpoints:
- POST /api/v1/analyze - Analyze a property with streaming progress
- POST /api/v1/analyze/sync - Analyze a property without streaming (simpler)
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sse_starlette.sse import EventSourceResponse

from app.config import Settings, get_settings
from app.graphs.main_graph import build_renovation_graph
from app.graphs.state import create_initial_state
from app.models.property import RenovationEstimate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    """Request body for property analysis."""

    url: HttpUrl = Field(description="Idealista listing URL")
    user_id: str = Field(default="", description="Optional user ID for tracking")


class AnalyzeResponse(BaseModel):
    """Response for synchronous analysis."""

    success: bool
    estimate: RenovationEstimate | None = None
    error: str | None = None


async def stream_analysis(
    url: str, user_id: str, settings: Settings
) -> AsyncGenerator[str, None]:
    """
    Generator that streams analysis events as SSE.

    Runs the LangGraph and yields each stream event as it occurs.

    Args:
        url: Idealista URL to analyze
        user_id: Optional user ID
        settings: Application settings

    Yields:
        SSE-formatted event strings
    """
    graph = build_renovation_graph(settings)
    initial_state = create_initial_state(url, user_id)

    # Track which events we've already sent
    sent_events = 0

    try:
        # Run the graph - we'll check for new events after each node
        async for state in graph.astream(initial_state):
            # Get new events from state
            # Note: astream yields state after each node, so we can check for new events
            if isinstance(state, dict):
                # Handle different state formats from LangGraph
                actual_state = state
                if len(state) == 1:
                    # State is wrapped in node name dict
                    actual_state = list(state.values())[0]

                events = actual_state.get("stream_events", [])
                new_events = events[sent_events:]

                for event in new_events:
                    # Convert event to dict if it's a Pydantic model
                    if hasattr(event, "model_dump"):
                        event_data = event.model_dump()
                    else:
                        event_data = event

                    yield json.dumps(event_data, ensure_ascii=False)
                    sent_events += 1

    except Exception as e:
        logger.error(f"Stream analysis error: {e}")
        error_event = {
            "type": "error",
            "message": f"Erro inesperado: {str(e)}",
            "step": 0,
            "total_steps": 5,
        }
        yield json.dumps(error_event, ensure_ascii=False)


@router.post("", response_class=EventSourceResponse)
async def analyze_property_stream(
    request: AnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """
    Analyze a property with streaming progress updates.

    This endpoint uses Server-Sent Events (SSE) to stream progress updates
    as the analysis runs. The frontend can display each step in real-time.

    Event types:
    - status: Major step updates (e.g., "A obter dados do Idealista...")
    - progress: Detailed progress (e.g., "A classificar foto 1/18...")
    - result: Final result with complete estimate
    - error: Error message if something fails

    Example usage with curl:
    ```
    curl -N -X POST http://localhost:8000/api/v1/analyze \
      -H "Content-Type: application/json" \
      -d '{"url": "https://www.idealista.pt/imovel/12345678/"}'
    ```
    """
    return EventSourceResponse(
        stream_analysis(str(request.url), request.user_id, settings),
        media_type="text/event-stream",
    )


@router.post("/sync", response_model=AnalyzeResponse)
async def analyze_property_sync(
    request: AnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """
    Analyze a property without streaming (simpler but no progress updates).

    This endpoint runs the complete analysis and returns the result at the end.
    Use this if you don't need real-time progress updates.

    Returns the complete RenovationEstimate or an error message.
    """
    try:
        graph = build_renovation_graph(settings)
        initial_state = create_initial_state(str(request.url), request.user_id)

        # Run the complete graph
        final_state = await graph.ainvoke(initial_state)

        # Check for errors
        if final_state.get("error"):
            return AnalyzeResponse(
                success=False,
                error=final_state["error"],
            )

        # Get the estimate
        estimate = final_state.get("estimate")
        if estimate is None:
            return AnalyzeResponse(
                success=False,
                error="Não foi possível gerar a estimativa",
            )

        return AnalyzeResponse(
            success=True,
            estimate=estimate,
        )

    except Exception as e:
        logger.error(f"Sync analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro na análise: {str(e)}",
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "rehabify-analyzer"}
