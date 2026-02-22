"""
Feature extractor service — calls GPT-4o with structured output to extract
room features from photos.

Each room gets one GPT call that returns a typed feature model (no cost reasoning).
Cost calculation is handled by the deterministic cost_calculator service.

Token monitoring: logs prompt_tokens and completion_tokens per call.
Alert threshold: >2000 input tokens/room triggers a warning.
"""

import json
import re

import structlog

from app.config import OpenAIConfig
from app.models.features.enums import (
    BuildingTypology,
    ConditionStatus,
    ConstructionEra,
    EnergyRating,
    FloorAccessibility,
    LocationCostTier,
)
from app.models.features.modules import (
    BathroomFeatures,
    GenericRoomFeatures,
    KitchenFeatures,
    PropertyContext,
    RoomFeatures,
)
from app.models.property import PropertyData, RoomType
from app.prompts.feature_extraction import build_extraction_prompt
from app.services.openai_client import get_openai_client

logger = structlog.get_logger(__name__)

# Alert if input exceeds this many tokens per room
TOKEN_ALERT_THRESHOLD = 2000


class FeatureExtractorService:
    """Extracts structured room features using GPT-4o vision."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o",
        openai_config: OpenAIConfig | None = None,
    ):
        self.client = get_openai_client(openai_api_key)
        self.model = model
        self.openai_config = openai_config or OpenAIConfig()

    async def extract_room_features(
        self,
        room_type: RoomType,
        room_label: str,
        image_urls: list[str],
        max_images: int = 4,
    ) -> RoomFeatures | None:
        """
        Extract structured features from room photos.

        Args:
            room_type:   Room type determines which feature model to use.
            room_label:  Human-readable label for the prompt, e.g. "Cozinha".
            image_urls:  List of image URLs (base64 or http).
            max_images:  Cap to keep token costs bounded.

        Returns:
            RoomFeatures (KitchenFeatures | BathroomFeatures | GenericRoomFeatures)
            or None on any failure.
        """
        capped_urls = image_urls[:max_images]
        prompt = build_extraction_prompt(room_label, room_type, len(capped_urls))

        content_payload: list[dict] = [{"type": "text", "text": prompt}]
        for url in capped_urls:
            content_payload.append({
                "type": "image_url",
                "image_url": {
                    "url": url,
                    "detail": self.openai_config.estimation_detail,
                },
            })

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content_payload}],
                max_tokens=self.openai_config.room_analysis_max_tokens,
                response_format={"type": "json_object"},
            )

            # Token monitoring
            usage = getattr(response, "usage", None)
            if usage:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                logger.info(
                    "feature_extraction_tokens",
                    room_label=room_label,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                if prompt_tokens > TOKEN_ALERT_THRESHOLD:
                    logger.warning(
                        "feature_extraction_high_token_usage",
                        room_label=room_label,
                        prompt_tokens=prompt_tokens,
                        threshold=TOKEN_ALERT_THRESHOLD,
                    )

            msg = response.choices[0].message

            if msg.refusal:
                logger.warning(
                    "feature_extraction_refusal",
                    room_label=room_label,
                    refusal=msg.refusal,
                )
                return None

            if msg.content is None:
                logger.warning(
                    "feature_extraction_null_content",
                    room_label=room_label,
                    finish_reason=response.choices[0].finish_reason,
                )
                return None

            return self._parse_features(msg.content, room_type, room_label)

        except Exception as e:
            logger.error("feature_extraction_error", room_label=room_label, error=str(e))
            return None

    def _parse_features(
        self, content: str, room_type: RoomType, room_label: str
    ) -> RoomFeatures | None:
        """Parse GPT JSON response into a typed feature model."""
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                "feature_extraction_json_error",
                room_label=room_label,
                error=str(e),
                content_preview=content[:200],
            )
            return None

        try:
            if room_type == RoomType.KITCHEN:
                # Ensure room_type discriminator is set
                raw.setdefault("room_type", "cozinha")
                return KitchenFeatures.model_validate(raw)
            if room_type == RoomType.BATHROOM:
                raw.setdefault("room_type", "casa_de_banho")
                return BathroomFeatures.model_validate(raw)
            # Generic: bedroom, living room, hallway, balcony
            room_type_val = room_type.value
            if room_type_val not in ("quarto", "sala", "corredor", "varanda"):
                room_type_val = "sala"  # safe fallback for unknown generics
            raw.setdefault("room_type", room_type_val)
            return GenericRoomFeatures.model_validate(raw)

        except Exception as e:
            logger.warning(
                "feature_extraction_validation_error",
                room_label=room_label,
                room_type=room_type.value,
                error=str(e),
            )
            return None


# ---------------------------------------------------------------------------
# Property context derivation (pure function, no GPT)
# ---------------------------------------------------------------------------


def derive_property_context(property_data: PropertyData) -> PropertyContext:
    """
    Derive PropertyContext from PropertyData metadata — no GPT call needed.

    Args:
        property_data: Scraped property data.

    Returns:
        PropertyContext with all fields populated from metadata.
    """
    return PropertyContext(
        construction_era=_infer_construction_era(property_data.description),
        building_typology=_infer_building_typology(property_data),
        floor_accessibility=_infer_floor_accessibility(property_data),
        energy_rating=_infer_energy_rating(property_data.energy_certificate),
        location_cost_tier=_infer_location_cost_tier(property_data.location),
        area_m2=property_data.area_m2 or 0,
        usable_area_m2=property_data.usable_area_m2 or 0,
        condition_status=_infer_condition_status(property_data.condition_status),
    )


def _infer_construction_era(description: str) -> ConstructionEra:
    """Extract construction year from description text and map to era."""
    # Look for 4-digit years between 1900 and 2030
    years = re.findall(r"\b(19\d{2}|20[0-2]\d)\b", description)
    if years:
        year = int(years[0])
        if year < 1950:
            return ConstructionEra.PRE_1950
        if year < 1970:
            return ConstructionEra.ERA_1950_1970
        if year < 1990:
            return ConstructionEra.ERA_1970_1990
        if year < 2005:
            return ConstructionEra.ERA_1990_2005
        return ConstructionEra.POST_2005
    return ConstructionEra.UNKNOWN


def _infer_building_typology(data: PropertyData) -> BuildingTypology:
    if data.is_studio:
        return BuildingTypology.STUDIO
    if data.is_duplex:
        return BuildingTypology.DUPLEX
    if data.property_type and "moradia" in data.property_type.lower():
        return BuildingTypology.HOUSE
    if data.has_elevator:
        return BuildingTypology.APARTMENT_WITH_ELEVATOR
    if data.has_elevator is False:
        return BuildingTypology.APARTMENT_WITHOUT_ELEVATOR
    return BuildingTypology.APARTMENT_WITHOUT_ELEVATOR


def _infer_floor_accessibility(data: PropertyData) -> FloorAccessibility:
    floor_str = str(data.floor).strip().lower()
    try:
        floor_num = int(floor_str.replace("r/c", "0").replace("rc", "0"))
    except ValueError:
        floor_num = 2  # assume mid-floor if unknown

    if floor_num == 0:
        return FloorAccessibility.GROUND_FLOOR
    if data.has_elevator:
        return FloorAccessibility.HIGH_WITH_ELEVATOR if floor_num > 3 else FloorAccessibility.LOW_WITH_ELEVATOR
    return FloorAccessibility.HIGH_WITHOUT_ELEVATOR if floor_num > 3 else FloorAccessibility.LOW_WITHOUT_ELEVATOR


def _infer_energy_rating(certificate: str) -> EnergyRating:
    """Map energy certificate string to EnergyRating enum."""
    mapping = {
        "a+": EnergyRating.A_PLUS,
        "a": EnergyRating.A,
        "b": EnergyRating.B,
        "b-": EnergyRating.B_MINUS,
        "c": EnergyRating.C,
        "d": EnergyRating.D,
        "e": EnergyRating.E,
        "f": EnergyRating.F,
    }
    return mapping.get(certificate.strip().lower(), EnergyRating.UNKNOWN)


def _infer_location_cost_tier(location: str) -> LocationCostTier:
    """Map location string to cost tier."""
    loc = location.lower()
    if "lisboa" in loc or "lisbon" in loc:
        return LocationCostTier.LISBOA
    if "porto" in loc or "oporto" in loc:
        return LocationCostTier.PORTO
    if "algarve" in loc or "faro" in loc or "tavira" in loc or "portimão" in loc:
        return LocationCostTier.ALGARVE
    if "açores" in loc or "madeira" in loc:
        return LocationCostTier.ILHAS
    if any(c in loc for c in ["beja", "évora", "portalegre", "castelo branco", "guarda", "bragança", "vila real"]):
        return LocationCostTier.INTERIOR
    return LocationCostTier.LITORAL


def _infer_condition_status(status: str) -> ConditionStatus:
    mapping = {
        "good": ConditionStatus.GOOD,
        "bom": ConditionStatus.GOOD,
        "bad": ConditionStatus.NEEDS_RENOVATION,
        "mau": ConditionStatus.NEEDS_RENOVATION,
        "needs_renovation": ConditionStatus.NEEDS_RENOVATION,
        "new": ConditionStatus.NEW,
        "novo": ConditionStatus.NEW,
        "ruins": ConditionStatus.RUINS,
        "ruinas": ConditionStatus.RUINS,
    }
    return mapping.get(status.strip().lower(), ConditionStatus.UNKNOWN)
