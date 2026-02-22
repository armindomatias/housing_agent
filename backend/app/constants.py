"""
Business logic constants for the Rehabify application.

These values are stable across environments (dev/staging/prod) and do not
need env-var overrides. For operational parameters that vary per environment
(timeouts, concurrency limits, max_tokens), see config.py.
"""

from app.models.features.enums import (
    ConstructionEra,
    CountertopMaterial,
    FinishLevel,
    FloorMaterial,
    LocationCostTier,
    WindowFrameMaterial,
    WorkScope,
)
from app.models.features.outputs import CostRange
from app.models.property import RoomCondition, RoomType

# --- Fallback renovation costs (EUR) when GPT analysis fails ---
# (min, max) per room type — conservative estimates
FALLBACK_COSTS: dict[RoomType, tuple[int, int]] = {
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

# --- Confidence thresholds ---
TAG_CLASSIFICATION_CONFIDENCE = 0.9  # Apify tag-based (no GPT)
FALLBACK_CONFIDENCE = 0.3            # When GPT fails entirely
IMAGE_BOOST_PER_IMAGE = 0.05         # Confidence boost per extra image
IMAGE_BOOST_MAX = 0.2                # Max total confidence boost from images

# --- Room types to skip during renovation estimation ---
# Stored as value strings to match the pattern used in graph nodes
SKIPPED_ROOM_TYPES: frozenset[str] = frozenset(
    {RoomType.EXTERIOR.value, RoomType.OTHER.value}
)

# --- Room types that can have multiple physical instances ---
MULTI_ROOM_TYPES: set[RoomType] = {RoomType.BEDROOM, RoomType.BATHROOM}

# --- Maximum images to send in a single clustering API call ---
MAX_CLUSTERING_IMAGES = 10

# --- Apify tag → RoomType mapping ---
# Apify's Idealista scraper attaches a "tag" string (English) to each image.
# Every known tag is mapped here; unknown tags fall back to GPT classification.
APIFY_TAG_MAP: dict[str, RoomType] = {
    "kitchen": RoomType.KITCHEN,
    "bedroom": RoomType.BEDROOM,
    "bathroom": RoomType.BATHROOM,
    "livingroom": RoomType.LIVING_ROOM,
    "living_room": RoomType.LIVING_ROOM,
    "living-room": RoomType.LIVING_ROOM,
    "lounge": RoomType.LIVING_ROOM,
    "dining": RoomType.LIVING_ROOM,
    "diningroom": RoomType.LIVING_ROOM,
    "terrace": RoomType.BALCONY,
    "balcony": RoomType.BALCONY,
    "exterior": RoomType.EXTERIOR,
    "facade": RoomType.EXTERIOR,
    "garden": RoomType.EXTERIOR,
    "garage": RoomType.GARAGE,
    "storage": RoomType.STORAGE,
    "hallway": RoomType.HALLWAY,
    "hall": RoomType.HALLWAY,
    "corridor": RoomType.HALLWAY,
    "laundry": RoomType.STORAGE,
    "office": RoomType.BEDROOM,
    "pool": RoomType.EXTERIOR,
    "planta": RoomType.FLOOR_PLAN,
    "floor_plan": RoomType.FLOOR_PLAN,
    "floorplan": RoomType.FLOOR_PLAN,
    "floor-plan": RoomType.FLOOR_PLAN,
    "plan": RoomType.FLOOR_PLAN,
    "plans": RoomType.FLOOR_PLAN,
    "planimetria": RoomType.FLOOR_PLAN,
}

# --- GPT response room type mapping ---
GPT_ROOM_TYPE_MAP: dict[str, RoomType] = {
    "cozinha": RoomType.KITCHEN,
    "kitchen": RoomType.KITCHEN,
    "sala": RoomType.LIVING_ROOM,
    "living_room": RoomType.LIVING_ROOM,
    "living room": RoomType.LIVING_ROOM,
    "sala de estar": RoomType.LIVING_ROOM,
    "quarto": RoomType.BEDROOM,
    "bedroom": RoomType.BEDROOM,
    "casa_de_banho": RoomType.BATHROOM,
    "casa de banho": RoomType.BATHROOM,
    "bathroom": RoomType.BATHROOM,
    "wc": RoomType.BATHROOM,
    "corredor": RoomType.HALLWAY,
    "hallway": RoomType.HALLWAY,
    "hall": RoomType.HALLWAY,
    "varanda": RoomType.BALCONY,
    "balcony": RoomType.BALCONY,
    "terraço": RoomType.BALCONY,
    "terrace": RoomType.BALCONY,
    "exterior": RoomType.EXTERIOR,
    "fachada": RoomType.EXTERIOR,
    "garagem": RoomType.GARAGE,
    "garage": RoomType.GARAGE,
    "arrecadacao": RoomType.STORAGE,
    "storage": RoomType.STORAGE,
    "despensa": RoomType.STORAGE,
    "planta": RoomType.FLOOR_PLAN,
    "floor_plan": RoomType.FLOOR_PLAN,
    "floor plan": RoomType.FLOOR_PLAN,
    "floorplan": RoomType.FLOOR_PLAN,
    "outro": RoomType.OTHER,
    "other": RoomType.OTHER,
}

# --- Room type labels (Portuguese) ---
ROOM_TYPE_LABELS: dict[RoomType, str] = {
    RoomType.KITCHEN: "Cozinha",
    RoomType.LIVING_ROOM: "Sala",
    RoomType.BEDROOM: "Quarto",
    RoomType.BATHROOM: "Casa de Banho",
    RoomType.HALLWAY: "Corredor",
    RoomType.BALCONY: "Varanda",
    RoomType.EXTERIOR: "Exterior",
    RoomType.GARAGE: "Garagem",
    RoomType.STORAGE: "Arrecadação",
    RoomType.FLOOR_PLAN: "Planta",
    RoomType.OTHER: "Outro",
}

# --- Condition string → RoomCondition mapping ---
CONDITION_MAP: dict[str, RoomCondition] = {
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

# --- Known image MIME types ---
KNOWN_IMAGE_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp", "image/gif"}
DEFAULT_IMAGE_CONTENT_TYPE = "image/jpeg"

# --- API metadata ---
API_TITLE = "Rehabify API"
API_VERSION = "0.1.0"

# --- Pipeline ---
PIPELINE_TOTAL_STEPS = 5

# =============================================================================
# FEATURE EXTRACTION COST TABLES
# Prices in EUR, Portugal market 2024/2025.
# Nested dict: COST_TABLE[category][action][material_or_key] -> CostRange
# Unit: "m2" | "unit" | "room" | "linear_m"
# =============================================================================

COST_TABLE: dict[str, dict] = {
    "flooring": {
        "replace": {
            FloorMaterial.HARDWOOD: CostRange(min=50, max=80, unit="m2"),
            FloorMaterial.LAMINATE: CostRange(min=20, max=35, unit="m2"),
            FloorMaterial.CERAMIC_TILE: CostRange(min=25, max=50, unit="m2"),
            FloorMaterial.VINYL: CostRange(min=15, max=30, unit="m2"),
            FloorMaterial.MARBLE: CostRange(min=80, max=150, unit="m2"),
            FloorMaterial.STONE: CostRange(min=60, max=120, unit="m2"),
            FloorMaterial.HYDRAULIC_TILE: CostRange(min=40, max=80, unit="m2"),
            FloorMaterial.CARPET: CostRange(min=15, max=30, unit="m2"),
            # Default when material not visible
            FloorMaterial.NOT_VISIBLE: CostRange(min=20, max=50, unit="m2"),
        },
        "refinish": {
            FloorMaterial.HARDWOOD: CostRange(min=15, max=30, unit="m2"),
        },
        "repair": CostRange(min=5, max=15, unit="m2"),
    },
    "walls": {
        "repaint": CostRange(min=8, max=15, unit="m2"),
        "strip_and_replaster": CostRange(min=25, max=45, unit="m2"),
        "remove_azulejos": CostRange(min=40, max=60, unit="m2"),
        "install_azulejos": CostRange(min=30, max=60, unit="m2"),
        "repair": CostRange(min=8, max=20, unit="m2"),
    },
    "ceiling": {
        "repaint": CostRange(min=6, max=12, unit="m2"),
        "repair_and_repaint": CostRange(min=15, max=30, unit="m2"),
        "full_replaster": CostRange(min=25, max=45, unit="m2"),
    },
    "windows": {
        "replace": {
            WindowFrameMaterial.ALUMINUM_SINGLE: CostRange(min=300, max=600, unit="unit"),
            WindowFrameMaterial.ALUMINUM_DOUBLE: CostRange(min=400, max=700, unit="unit"),
            WindowFrameMaterial.PVC_DOUBLE: CostRange(min=400, max=800, unit="unit"),
            WindowFrameMaterial.WOOD: CostRange(min=500, max=1000, unit="unit"),
            WindowFrameMaterial.NOT_VISIBLE: CostRange(min=350, max=700, unit="unit"),
        },
        "repair": CostRange(min=50, max=150, unit="unit"),
    },
    "doors": {
        "replace": CostRange(min=150, max=400, unit="unit"),
        "repair_and_paint": CostRange(min=30, max=80, unit="unit"),
    },
    "kitchen_cabinets": {
        "replace_full": CostRange(min=3000, max=15000, unit="room"),
        "reface": CostRange(min=800, max=2500, unit="room"),
        "repair": CostRange(min=200, max=600, unit="room"),
    },
    "kitchen_countertop": {
        "replace": {
            CountertopMaterial.GRANITE: CostRange(min=800, max=2000, unit="linear_m"),
            CountertopMaterial.MARBLE: CostRange(min=1000, max=2500, unit="linear_m"),
            CountertopMaterial.LAMINATE: CostRange(min=200, max=500, unit="linear_m"),
            CountertopMaterial.QUARTZ: CostRange(min=700, max=1800, unit="linear_m"),
            CountertopMaterial.CERAMIC_TILE: CostRange(min=300, max=700, unit="linear_m"),
            CountertopMaterial.STAINLESS_STEEL: CostRange(min=600, max=1500, unit="linear_m"),
            CountertopMaterial.NOT_VISIBLE: CostRange(min=400, max=1200, unit="linear_m"),
        },
        "repair": CostRange(min=100, max=300, unit="room"),
    },
    "kitchen_appliances": {
        "full_set": CostRange(min=2000, max=8000, unit="room"),
    },
    "bathroom_sanitary": {
        "replace_full_set": CostRange(min=500, max=3000, unit="room"),
        "replace_toilet": CostRange(min=150, max=500, unit="unit"),
        "replace_sink": CostRange(min=100, max=400, unit="unit"),
        "repair": CostRange(min=50, max=200, unit="room"),
    },
    "bathroom_shower_bath": {
        "replace_shower": CostRange(min=400, max=1500, unit="unit"),
        "replace_bathtub": CostRange(min=300, max=1200, unit="unit"),
        "replace_walk_in": CostRange(min=800, max=3000, unit="unit"),
        "reseal": CostRange(min=50, max=150, unit="unit"),
    },
    "bathroom_tiles": {
        "replace_wall_tiles": CostRange(min=30, max=60, unit="m2"),
        "repair_grout": CostRange(min=5, max=15, unit="m2"),
    },
    "electrical": {
        "rewire_room": CostRange(min=300, max=800, unit="room"),
        "rewire_property": CostRange(min=3000, max=8000, unit="room"),
        "update_outlets": CostRange(min=50, max=150, unit="unit"),
    },
    "plumbing": {
        "replace_room": CostRange(min=500, max=2000, unit="room"),
        "replace_property": CostRange(min=3000, max=10000, unit="room"),
        "repair_visible": CostRange(min=100, max=500, unit="room"),
    },
}

# --- Labor ratios per work category ---
# labor_ratio: fraction of total cost that is labor.
# When diy=True, labor costs are stripped (materials_only = total * (1 - ratio)).
LABOR_RATIOS: dict[str, float] = {
    "flooring_replace": 0.50,
    "flooring_refinish": 0.65,
    "flooring_repair": 0.70,
    "walls_repaint": 0.60,
    "walls_replaster": 0.55,
    "walls_remove_azulejos": 0.55,
    "walls_install_azulejos": 0.55,
    "walls_repair": 0.65,
    "ceiling_repaint": 0.60,
    "ceiling_repair": 0.60,
    "ceiling_replaster": 0.55,
    "windows_replace": 0.40,
    "windows_repair": 0.60,
    "doors_replace": 0.40,
    "doors_repair": 0.65,
    "kitchen_cabinets_replace": 0.35,
    "kitchen_cabinets_reface": 0.45,
    "kitchen_cabinets_repair": 0.60,
    "kitchen_countertop_replace": 0.45,
    "kitchen_countertop_repair": 0.65,
    "kitchen_appliances_install": 0.20,
    "bathroom_sanitary_replace": 0.50,
    "bathroom_sanitary_repair": 0.65,
    "bathroom_shower_replace": 0.45,
    "bathroom_shower_reseal": 0.75,
    "bathroom_tiles_replace": 0.55,
    "bathroom_tiles_repair": 0.70,
    "electrical_rewire": 0.65,
    "electrical_update": 0.70,
    "plumbing_replace": 0.70,
    "plumbing_repair": 0.75,
}

# --- Finish level cost multipliers ---
FINISH_LEVEL_MULTIPLIERS: dict[FinishLevel, float] = {
    FinishLevel.ECONOMICO: 0.7,
    FinishLevel.STANDARD: 1.0,
    FinishLevel.PREMIUM: 1.5,
}

# --- Room area weights (fraction of total usable area) ---
# Used to estimate room area when GPT doesn't provide it and no usable_area is available.
ROOM_AREA_WEIGHTS: dict[RoomType, float] = {
    RoomType.KITCHEN: 0.14,
    RoomType.LIVING_ROOM: 0.25,
    RoomType.BEDROOM: 0.16,
    RoomType.BATHROOM: 0.07,
    RoomType.HALLWAY: 0.08,
    RoomType.BALCONY: 0.06,
    RoomType.GARAGE: 0.15,
    RoomType.STORAGE: 0.05,
}

# --- Default fallback room area (m2) when all else fails ---
DEFAULT_ROOM_AREA_M2 = 10.0

# --- Regional cost multipliers ---
# Applied on top of base COST_TABLE prices.
LOCATION_COST_MULTIPLIERS: dict[LocationCostTier, float] = {
    LocationCostTier.LISBOA: 1.15,
    LocationCostTier.PORTO: 1.10,
    LocationCostTier.ALGARVE: 1.10,
    LocationCostTier.LITORAL: 1.0,
    LocationCostTier.INTERIOR: 0.85,
    LocationCostTier.ILHAS: 1.20,
}

# --- Floor accessibility labor surcharges ---
# Additional multiplier on labor cost for high-floor no-elevator situations.
FLOOR_ACCESSIBILITY_SURCHARGES: dict[str, float] = {
    "ground_floor": 0.0,
    "low_with_elevator": 0.0,
    "high_with_elevator": 0.03,
    "low_without_elevator": 0.05,
    "high_without_elevator": 0.10,
}

# --- Construction era MEP risk rules ---
# Maps era → whether rewiring / replumbing is likely needed.
# Used to derive estimated_rewiring_needed and estimated_replumbing_needed.
ERA_REWIRING_LIKELY: dict[ConstructionEra, bool] = {
    ConstructionEra.PRE_1950: True,
    ConstructionEra.ERA_1950_1970: True,
    ConstructionEra.ERA_1970_1990: True,
    ConstructionEra.ERA_1990_2005: False,
    ConstructionEra.POST_2005: False,
    ConstructionEra.UNKNOWN: False,
}

ERA_REPLUMBING_LIKELY: dict[ConstructionEra, bool] = {
    ConstructionEra.PRE_1950: True,
    ConstructionEra.ERA_1950_1970: True,
    ConstructionEra.ERA_1970_1990: False,
    ConstructionEra.ERA_1990_2005: False,
    ConstructionEra.POST_2005: False,
    ConstructionEra.UNKNOWN: False,
}

# --- Condition score thresholds for action decisions ---
# Scores are 1-5: 1=needs full replacement, 5=excellent/no work needed.
CONDITION_REPLACE_THRESHOLD = 2  # score <= 2 → replace
CONDITION_REPAIR_THRESHOLD = 3   # score == 3 → repair/refurbish
# score >= 4 → keep (no work)

# --- Work scope thresholds ---
# Average condition score for a module → WorkScope classification.
WORK_SCOPE_FROM_AVG_CONDITION: list[tuple[float, WorkScope]] = [
    (1.5, WorkScope.FULL_RENOVATION),
    (2.5, WorkScope.REPLACE),
    (3.5, WorkScope.REFURBISH),
    (4.5, WorkScope.REPAIR),
    (5.0, WorkScope.NONE),
]

# --- Time estimates per work scope (weeks) ---
TIME_WEEKS_PER_SCOPE: dict[WorkScope, tuple[int, int]] = {
    WorkScope.NONE: (0, 0),
    WorkScope.REPAIR: (1, 2),
    WorkScope.REFURBISH: (2, 4),
    WorkScope.REPLACE: (3, 6),
    WorkScope.FULL_RENOVATION: (4, 8),
}

# --- Countertop default linear meters (for cost calculation when area is known) ---
COUNTERTOP_DEFAULT_LINEAR_M = 3.0
