"""
Renovation cost estimation service using GPT-4 Vision.

Analyzes grouped room photos and produces one cost estimate per room.
Photos are pre-grouped by ImageClassifierService so each room is assessed
as a whole, even when the listing has several angles of the same space.

Estimates use Portuguese market prices (2024/2025) and always return a
min–max range to reflect inherent uncertainty from photo-only analysis.

## Concurrency model

analyze_all_rooms() submits one async task per room and collects results
with asyncio.as_completed(). A semaphore caps concurrent GPT-4o calls to
stay within rate limits. Progress events fire as each room finishes, in
whatever order — the frontend only cares about current/total counts.

For a 5-room property this reduces wall-clock time from ~35 s (serial) to
~12 s (parallel), bounded by the slowest single call rather than the sum.

Usage:
    estimator = RenovationEstimatorService(openai_api_key="...")
    analyses = await estimator.analyze_all_rooms(grouped_images, progress_callback)
"""

import asyncio
import json

import structlog

from app.config import ImageProcessingConfig, OpenAIConfig
from app.constants import (
    CONDITION_MAP,
    FALLBACK_CONFIDENCE,
    FALLBACK_COSTS,
    IMAGE_BOOST_MAX,
    IMAGE_BOOST_PER_IMAGE,
)
from app.models.features.enums import WorkScope
from app.models.features.modules import PropertyContext, RoomFeatures
from app.models.features.outputs import (
    RoomCostResult,
    UserPreferences,
)
from app.models.property import (
    FloorPlanAnalysis,
    FloorPlanIdea,
    ImageClassification,
    PropertyData,
    RenovationEstimate,
    RenovationItem,
    RoomAnalysis,
    RoomCondition,
    RoomType,
)
from app.prompts.renovation import FLOOR_PLAN_ANALYSIS_PROMPT, ROOM_ANALYSIS_PROMPT, SUMMARY_PROMPT
from app.services.cost_calculator import (
    calculate_costs,
    compute_composite_indices,
    renovation_items_from_cost_result,
)
from app.services.feature_extractor import FeatureExtractorService, derive_property_context
from app.services.image_classifier import get_room_label
from app.services.openai_client import get_openai_client

logger = structlog.get_logger(__name__)


class RenovationEstimatorService:
    """Service for estimating renovation costs using GPT-4 Vision."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o",
        max_concurrent: int = 3,
        openai_config: OpenAIConfig | None = None,
        image_processing: ImageProcessingConfig | None = None,
        user_preferences: UserPreferences | None = None,
        property_data: PropertyData | None = None,
    ):
        """
        Initialize the renovation estimator.

        Args:
            openai_api_key:    OpenAI API key
            model:             Model to use for analysis
            max_concurrent:    Maximum simultaneous room-analysis API calls.
            openai_config:     OpenAI call parameters (max_tokens, detail levels).
            image_processing:  Image processing limits (images per room analysis).
            user_preferences:  User preferences for cost calculation (diy, finish_level).
            property_data:     Property data for deriving context (region, era, etc.).
        """
        self.client = get_openai_client(openai_api_key)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.openai_config = openai_config or OpenAIConfig()
        self.image_processing = image_processing or ImageProcessingConfig()
        self.user_preferences = user_preferences or UserPreferences()
        self._property_context: PropertyContext | None = (
            derive_property_context(property_data) if property_data else None
        )
        self._feature_extractor = FeatureExtractorService(
            openai_api_key=openai_api_key,
            model=model,
            openai_config=self.openai_config,
        )

    async def analyze_room(
        self,
        room_type: RoomType,
        room_number: int,
        image_urls: list[str],
        property_context: PropertyContext | None = None,
    ) -> RoomAnalysis:
        """
        Analyze a single room using feature extraction + deterministic cost calculation.

        Flow:
          1. Feature extractor (GPT-4o) → structured features (no cost reasoning)
          2. Cost calculator (pure Python) → deterministic costs from features
          3. Map cost result → backward-compat RoomAnalysis fields

        Falls back to legacy GPT analysis if feature extraction fails.

        Args:
            room_type:        Type of room (kitchen, bedroom, etc.)
            room_number:      Room number (1, 2, etc.)
            image_urls:       List of image URLs for this room
            property_context: Property-level context for cost calculation

        Returns:
            RoomAnalysis with condition assessment and cost estimates
        """
        room_label = get_room_label(room_type, room_number)
        context = property_context or self._property_context or PropertyContext()

        async with self.semaphore:
            features = await self._feature_extractor.extract_room_features(
                room_type=room_type,
                room_label=room_label,
                image_urls=image_urls,
                max_images=self.image_processing.images_per_room_analysis,
            )

        if features is not None:
            return self._build_analysis_from_features(
                features=features,
                room_type=room_type,
                room_number=room_number,
                room_label=room_label,
                image_urls=image_urls,
                context=context,
            )

        # Feature extraction failed — fall back to legacy GPT analysis
        logger.warning("feature_extraction_failed_using_legacy", room_label=room_label)
        return await self._analyze_room_legacy(room_type, room_number, image_urls, room_label)

    def _build_analysis_from_features(
        self,
        features: "RoomFeatures",
        room_type: RoomType,
        room_number: int,
        room_label: str,
        image_urls: list[str],
        context: PropertyContext,
    ) -> RoomAnalysis:
        """Build RoomAnalysis from structured features + cost calculator."""

        cost_result = calculate_costs(features, room_type, self.user_preferences, context)

        # Backward compat: derive condition from overall work scope
        condition = self._work_scope_to_condition(cost_result.work_scope.overall)
        condition_notes = self._features_to_notes(features)

        renovation_items = renovation_items_from_cost_result(cost_result)

        total_min = round(cost_result.cost_breakdown.total_min, 2)
        total_max = round(cost_result.cost_breakdown.total_max, 2)

        # Confidence from module confidence
        confidence = min(
            1.0,
            cost_result.module_confidence.overall + min(IMAGE_BOOST_MAX, len(image_urls) * IMAGE_BOOST_PER_IMAGE),
        )

        return RoomAnalysis(
            room_type=room_type,
            room_number=room_number,
            room_label=room_label,
            images=image_urls,
            condition=condition,
            condition_notes=condition_notes,
            renovation_items=renovation_items,
            cost_min=total_min,
            cost_max=total_max,
            confidence=confidence,
            features=features,
            cost_breakdown=cost_result.cost_breakdown,
        )

    def _work_scope_to_condition(self, scope: WorkScope) -> RoomCondition:
        """Map WorkScope to backward-compat RoomCondition."""
        mapping = {
            WorkScope.NONE: RoomCondition.EXCELLENT,
            WorkScope.REPAIR: RoomCondition.GOOD,
            WorkScope.REFURBISH: RoomCondition.FAIR,
            WorkScope.REPLACE: RoomCondition.POOR,
            WorkScope.FULL_RENOVATION: RoomCondition.NEEDS_FULL_RENOVATION,
        }
        return mapping.get(scope, RoomCondition.FAIR)

    def _features_to_notes(self, features: "RoomFeatures") -> str:
        """Extract consolidated notes from features for condition_notes field."""
        if hasattr(features, "room_notes") and features.room_notes:
            return features.room_notes
        if hasattr(features, "kitchen_notes") and features.kitchen_notes:
            return features.kitchen_notes
        if hasattr(features, "bathroom_notes") and features.bathroom_notes:
            return features.bathroom_notes
        return ""

    async def _analyze_room_legacy(
        self,
        room_type: RoomType,
        room_number: int,
        image_urls: list[str],
        room_label: str,
    ) -> RoomAnalysis:
        """Legacy GPT-based room analysis (fallback when feature extraction fails)."""
        prompt = ROOM_ANALYSIS_PROMPT.format(
            room_label=room_label,
            num_images=len(image_urls),
        )

        content_payload = [{"type": "text", "text": prompt}]
        capped_urls = image_urls[:self.image_processing.images_per_room_analysis]
        for url in capped_urls:
            content_payload.append({
                "type": "image_url",
                "image_url": {"url": url, "detail": self.openai_config.estimation_detail},
            })

        _refused = False

        async def _call_api() -> str | None:
            nonlocal _refused
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content_payload}],
                max_tokens=self.openai_config.room_analysis_max_tokens,
                response_format={"type": "json_object"},
            )
            msg = resp.choices[0].message
            if msg.refusal:
                _refused = True
                logger.warning("room_analysis_refusal", room_label=room_label, refusal=msg.refusal)
                return None
            if msg.content is None:
                logger.warning("room_analysis_null_content", room_label=room_label,
                               finish_reason=resp.choices[0].finish_reason)
                return None
            return msg.content

        try:
            content = await _call_api()
            if content is None and not _refused:
                logger.info("room_analysis_retrying", room_label=room_label)
                await asyncio.sleep(1)
                content = await _call_api()

            if content is None:
                return self._get_fallback_analysis(room_type, room_number, room_label, image_urls)

            data = json.loads(content)
            renovation_items = [
                RenovationItem(
                    item=item_data.get("item", ""),
                    cost_min=float(item_data.get("cost_min", 0)),
                    cost_max=float(item_data.get("cost_max", 0)),
                    priority=item_data.get("priority", "media"),
                    notes=item_data.get("notes", ""),
                )
                for item_data in data.get("renovation_items", [])
            ]
            condition = self._map_condition(data.get("condition", "razoavel"))
            base_confidence = float(data.get("confidence", 0.5))
            image_boost = min(IMAGE_BOOST_MAX, len(image_urls) * IMAGE_BOOST_PER_IMAGE)

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
                confidence=min(1.0, base_confidence + image_boost),
            )

        except json.JSONDecodeError as e:
            logger.warning("room_analysis_json_parse_error", room_label=room_label, error=str(e))
            return self._get_fallback_analysis(room_type, room_number, room_label, image_urls)
        except Exception as e:
            logger.error("room_analysis_api_error", room_label=room_label, error=str(e))
            return self._get_fallback_analysis(room_type, room_number, room_label, image_urls)

    def _map_condition(self, condition_str: str) -> RoomCondition:
        """
        Map a condition string to the RoomCondition enum.

        Args:
            condition_str: Condition string from GPT response

        Returns:
            Corresponding RoomCondition enum value
        """
        return CONDITION_MAP.get(condition_str.lower(), RoomCondition.FAIR)

    def _get_fallback_analysis(
        self,
        room_type: RoomType,
        room_number: int,
        room_label: str,
        image_urls: list[str],
    ) -> RoomAnalysis:
        """
        Return a fallback analysis when GPT fails.

        Uses conservative estimates from FALLBACK_COSTS based on room type.
        """
        cost_min, cost_max = FALLBACK_COSTS.get(room_type, (500, 2000))

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
            confidence=FALLBACK_CONFIDENCE,
        )

    async def analyze_all_rooms(
        self,
        grouped_images: dict[str, list[ImageClassification]],
        progress_callback=None,
        property_data: PropertyData | None = None,
    ) -> list[RoomAnalysis]:
        """
        Analyze all rooms concurrently, respecting the semaphore rate limit.

        Submits one coroutine per room via asyncio.as_completed() so progress
        events fire as each room finishes. Semaphore is handled inside analyze_room.

        Args:
            grouped_images:    Dict mapping room key → list[ImageClassification].
                               Produced by ImageClassifierService.group_by_room().
            progress_callback: Optional async callback(current, total, room_analysis).
            property_data:     Optional property data to derive context for cost calc.

        Returns:
            List of RoomAnalysis objects (one per room, order may differ from input).
        """
        context = (
            derive_property_context(property_data)
            if property_data
            else self._property_context or PropertyContext()
        )

        total = len(grouped_images)
        room_analyses: list[RoomAnalysis] = []
        completed = 0

        tasks = [
            self.analyze_room(
                classifications[0].room_type,
                classifications[0].room_number,
                [c.image_url for c in classifications],
                property_context=context,
            )
            for classifications in grouped_images.values()
        ]

        for coro in asyncio.as_completed(tasks):
            analysis = await coro
            room_analyses.append(analysis)
            completed += 1

            if progress_callback:
                await progress_callback(completed, total, analysis)

        return room_analyses

    async def analyze_floor_plan(
        self,
        image_urls: list[str],
        property_data: PropertyData | None = None,
    ) -> FloorPlanAnalysis | None:
        """
        Analyse floor plan image(s) and return layout optimisation ideas.

        Sends the images to GPT-4o with FLOOR_PLAN_ANALYSIS_PROMPT. The result
        is non-critical — callers should treat None as "no ideas available" and
        continue normally without raising an error.

        Args:
            image_urls:    URLs of floor plan images to analyse.
            property_data: Optional property metadata for context (typology, area, price).

        Returns:
            FloorPlanAnalysis with ideas, or None on any failure.
        """
        if not image_urls:
            return None

        # Build property context string from metadata when available
        if property_data:
            parts = []
            if property_data.num_rooms:
                parts.append(f"T{property_data.num_rooms}")
            if property_data.area_m2:
                parts.append(f"{property_data.area_m2:.0f}m²")
            if property_data.price:
                parts.append(f"{property_data.price:,.0f}€")
            if property_data.location:
                parts.append(property_data.location)
            context_line = ", ".join(parts)
            property_context = (
                f"DADOS DO IMÓVEL: {context_line}\n\n" if context_line else ""
            )
        else:
            property_context = ""

        prompt = FLOOR_PLAN_ANALYSIS_PROMPT.format(property_context=property_context)

        content_payload: list[dict] = [{"type": "text", "text": prompt}]
        for url in image_urls:
            content_payload.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": self.openai_config.estimation_detail},
                }
            )

        try:
            async with self.semaphore:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": content_payload}],
                    max_tokens=self.openai_config.floor_plan_max_tokens,
                    response_format={"type": "json_object"},
                )

            msg = response.choices[0].message

            if msg.refusal:
                logger.warning("floor_plan_analysis_refusal", refusal=msg.refusal)
                return None

            if msg.content is None:
                logger.warning(
                    "floor_plan_analysis_null_content",
                    finish_reason=response.choices[0].finish_reason,
                )
                return None

            data = json.loads(msg.content)

            ideas = [
                FloorPlanIdea(
                    title=idea.get("title", ""),
                    description=idea.get("description", ""),
                    potential_impact=idea.get("potential_impact", ""),
                    estimated_complexity=idea.get("estimated_complexity", "media"),
                )
                for idea in data.get("ideas", [])
            ]

            return FloorPlanAnalysis(
                images=image_urls,
                ideas=ideas,
                property_context=data.get("property_context", ""),
                confidence=float(data.get("confidence", 0.5)),
            )

        except Exception as e:
            logger.error("floor_plan_analysis_error", error=str(e))
            return None

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
                max_tokens=self.openai_config.summary_max_tokens,
            )
            msg = response.choices[0].message
            if msg.refusal:
                logger.warning("summary_generation_refusal", refusal=msg.refusal)
                raise ValueError("OpenAI refused to generate summary")
            if msg.content is None:
                logger.warning(
                    "summary_generation_null_content",
                    finish_reason=response.choices[0].finish_reason,
                )
                raise ValueError("OpenAI returned null content for summary")
            return msg.content.strip()
        except Exception as e:
            logger.error("summary_generation_error", error=str(e))
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
        floor_plan_analysis: FloorPlanAnalysis | None = None,
    ) -> RenovationEstimate:
        """
        Create the final renovation estimate.

        Args:
            property_url:       Original Idealista URL
            property_data:      Scraped property data
            room_analyses:      List of room analyses
            summary:            Generated summary text
            floor_plan_analysis: Optional floor plan analysis

        Returns:
            Complete RenovationEstimate
        """
        total_min = sum(r.cost_min for r in room_analyses)
        total_max = sum(r.cost_max for r in room_analyses)

        if total_max > 0:
            weighted_confidence = sum(r.confidence * r.cost_max for r in room_analyses) / total_max
        else:
            weighted_confidence = sum(r.confidence for r in room_analyses) / max(len(room_analyses), 1)

        # Build composite indices from rooms that used feature extraction
        room_results: dict[str, RoomCostResult] = {}
        for r in room_analyses:
            if r.features is not None and r.cost_breakdown is not None:
                from app.services.cost_calculator import calculate_costs
                ctx = (
                    derive_property_context(property_data)
                    if property_data
                    else self._property_context or PropertyContext()
                )
                cost_result = calculate_costs(r.features, r.room_type, self.user_preferences, ctx)
                room_results[r.room_label] = cost_result

        composite = None
        if room_results and property_data:
            ctx = derive_property_context(property_data)
            composite = compute_composite_indices(room_results, ctx)
        elif room_results:
            composite = compute_composite_indices(room_results, PropertyContext())

        return RenovationEstimate(
            property_url=property_url,
            property_data=property_data,
            room_analyses=room_analyses,
            total_cost_min=total_min,
            total_cost_max=total_max,
            overall_confidence=min(1.0, weighted_confidence),
            summary=summary,
            floor_plan_ideas=floor_plan_analysis,
            composite_indices=composite,
            user_preferences=self.user_preferences,
        )
