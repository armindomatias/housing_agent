"""
Feature extraction enums for room analysis.

All enums used by the structured feature extraction system.
Values are lowercase English identifiers; Portuguese labels live in constants.py.
"""

from enum import Enum

# ---------------------------------------------------------------------------
# M1 — Surfaces
# ---------------------------------------------------------------------------


class FloorMaterial(str, Enum):
    """Floor material types visible in photos."""

    HARDWOOD = "hardwood"
    LAMINATE = "laminate"
    CERAMIC_TILE = "ceramic_tile"
    VINYL = "vinyl"
    MARBLE = "marble"
    STONE = "stone"
    CARPET = "carpet"
    HYDRAULIC_TILE = "hydraulic_tile"
    NOT_VISIBLE = "not_visible"


class WallFinish(str, Enum):
    """Wall finish types."""

    PAINT = "paint"
    AZULEJOS = "azulejos"
    WALLPAPER = "wallpaper"
    EXPOSED_BRICK = "exposed_brick"
    PLASTER = "plaster"
    CERAMIC_TILE = "ceramic_tile"
    NOT_VISIBLE = "not_visible"


# ---------------------------------------------------------------------------
# M2 — Fixtures & Fittings
# ---------------------------------------------------------------------------


class WindowFrameMaterial(str, Enum):
    """Window frame material types."""

    ALUMINUM_SINGLE = "aluminum_single"
    ALUMINUM_DOUBLE = "aluminum_double"
    PVC_DOUBLE = "pvc_double"
    WOOD = "wood"
    NOT_VISIBLE = "not_visible"


class CountertopMaterial(str, Enum):
    """Kitchen countertop material types."""

    GRANITE = "granite"
    MARBLE = "marble"
    LAMINATE = "laminate"
    QUARTZ = "quartz"
    CERAMIC_TILE = "ceramic_tile"
    STAINLESS_STEEL = "stainless_steel"
    NOT_VISIBLE = "not_visible"


class ApplianceType(str, Enum):
    """Kitchen appliance types visible in photos."""

    FRIDGE = "fridge"
    OVEN = "oven"
    HOB = "hob"
    DISHWASHER = "dishwasher"
    WASHING_MACHINE = "washing_machine"
    MICROWAVE = "microwave"
    EXTRACTOR_HOOD = "extractor_hood"


class ShowerOrBath(str, Enum):
    """Bathroom shower/bath configuration."""

    SHOWER = "shower"
    BATHTUB = "bathtub"
    WALK_IN_SHOWER = "walk_in_shower"
    SHOWER_OVER_BATH = "shower_over_bath"
    NOT_VISIBLE = "not_visible"


class VentilationType(str, Enum):
    """Bathroom ventilation type."""

    WINDOW = "window"
    EXTRACTOR_FAN = "extractor_fan"
    NONE_VISIBLE = "none_visible"
    NOT_ASSESSABLE = "not_assessable"


# ---------------------------------------------------------------------------
# M3 — MEP (Mechanical, Electrical, Plumbing)
# ---------------------------------------------------------------------------


class OutletSwitchStyle(str, Enum):
    """Electrical outlet/switch style — best proxy for wiring age."""

    MODERN_FLUSH = "modern_flush"
    ROUND_RECESSED = "round_recessed"
    BAKELITE_OLD = "bakelite_old"
    SURFACE_MOUNTED = "surface_mounted"
    NOT_VISIBLE = "not_visible"


class PlumbingVisibleCondition(str, Enum):
    """Visible plumbing condition under sinks / exposed pipes."""

    MODERN_CONCEALED = "modern_concealed"
    VISIBLE_GOOD = "visible_good"
    VISIBLE_CORRODED = "visible_corroded"
    NOT_VISIBLE = "not_visible"


# ---------------------------------------------------------------------------
# Property-level enums (derived from metadata, no GPT)
# ---------------------------------------------------------------------------


class ConstructionEra(str, Enum):
    """Approximate construction era of the building."""

    PRE_1950 = "pre_1950"
    ERA_1950_1970 = "1950_1970"
    ERA_1970_1990 = "1970_1990"
    ERA_1990_2005 = "1990_2005"
    POST_2005 = "post_2005"
    UNKNOWN = "unknown"


class BuildingTypology(str, Enum):
    """Building type classification."""

    APARTMENT_WITH_ELEVATOR = "apartment_with_elevator"
    APARTMENT_WITHOUT_ELEVATOR = "apartment_without_elevator"
    HOUSE = "house"
    DUPLEX = "duplex"
    STUDIO = "studio"
    OTHER = "other"


class FloorAccessibility(str, Enum):
    """Floor accessibility classification (affects labor logistics)."""

    GROUND_FLOOR = "ground_floor"
    LOW_WITH_ELEVATOR = "low_with_elevator"
    HIGH_WITH_ELEVATOR = "high_with_elevator"
    LOW_WITHOUT_ELEVATOR = "low_without_elevator"
    HIGH_WITHOUT_ELEVATOR = "high_without_elevator"


class EnergyRating(str, Enum):
    """Energy efficiency certificate rating."""

    A_PLUS = "a_plus"
    A = "a"
    B = "b"
    B_MINUS = "b_minus"
    C = "c"
    D = "d"
    E = "e"
    F = "f"
    UNKNOWN = "unknown"


class LocationCostTier(str, Enum):
    """Regional labor/material cost tier."""

    LISBOA = "lisboa"
    PORTO = "porto"
    ALGARVE = "algarve"
    LITORAL = "litoral"
    INTERIOR = "interior"
    ILHAS = "ilhas"


class ConditionStatus(str, Enum):
    """Property overall condition from listing."""

    NEW = "new"
    GOOD = "good"
    NEEDS_RENOVATION = "needs_renovation"
    RUINS = "ruins"
    UNKNOWN = "unknown"


class PropertyPurpose(str, Enum):
    """User's intended purpose for the property."""

    HABITACAO_PROPRIA = "habitacao_propria"
    INVESTIMENTO_ARRENDAMENTO = "investimento_arrendamento"
    SEGUNDA_HABITACAO = "segunda_habitacao"
    REVENDA = "revenda"


class FinishLevel(str, Enum):
    """User-selected finish quality level."""

    ECONOMICO = "economico"
    STANDARD = "standard"
    PREMIUM = "premium"


# ---------------------------------------------------------------------------
# Composite index enums
# ---------------------------------------------------------------------------


class WorkScope(str, Enum):
    """Work scope classification per module or overall."""

    NONE = "none"
    REPAIR = "repair"
    REFURBISH = "refurbish"
    REPLACE = "replace"
    FULL_RENOVATION = "full_renovation"


class HiddenCostRisk(str, Enum):
    """Hidden cost risk index level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ScopeComplexity(str, Enum):
    """Overall scope complexity classification."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    MAJOR = "major"
