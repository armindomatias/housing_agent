"""
Feature module models for structured room analysis.

Each room type has a specific feature model containing M1-M3 modules.
M4 (Structural) and M5 (Exterior) are Optional=None, ready for v2.

Module layout:
  M1 — Surfaces (floor, walls, ceiling)
  M2 — Fixtures & Fittings (windows, doors, kitchen/bathroom fixtures)
  M3 — MEP (electrical outlets, plumbing)
"""

from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

from app.models.features.enums import (
    ApplianceType,
    BuildingTypology,
    ConditionStatus,
    ConstructionEra,
    CountertopMaterial,
    EnergyRating,
    FloorAccessibility,
    FloorMaterial,
    LocationCostTier,
    OutletSwitchStyle,
    PlumbingVisibleCondition,
    ShowerOrBath,
    VentilationType,
    WallFinish,
    WindowFrameMaterial,
)

def _coerce_condition_score(v: object) -> int | None:
    """Coerce GPT output to int or None. Non-integer strings (e.g. 'not_visible') → None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _validate_condition_range(v: int | None) -> int | None:
    """Enforce 1-5 range only for non-None values."""
    if v is not None and not (1 <= v <= 5):
        raise ValueError(f"Condition score must be between 1 and 5, got {v}")
    return v


# Condition scores: 1 = needs full replacement, 5 = excellent / no work needed
# None = GPT could not assess the feature (treated as "keep" by cost calculator)
# BeforeValidator coerces non-integer strings → None; AfterValidator enforces range.
ConditionScore = Annotated[
    int | None,
    BeforeValidator(_coerce_condition_score),
    AfterValidator(_validate_condition_range),
    Field(default=None),
]


# ---------------------------------------------------------------------------
# M1 — Surfaces (shared across all room types)
# ---------------------------------------------------------------------------


class GenericSurfacesModule(BaseModel):
    """M1 surfaces for generic rooms (bedroom, living room, hallway)."""

    floor_material: FloorMaterial = Field(description="Observed floor material type")
    floor_condition: ConditionScore = Field(description="Floor condition 1-5")
    wall_finish: WallFinish = Field(description="Primary wall finish type")
    wall_condition: ConditionScore = Field(description="Wall condition 1-5")
    ceiling_condition: ConditionScore = Field(description="Ceiling condition 1-5")


class KitchenSurfacesModule(BaseModel):
    """M1 surfaces for kitchens."""

    floor_material: FloorMaterial = Field(description="Observed floor material type")
    floor_condition: ConditionScore = Field(description="Floor condition 1-5")
    wall_finish: WallFinish = Field(description="Primary wall finish type")
    wall_condition: ConditionScore = Field(description="Wall condition 1-5")
    ceiling_condition: ConditionScore = Field(description="Ceiling condition 1-5")


class BathroomSurfacesModule(BaseModel):
    """M1 surfaces for bathrooms (no floor_material — almost always tile in PT)."""

    wall_finish: WallFinish = Field(description="Primary wall finish (typically azulejos)")
    wall_condition: ConditionScore = Field(description="Wall condition 1-5")
    floor_condition: ConditionScore = Field(description="Floor condition 1-5")
    ceiling_condition: ConditionScore = Field(description="Ceiling condition 1-5")


# ---------------------------------------------------------------------------
# M2 — Fixtures & Fittings
# ---------------------------------------------------------------------------


class GenericFixturesModule(BaseModel):
    """M2 fixtures for generic rooms (bedroom, living room, hallway)."""

    window_frame_material: WindowFrameMaterial = Field(
        description="Window frame material type"
    )
    window_condition: ConditionScore = Field(description="Window condition 1-5")
    window_count_estimate: int = Field(ge=0, description="Estimated number of windows")
    door_condition: ConditionScore = Field(description="Door condition 1-5")


class KitchenFixturesModule(BaseModel):
    """M2 fixtures for kitchens."""

    window_frame_material: WindowFrameMaterial = Field(
        description="Window frame material type"
    )
    cabinet_condition: ConditionScore = Field(description="Kitchen cabinet condition 1-5")
    countertop_material: CountertopMaterial = Field(
        description="Countertop material type"
    )
    countertop_condition: ConditionScore = Field(description="Countertop condition 1-5")
    appliances_visible: list[ApplianceType] = Field(
        default_factory=list, description="Appliances visible in photos"
    )
    door_condition: ConditionScore = Field(description="Door condition 1-5")


class BathroomFixturesModule(BaseModel):
    """M2 fixtures for bathrooms."""

    sanitary_ware_condition: ConditionScore = Field(
        description="Toilet/sink condition 1-5"
    )
    shower_or_bath: ShowerOrBath = Field(description="Shower/bath configuration")
    shower_bath_condition: ConditionScore = Field(
        description="Shower/bath condition 1-5"
    )
    bathroom_tile_condition: ConditionScore = Field(
        description="Wall tile condition 1-5 (separate from floor)"
    )
    ventilation_visible: VentilationType = Field(description="Ventilation type visible")
    window_frame_material: WindowFrameMaterial = Field(
        description="Bathroom window frame material (if present)"
    )


# ---------------------------------------------------------------------------
# M3 — MEP (Mechanical, Electrical, Plumbing)
# ---------------------------------------------------------------------------


class GenericMEPModule(BaseModel):
    """M3 MEP for generic rooms (bedroom, living room, hallway)."""

    outlet_switch_style: OutletSwitchStyle = Field(
        description="Electrical outlet/switch style — proxy for wiring age"
    )


class KitchenMEPModule(BaseModel):
    """M3 MEP for kitchens."""

    plumbing_visible_condition: PlumbingVisibleCondition = Field(
        description="Visible plumbing condition under sink"
    )
    outlet_switch_style: OutletSwitchStyle = Field(
        description="Electrical outlet/switch style"
    )


class BathroomMEPModule(BaseModel):
    """M3 MEP for bathrooms."""

    plumbing_visible_condition: PlumbingVisibleCondition = Field(
        description="Visible plumbing condition"
    )
    outlet_switch_style: OutletSwitchStyle = Field(
        description="Electrical outlet/switch style"
    )


# ---------------------------------------------------------------------------
# Room-level feature models
# ---------------------------------------------------------------------------


class GenericRoomFeatures(BaseModel):
    """Features for generic rooms: bedroom, living room, hallway, balcony."""

    room_type: Literal["quarto", "sala", "corredor", "varanda"] = Field(
        description="Room type discriminator"
    )
    surfaces: GenericSurfacesModule | None = Field(
        default=None, description="M1: Surface features"
    )
    fixtures: GenericFixturesModule | None = Field(
        default=None, description="M2: Fixture features"
    )
    mep: GenericMEPModule | None = Field(
        default=None, description="M3: MEP features"
    )
    estimated_area_m2: float | None = Field(
        default=None, ge=0, description="GPT-estimated room area in m2"
    )
    room_notes: str = Field(
        default="", description="Consolidated observation for chat context"
    )


class KitchenFeatures(BaseModel):
    """Features for kitchen rooms."""

    room_type: Literal["cozinha"] = Field(
        default="cozinha", description="Room type discriminator"
    )
    surfaces: KitchenSurfacesModule | None = Field(
        default=None, description="M1: Surface features"
    )
    fixtures: KitchenFixturesModule | None = Field(
        default=None, description="M2: Fixture features"
    )
    mep: KitchenMEPModule | None = Field(
        default=None, description="M3: MEP features"
    )
    estimated_area_m2: float | None = Field(
        default=None, ge=0, description="GPT-estimated room area in m2"
    )
    kitchen_notes: str = Field(
        default="", description="Consolidated observation for chat context"
    )


class BathroomFeatures(BaseModel):
    """Features for bathroom rooms."""

    room_type: Literal["casa_de_banho"] = Field(
        default="casa_de_banho", description="Room type discriminator"
    )
    surfaces: BathroomSurfacesModule | None = Field(
        default=None, description="M1: Surface features"
    )
    fixtures: BathroomFixturesModule | None = Field(
        default=None, description="M2: Fixture features"
    )
    mep: BathroomMEPModule | None = Field(
        default=None, description="M3: MEP features"
    )
    estimated_area_m2: float | None = Field(
        default=None, ge=0, description="GPT-estimated room area in m2"
    )
    bathroom_notes: str = Field(
        default="", description="Consolidated observation for chat context"
    )


# Discriminated union for any room's features
RoomFeatures = Annotated[
    Union[GenericRoomFeatures, KitchenFeatures, BathroomFeatures],
    Field(discriminator="room_type"),
]


# ---------------------------------------------------------------------------
# Property-level context (derived from metadata, no GPT)
# ---------------------------------------------------------------------------


class PropertyContext(BaseModel):
    """Property-level features derived from PropertyData metadata."""

    construction_era: ConstructionEra = Field(
        default=ConstructionEra.UNKNOWN, description="Approximate construction era"
    )
    building_typology: BuildingTypology = Field(
        default=BuildingTypology.OTHER, description="Building type classification"
    )
    floor_accessibility: FloorAccessibility = Field(
        default=FloorAccessibility.GROUND_FLOOR,
        description="Floor accessibility classification",
    )
    energy_rating: EnergyRating = Field(
        default=EnergyRating.UNKNOWN, description="Energy efficiency rating"
    )
    location_cost_tier: LocationCostTier = Field(
        default=LocationCostTier.LITORAL, description="Regional cost tier"
    )
    area_m2: float = Field(default=0, description="Total constructed area")
    usable_area_m2: float = Field(default=0, description="Usable area")
    condition_status: ConditionStatus = Field(
        default=ConditionStatus.UNKNOWN, description="Overall condition from listing"
    )
