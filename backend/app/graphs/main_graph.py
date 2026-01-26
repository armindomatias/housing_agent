"""
Main LangGraph definition for the renovation estimation pipeline.

This graph orchestrates the entire analysis process:
1. scrape: Fetch property data from Idealista via Apify
2. classify: Classify each image to identify room types using GPT-4 Vision
3. group: Group images by room to avoid duplicate estimates
4. estimate: Analyze each room and estimate renovation costs
5. summarize: Generate final report with totals and summary

Each node emits stream events that are sent to the frontend in real-time.

Usage:
    graph = build_renovation_graph(settings)
    async for event in graph.astream({"url": "...", "user_id": "..."}):
        # Handle stream events
        pass
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.config import Settings
from app.models.property import ImageClassification, RoomType, StreamEvent
from app.services.idealista import IdealistaService
from app.services.image_classifier import ImageClassifierService
from app.services.renovation_estimator import RenovationEstimatorService

logger = logging.getLogger(__name__)


# Type alias for state (using dict for LangGraph compatibility)
GraphState = dict[str, Any]


async def scrape_node(state: GraphState, *, settings: Settings) -> GraphState:
    """
    Node 1: Scrape property data from Idealista.

    Fetches the listing data and image URLs using Apify.
    """
    url = state["url"]
    events = list(state.get("stream_events", []))

    # Emit start event
    events.append(
        StreamEvent(
            type="status",
            message="A obter dados do Idealista...",
            step=1,
            total_steps=5,
        )
    )

    try:
        # Create service and scrape
        service = IdealistaService(settings.apify_token)
        try:
            property_data = await service.scrape_property(url)
        finally:
            await service.close()

        # Emit success event
        num_images = len(property_data.image_urls)
        events.append(
            StreamEvent(
                type="status",
                message=f"Encontradas {num_images} fotografias",
                step=1,
                total_steps=5,
                data={"num_images": num_images, "title": property_data.title},
            )
        )

        return {
            **state,
            "property_data": property_data,
            "image_urls": property_data.image_urls,
            "stream_events": events,
            "current_step": "scraped",
        }

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        events.append(
            StreamEvent(
                type="error",
                message=f"Erro ao obter dados: {str(e)}",
                step=1,
                total_steps=5,
            )
        )
        return {
            **state,
            "error": str(e),
            "stream_events": events,
            "current_step": "error",
        }


async def classify_node(state: GraphState, *, settings: Settings) -> GraphState:
    """
    Node 2: Classify each image to identify room types.

    Uses GPT-4 Vision (mini model) to classify each photo.
    Emits progress events for each image processed.
    """
    if state.get("error"):
        return state

    image_urls = state.get("image_urls", [])
    events = list(state.get("stream_events", []))

    events.append(
        StreamEvent(
            type="status",
            message=f"A classificar {len(image_urls)} fotografias...",
            step=2,
            total_steps=5,
        )
    )

    try:
        classifier = ImageClassifierService(
            settings.openai_api_key,
            model=settings.openai_classification_model,
        )

        classifications = []

        # Progress callback to emit events for each image
        async def progress_callback(
            current: int, total: int, classification: ImageClassification
        ) -> None:
            room_label = classifier.get_room_label(
                classification.room_type, classification.room_number
            )
            events.append(
                StreamEvent(
                    type="progress",
                    message=f"A classificar foto {current}/{total}: {room_label} detectada",
                    step=2,
                    total_steps=5,
                    data={
                        "current": current,
                        "total": total,
                        "room_type": classification.room_type.value,
                        "confidence": classification.confidence,
                    },
                )
            )

        classifications = await classifier.classify_images(image_urls, progress_callback)

        # Summary of classifications
        room_counts: dict[str, int] = {}
        for c in classifications:
            room_type = c.room_type.value
            room_counts[room_type] = room_counts.get(room_type, 0) + 1

        summary_parts = []
        for room_type, count in room_counts.items():
            if room_type not in ["exterior", "outro"]:
                summary_parts.append(f"{count}x {room_type}")

        events.append(
            StreamEvent(
                type="status",
                message=f"Divisões identificadas: {', '.join(summary_parts)}",
                step=2,
                total_steps=5,
            )
        )

        return {
            **state,
            "classifications": classifications,
            "stream_events": events,
            "current_step": "classified",
        }

    except Exception as e:
        logger.error(f"Classification failed: {e}")
        events.append(
            StreamEvent(
                type="error",
                message=f"Erro na classificação: {str(e)}",
                step=2,
                total_steps=5,
            )
        )
        return {
            **state,
            "error": str(e),
            "stream_events": events,
            "current_step": "error",
        }


async def group_node(state: GraphState, *, settings: Settings) -> GraphState:
    """
    Node 3: Group images by room.

    This step is crucial to avoid counting the same room multiple times.
    Multiple photos of the kitchen should be analyzed together as ONE kitchen.
    """
    _ = settings  # Not used in this node but kept for consistency

    if state.get("error"):
        return state

    classifications = state.get("classifications", [])
    events = list(state.get("stream_events", []))

    events.append(
        StreamEvent(
            type="status",
            message="A agrupar fotografias por divisão...",
            step=3,
            total_steps=5,
        )
    )

    # Group images by room
    classifier = ImageClassifierService(
        openai_api_key="",  # Not needed for grouping
    )
    grouped = classifier.group_by_room(classifications)

    # Filter out exterior and other non-room images for estimation
    # But keep track of them for reference
    room_groups = {}
    skipped_types = [RoomType.EXTERIOR.value, RoomType.OTHER.value]

    for room_key, room_classifications in grouped.items():
        room_type = room_classifications[0].room_type.value
        if room_type not in skipped_types:
            # Convert to dict for JSON serialization in state
            room_groups[room_key] = [
                {
                    "image_url": c.image_url,
                    "room_type": c.room_type.value,
                    "room_number": c.room_number,
                    "confidence": c.confidence,
                }
                for c in room_classifications
            ]

    events.append(
        StreamEvent(
            type="status",
            message=f"Agrupadas {sum(len(v) for v in room_groups.values())} fotos em {len(room_groups)} divisões",
            step=3,
            total_steps=5,
            data={"num_rooms": len(room_groups), "rooms": list(room_groups.keys())},
        )
    )

    return {
        **state,
        "grouped_images": room_groups,
        "stream_events": events,
        "current_step": "grouped",
    }


async def estimate_node(state: GraphState, *, settings: Settings) -> GraphState:
    """
    Node 4: Estimate renovation costs for each room.

    Uses GPT-4 Vision to analyze each room and provide cost estimates.
    Each room is analyzed only once, even if it has multiple photos.
    """
    if state.get("error"):
        return state

    grouped_images = state.get("grouped_images", {})
    events = list(state.get("stream_events", []))

    events.append(
        StreamEvent(
            type="status",
            message=f"A analisar estado de {len(grouped_images)} divisões...",
            step=4,
            total_steps=5,
        )
    )

    try:
        estimator = RenovationEstimatorService(
            settings.openai_api_key,
            model=settings.openai_vision_model,
        )

        room_analyses = []

        # Analyze each room
        for _, room_data in grouped_images.items():
            # Reconstruct classification objects
            classifications = [
                ImageClassification(
                    image_url=d["image_url"],
                    room_type=RoomType(d["room_type"]),
                    room_number=d["room_number"],
                    confidence=d["confidence"],
                )
                for d in room_data
            ]

            room_type = classifications[0].room_type
            room_number = classifications[0].room_number
            image_urls = [c.image_url for c in classifications]

            # Get room label for progress message
            room_label = estimator._classifier.get_room_label(room_type, room_number)

            events.append(
                StreamEvent(
                    type="progress",
                    message=f"A analisar {room_label}...",
                    step=4,
                    total_steps=5,
                )
            )

            # Analyze the room
            analysis = await estimator.analyze_room(room_type, room_number, image_urls)
            room_analyses.append(analysis)

            events.append(
                StreamEvent(
                    type="progress",
                    message=(
                        f"{room_label}: estado {analysis.condition.value}, "
                        f"custo {analysis.cost_min:,.0f}€ - {analysis.cost_max:,.0f}€"
                    ),
                    step=4,
                    total_steps=5,
                    data={
                        "room": room_label,
                        "condition": analysis.condition.value,
                        "cost_min": analysis.cost_min,
                        "cost_max": analysis.cost_max,
                    },
                )
            )

        events.append(
            StreamEvent(
                type="status",
                message=f"Análise completa de {len(room_analyses)} divisões",
                step=4,
                total_steps=5,
            )
        )

        return {
            **state,
            "room_analyses": room_analyses,
            "stream_events": events,
            "current_step": "estimated",
        }

    except Exception as e:
        logger.error(f"Estimation failed: {e}")
        events.append(
            StreamEvent(
                type="error",
                message=f"Erro na estimativa: {str(e)}",
                step=4,
                total_steps=5,
            )
        )
        return {
            **state,
            "error": str(e),
            "stream_events": events,
            "current_step": "error",
        }


async def summarize_node(state: GraphState, *, settings: Settings) -> GraphState:
    """
    Node 5: Generate final summary and create the complete estimate.

    Calculates totals and generates a human-readable summary.
    """
    if state.get("error"):
        return state

    property_data = state.get("property_data")
    room_analyses = state.get("room_analyses", [])
    events = list(state.get("stream_events", []))

    events.append(
        StreamEvent(
            type="status",
            message="A calcular custos finais...",
            step=5,
            total_steps=5,
        )
    )

    try:
        estimator = RenovationEstimatorService(
            settings.openai_api_key,
            model=settings.openai_vision_model,
        )

        # Calculate totals
        total_min = sum(r.cost_min for r in room_analyses)
        total_max = sum(r.cost_max for r in room_analyses)

        # Generate summary
        summary = await estimator.generate_summary(
            property_data, room_analyses, total_min, total_max
        )

        # Create final estimate
        estimate = estimator.create_estimate(
            state["url"],
            property_data,
            room_analyses,
            summary,
        )

        events.append(
            StreamEvent(
                type="result",
                message=f"Estimativa completa: {total_min:,.0f}€ - {total_max:,.0f}€",
                step=5,
                total_steps=5,
                data={"estimate": estimate.model_dump()},
            )
        )

        return {
            **state,
            "estimate": estimate,
            "summary": summary,
            "stream_events": events,
            "current_step": "completed",
        }

    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        events.append(
            StreamEvent(
                type="error",
                message=f"Erro ao gerar resumo: {str(e)}",
                step=5,
                total_steps=5,
            )
        )
        return {
            **state,
            "error": str(e),
            "stream_events": events,
            "current_step": "error",
        }


def build_renovation_graph(settings: Settings) -> StateGraph:
    """
    Build the complete LangGraph for renovation estimation.

    The graph flows linearly:
    scrape -> classify -> group -> estimate -> summarize -> END

    Args:
        settings: Application settings with API keys

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with dict state
    graph = StateGraph(dict)

    # Add nodes - each node receives state and settings
    # Using functools.partial equivalent via lambda to inject settings
    graph.add_node("scrape", lambda s: scrape_node(s, settings=settings))
    graph.add_node("classify", lambda s: classify_node(s, settings=settings))
    graph.add_node("group", lambda s: group_node(s, settings=settings))
    graph.add_node("estimate", lambda s: estimate_node(s, settings=settings))
    graph.add_node("summarize", lambda s: summarize_node(s, settings=settings))

    # Define the flow (linear for MVP)
    graph.set_entry_point("scrape")
    graph.add_edge("scrape", "classify")
    graph.add_edge("classify", "group")
    graph.add_edge("group", "estimate")
    graph.add_edge("estimate", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


# Convenience function to run the graph
async def analyze_property(url: str, settings: Settings, user_id: str = "") -> GraphState:
    """
    Run the complete renovation analysis for a property.

    Args:
        url: Idealista listing URL
        settings: Application settings
        user_id: Optional user ID

    Returns:
        Final state with all results
    """
    from app.graphs.state import create_initial_state

    graph = build_renovation_graph(settings)
    initial_state = create_initial_state(url, user_id)

    # Run the graph
    final_state = await graph.ainvoke(initial_state)
    return final_state
