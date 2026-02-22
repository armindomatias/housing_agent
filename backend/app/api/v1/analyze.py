"""
Property analysis API endpoints.

This module provides the main API endpoint for analyzing properties.
It supports both streaming (SSE) and non-streaming responses.

Endpoints:
- POST /api/v1/analyze - Analyze a property with streaming progress
- POST /api/v1/analyze/sync - Analyze a property without streaming (simpler)
"""

import asyncio
import inspect
import json
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from sse_starlette.sse import EventSourceResponse

from app.auth import CurrentUser
from app.graphs.state import create_initial_state
from app.models.billing import EntitlementDecision
from app.models.property import RenovationEstimate
from app.services.billing_service import BillingService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analyze", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    """Request body for property analysis."""

    url: HttpUrl = Field(description="Idealista listing URL")


class AnalyzeResponse(BaseModel):
    """Response for synchronous analysis."""

    success: bool
    estimate: RenovationEstimate | None = None
    error: str | None = None


async def stream_analysis(
    url: str,
    user_id: str,
    graph: Any,
    billing_service: BillingService | None = None,
    reservation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generator that streams analysis events as SSE.

    Runs the pre-compiled LangGraph and yields each stream event as it occurs.

    Args:
        url: Idealista URL to analyze
        user_id: Optional user ID
        graph: Pre-compiled LangGraph instance from app.state

    Yields:
        SSE-formatted event strings
    """
    initial_state = create_initial_state(url, user_id)

    # Track which events we've already sent
    sent_events = 0
    has_result = False
    has_error = False

    try:
        async for state in graph.astream(initial_state):
            # Some LangGraph configurations may yield a coroutine instead of a plain dict.
            # If that happens, await it here so we always work with the resolved state.
            if inspect.iscoroutine(state):
                state = await state

            if isinstance(state, dict):
                # Handle different state formats from LangGraph
                actual_state = state
                if len(state) == 1:
                    # State is wrapped in node name dict
                    actual_state = list(state.values())[0]

                events = actual_state.get("stream_events", [])
                new_events = events[sent_events:]

                for event in new_events:
                    if hasattr(event, "model_dump"):
                        event_data = event.model_dump()
                    else:
                        event_data = event

                    event_type = event_data.get("type")
                    if event_type == "result":
                        has_result = True
                    elif event_type == "error":
                        has_error = True

                    yield json.dumps(event_data, ensure_ascii=False)
                    sent_events += 1

    except asyncio.CancelledError:
        has_error = True
        raise
    except Exception as e:
        logger.error("stream_analysis_error", error=str(e))
        has_error = True
        error_event = {
            "type": "error",
            "message": f"Erro inesperado: {str(e)}",
            "step": 0,
            "total_steps": 5,
        }
        yield json.dumps(error_event, ensure_ascii=False)
    finally:
        if billing_service and reservation_id:
            if has_result and not has_error:
                await billing_service.commit_reservation(reservation_id)
            else:
                await billing_service.release_reservation(reservation_id)


def _get_billing_service(request: Request) -> BillingService | None:
    return getattr(request.app.state, "billing_service", None)


def _payment_required_error(decision: EntitlementDecision) -> HTTPException:
    return HTTPException(
        status_code=402,
        detail={
            "code": "payment_required",
            "reason": decision.reason.value,
            "plan_code": decision.plan_code.value,
            "free_analyses_remaining": decision.free_analyses_remaining,
            "analyses_remaining": decision.analyses_remaining,
            "daily_remaining": decision.daily_remaining,
        },
    )


@router.post("", response_class=EventSourceResponse)
async def analyze_property_stream(
    body: AnalyzeRequest,
    request: Request,
    user: CurrentUser,
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
      -H "Authorization: Bearer <token>" \
      -d '{"url": "https://www.idealista.pt/imovel/12345678/"}'
    ```
    """
    structlog.contextvars.bind_contextvars(property_url=str(body.url), user_id=user.id)
    graph = request.app.state.graph
    billing_service = _get_billing_service(request)
    reservation_id: str | None = None

    if billing_service is not None:
        decision = await billing_service.reserve_analysis(user.id)
        if not decision.allowed:
            raise _payment_required_error(decision)
        reservation_id = decision.reservation_id

    return EventSourceResponse(
        stream_analysis(
            str(body.url),
            user.id,
            graph,
            billing_service=billing_service,
            reservation_id=reservation_id,
        ),
        media_type="text/event-stream",
    )


@router.post("/sync", response_model=AnalyzeResponse)
async def analyze_property_sync(
    body: AnalyzeRequest,
    request: Request,
    user: CurrentUser,
) -> AnalyzeResponse:
    """
    Analyze a property without streaming (simpler but no progress updates).

    This endpoint runs the complete analysis and returns the result at the end.
    Use this if you don't need real-time progress updates.

    Returns the complete RenovationEstimate or an error message.
    """
    billing_service = _get_billing_service(request)
    reservation_id: str | None = None

    try:
        structlog.contextvars.bind_contextvars(property_url=str(body.url), user_id=user.id)
        if billing_service is not None:
            decision = await billing_service.reserve_analysis(user.id)
            if not decision.allowed:
                raise _payment_required_error(decision)
            reservation_id = decision.reservation_id

        graph = request.app.state.graph
        initial_state = create_initial_state(str(body.url), user.id)

        final_state = await graph.ainvoke(initial_state)

        if final_state.get("error"):
            if billing_service is not None:
                await billing_service.release_reservation(reservation_id)
            return AnalyzeResponse(
                success=False,
                error=final_state["error"],
            )

        estimate = final_state.get("estimate")
        if estimate is None:
            if billing_service is not None:
                await billing_service.release_reservation(reservation_id)
            return AnalyzeResponse(
                success=False,
                error="Não foi possível gerar a estimativa",
            )

        if billing_service is not None:
            await billing_service.commit_reservation(reservation_id)

        return AnalyzeResponse(
            success=True,
            estimate=estimate,
        )

    except Exception as e:
        if billing_service is not None:
            await billing_service.release_reservation(reservation_id)
        logger.error("sync_analysis_error", error=str(e))
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Erro na análise: {str(e)}",
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "rehabify-analyzer"}
