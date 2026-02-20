"""
Business logic constants for the Rehabify application.

These values are stable across environments (dev/staging/prod) and do not
need env-var overrides. For operational parameters that vary per environment
(timeouts, concurrency limits, max_tokens), see config.py.
"""

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
    "office": RoomType.OTHER,
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
