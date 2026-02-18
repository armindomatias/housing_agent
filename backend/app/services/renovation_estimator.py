"""
Renovation cost estimation service using GPT-4 Vision.

Analyzes grouped room photos and produces one cost estimate per room.
Photos are pre-grouped by ImageClassifierService so each room is assessed
as a whole, even when the listing has several angles of the same space.

Estimates use Portuguese market prices (2024/2025) and always return a
min–max range to reflect inherent uncertainty from photo-only analysis.

## Concurrency model

analyze_all_rooms() submits one async task per room and collects results
with asyncio.as_completed(). A semaphore (default: 3 slots) caps concurrent
GPT-4o calls to stay within rate limits. Progress events fire as each room
finishes, in whatever order — the frontend only cares about current/total counts.

For a 5-room property this reduces wall-clock time from ~35 s (serial) to
~12 s (parallel), bounded by the slowest single call rather than the sum.

Usage:
    estimator = RenovationEstimatorService(openai_api_key="...")
    analyses = await estimator.analyze_all_rooms(grouped_images, progress_callback)
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI

from app.models.property import (
    ImageClassification,
    PropertyData,
    RenovationEstimate,
    RenovationItem,
    RoomAnalysis,
    RoomCondition,
    RoomType,
)
from app.prompts.renovation import ROOM_ANALYSIS_PROMPT, SUMMARY_PROMPT
from app.services.image_classifier import get_room_label

logger = logging.getLogger(__name__)


class RenovationEstimatorService:
    """Service for estimating renovation costs using GPT-4 Vision."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o",      # Use full GPT-4o for better analysis
        max_concurrent: int = 3,    # Concurrent GPT-4o calls (rate-limit guard)
    ):
        """
        Initialize the renovation estimator.

        Args:
            openai_api_key: OpenAI API key
            model:          Model to use for analysis (default: gpt-4o for quality)
            max_concurrent: Maximum simultaneous room-analysis API calls.
                            3 is a safe default — GPT-4o Vision calls are heavy
                            and the Tier-1 rate limit is typically 500 RPM.
        """
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_room(
        self,
        room_type: RoomType,
        room_number: int,
        image_urls: list[str],
    ) -> RoomAnalysis:
        """
        Analyze a single room and estimate renovation costs.

        This method receives ALL photos of a specific room and analyzes them
        together to provide a single, comprehensive estimate.

        Args:
            room_type: Type of room (kitchen, bedroom, etc.)
            room_number: Room number (1, 2, etc.)
            image_urls: List of image URLs for this room

        Returns:
            RoomAnalysis with condition assessment and cost estimates
        """
        room_label = get_room_label(room_type, room_number)

        # Build the prompt with room context
        prompt = ROOM_ANALYSIS_PROMPT.format(
            room_label=room_label,
            num_images=len(image_urls),
        )

        # Build message content with all images
        content = [{"type": "text", "text": prompt}]

        # Add all images for this room (GPT-4 Vision can analyze multiple)
        for url in image_urls[:4]:  # Limit to 4 images to manage costs/tokens
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": "high"},  # High detail for cost estimation
                }
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content}],
                max_tokens=2000,  # Increased for detailed room analysis JSON
                response_format={"type": "json_object"},
            )

            # Parse the JSON response
            data = json.loads(response.choices[0].message.content)

            # Parse renovation items
            renovation_items = []
            for item_data in data.get("renovation_items", []):
                renovation_items.append(
                    RenovationItem(
                        item=item_data.get("item", ""),
                        cost_min=float(item_data.get("cost_min", 0)),
                        cost_max=float(item_data.get("cost_max", 0)),
                        priority=item_data.get("priority", "media"),
                        notes=item_data.get("notes", ""),
                    )
                )

            # Map condition string to enum
            condition = self._map_condition(data.get("condition", "razoavel"))

            # Calculate confidence boost based on number of images
            # More images = higher confidence
            base_confidence = float(data.get("confidence", 0.5))
            image_boost = min(0.2, len(image_urls) * 0.05)  # Up to 0.2 boost
            final_confidence = min(1.0, base_confidence + image_boost)

            return RoomAnalysis(
                room_type=room_type,
                room_number=room_number,
                room_label=room_label,
                images=image_urls,
                condition=condition,
                condition_notes=data.get("condition_notes", ""),
                renovation_items=renovation_items,
                cost_min=float(data.get("cost_min", 0)),
                cost_max=float(data.get("cost_max", 0)),
                confidence=final_confidence,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse room analysis JSON for {room_label}: {e}")
            logger.debug(f"Raw response content: {response.choices[0].message.content[:500]}")
            return self._get_fallback_analysis(room_type, room_number, room_label, image_urls)
        except Exception as e:
            logger.error(f"Error analyzing room {room_label}: {e}")
            return self._get_fallback_analysis(room_type, room_number, room_label, image_urls)

    def _map_condition(self, condition_str: str) -> RoomCondition:
        """
        Map a condition string to the RoomCondition enum.

        Args:
            condition_str: Condition string from GPT response

        Returns:
            Corresponding RoomCondition enum value
        """
        mapping = {
            "excelente": RoomCondition.EXCELLENT,
            "excellent": RoomCondition.EXCELLENT,
            "bom": RoomCondition.GOOD,
            "good": RoomCondition.GOOD,
            "razoavel": RoomCondition.FAIR,
            "razoável": RoomCondition.FAIR,
            "fair": RoomCondition.FAIR,
            "mau": RoomCondition.POOR,
            "poor": RoomCondition.POOR,
            "necessita_remodelacao_total": RoomCondition.NEEDS_FULL_RENOVATION,
            "needs_full_renovation": RoomCondition.NEEDS_FULL_RENOVATION,
        }
        return mapping.get(condition_str.lower(), RoomCondition.FAIR)

    def _get_fallback_analysis(
        self,
        room_type: RoomType,
        room_number: int,
        room_label: str,
        image_urls: list[str],
    ) -> RoomAnalysis:
        """
        Return a fallback analysis when GPT fails.

        Uses conservative estimates based on room type.
        """
        # Conservative fallback estimates by room type
        fallback_costs = {
            RoomType.KITCHEN: (5000, 15000),
            RoomType.BATHROOM: (3000, 8000),
            RoomType.BEDROOM: (1000, 3000),
            RoomType.LIVING_ROOM: (1500, 5000),
            RoomType.HALLWAY: (500, 1500),
            RoomType.BALCONY: (500, 2000),
            RoomType.EXTERIOR: (0, 0),
            RoomType.GARAGE: (500, 2000),
            RoomType.STORAGE: (200, 800),
            RoomType.OTHER: (500, 2000),
        }

        cost_min, cost_max = fallback_costs.get(room_type, (500, 2000))

        return RoomAnalysis(
            room_type=room_type,
            room_number=room_number,
            room_label=room_label,
            images=image_urls,
            condition=RoomCondition.FAIR,
            condition_notes="Não foi possível analisar as imagens em detalhe.",
            renovation_items=[
                RenovationItem(
                    item=f"Remodelação geral da {room_label.lower()}",
                    cost_min=cost_min,
                    cost_max=cost_max,
                    priority="media",
                    notes="Estimativa conservadora devido a falha na análise",
                )
            ],
            cost_min=cost_min,
            cost_max=cost_max,
            confidence=0.3,  # Low confidence for fallback
        )

    async def analyze_all_rooms(
        self,
        grouped_images: dict[str, list[ImageClassification]],
        progress_callback=None,
    ) -> list[RoomAnalysis]:
        """
        Analyze all rooms concurrently, respecting the semaphore rate limit.

        Submits one bounded coroutine per room via asyncio.as_completed() so
        progress events fire as each room finishes rather than waiting for all.
        The semaphore caps concurrent GPT-4o calls at self.max_concurrent (default 3).

        Args:
            grouped_images:    Dict mapping room key → list[ImageClassification].
                               Produced by ImageClassifierService.group_by_room().
            progress_callback: Optional async callback(current, total, room_analysis)
                               called as each room finishes.

        Returns:
            List of RoomAnalysis objects (one per room, order may differ from input).
        """
        total = len(grouped_images)
        room_analyses: list[RoomAnalysis] = []
        completed = 0

        async def _bounded_analyze(
            room_type: RoomType, room_number: int, image_urls: list[str]
        ) -> RoomAnalysis:
            # Semaphore lives here, not in analyze_room, so analyze_room stays
            # a clean, independently testable wrapper around the API call.
            async with self.semaphore:
                return await self.analyze_room(room_type, room_number, image_urls)

        # Build one bounded coroutine per room
        tasks = [
            _bounded_analyze(
                classifications[0].room_type,
                classifications[0].room_number,
                [c.image_url for c in classifications],
            )
            for classifications in grouped_images.values()
        ]

        # as_completed yields futures as they finish, not in submission order.
        # This lets progress events fire immediately when a room is done.
        for coro in asyncio.as_completed(tasks):
            analysis = await coro
            room_analyses.append(analysis)
            completed += 1

            if progress_callback:
                await progress_callback(completed, total, analysis)

        return room_analyses

    async def generate_summary(
        self,
        property_data: PropertyData | None,
        room_analyses: list[RoomAnalysis],
        total_min: float,
        total_max: float,
    ) -> str:
        """
        Generate a summary of the renovation estimate.

        Args:
            property_data: Property information (if available)
            room_analyses: List of room analyses
            total_min: Total minimum cost
            total_max: Total maximum cost

        Returns:
            Summary text in Portuguese
        """
        # Build room summaries
        room_summaries = []
        for analysis in room_analyses:
            summary = (
                f"- {analysis.room_label}: Estado {analysis.condition.value}, "
                f"custo estimado {analysis.cost_min:,.0f}€ - {analysis.cost_max:,.0f}€"
            )
            room_summaries.append(summary)

        prompt = SUMMARY_PROMPT.format(
            price=f"{property_data.price:,.0f}" if property_data else "N/A",
            area_m2=f"{property_data.area_m2:.0f}" if property_data else "N/A",
            location=property_data.location if property_data else "N/A",
            room_summaries="\n".join(room_summaries),
            total_min=f"{total_min:,.0f}",
            total_max=f"{total_max:,.0f}",
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return (
                f"Estimativa total de remodelação: {total_min:,.0f}€ - {total_max:,.0f}€. "
                f"Analisadas {len(room_analyses)} divisões."
            )

    def create_estimate(
        self,
        property_url: str,
        property_data: PropertyData | None,
        room_analyses: list[RoomAnalysis],
        summary: str,
    ) -> RenovationEstimate:
        """
        Create the final renovation estimate.

        Args:
            property_url: Original Idealista URL
            property_data: Scraped property data
            room_analyses: List of room analyses
            summary: Generated summary text

        Returns:
            Complete RenovationEstimate
        """
        # Calculate totals
        total_min = sum(r.cost_min for r in room_analyses)
        total_max = sum(r.cost_max for r in room_analyses)

        # Calculate overall confidence (weighted average by cost)
        if total_max > 0:
            weighted_confidence = sum(r.confidence * r.cost_max for r in room_analyses) / total_max
        else:
            weighted_confidence = sum(r.confidence for r in room_analyses) / max(
                len(room_analyses), 1
            )

        return RenovationEstimate(
            property_url=property_url,
            property_data=property_data,
            room_analyses=room_analyses,
            total_cost_min=total_min,
            total_cost_max=total_max,
            overall_confidence=min(1.0, weighted_confidence),
            summary=summary,
        )
