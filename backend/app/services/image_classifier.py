"""
Image classification service using GPT-4 Vision.

Classifies property images into room types and groups them for deduplication.
Because a listing often contains multiple photos of the same room, grouping
ensures we generate exactly one estimate per room, not one per photo.

## Classification strategy

Two-phase approach, ordered cheapest-first:

1. **Tag phase (free):** Idealista listings scraped via Apify include a "tag"
   field on each image (e.g. "kitchen", "bedroom"). When a tag maps to a known
   RoomType we produce an ImageClassification instantly without any API call.
   A typical listing saves 60–80 % of classification costs this way.

2. **GPT phase (paid):** Images with no tag or an unrecognised tag are sent
   to GPT-4o-mini with `detail="low"` for cost efficiency.  Up to
   `max_concurrent` calls run in parallel, rate-limited by a semaphore.

Flow:
    tagged images    →  classify_from_tag()       →  ImageClassification (confidence=0.9)
    untagged images  →  classify_single_image()   →  ImageClassification (GPT-scored confidence)

Usage:
    classifier = ImageClassifierService(openai_api_key="...")

    classifications = await classifier.classify_images(
        image_urls, image_tags=property_data.image_tags
    )
    grouped = classifier.group_by_room(classifications)

    # Standalone label helper usable anywhere without a service instance:
    label = get_room_label(RoomType.BEDROOM, 2)  # -> "Quarto 2"
"""

import asyncio
import json
import logging
from collections import defaultdict

from openai import AsyncOpenAI

from app.models.property import ImageClassification, RoomType
from app.prompts.renovation import IMAGE_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)


def get_room_label(room_type: RoomType, room_number: int) -> str:
    """
    Get a human-readable label for a room.

    Args:
        room_type: Type of room
        room_number: Room number

    Returns:
        Human-readable label in Portuguese, e.g., "Cozinha", "Quarto 1"
    """
    labels = {
        RoomType.KITCHEN: "Cozinha",
        RoomType.LIVING_ROOM: "Sala",
        RoomType.BEDROOM: "Quarto",
        RoomType.BATHROOM: "Casa de Banho",
        RoomType.HALLWAY: "Corredor",
        RoomType.BALCONY: "Varanda",
        RoomType.EXTERIOR: "Exterior",
        RoomType.GARAGE: "Garagem",
        RoomType.STORAGE: "Arrecadação",
        RoomType.OTHER: "Outro",
    }

    base_label = labels.get(room_type, "Outro")

    # Add number for rooms that can have multiples
    if room_type in [RoomType.BEDROOM, RoomType.BATHROOM] and room_number > 0:
        return f"{base_label} {room_number}"

    return base_label


# ---------------------------------------------------------------------------
# Apify tag → RoomType mapping
# ---------------------------------------------------------------------------
# Apify's Idealista scraper attaches a "tag" string (English) to each image,
# mirroring the label Idealista itself assigns. Every known tag is mapped here;
# any tag absent from this dict falls back to GPT classification.
#
# room_number is always 1 for tag-based results because Apify tags carry no
# numbering (e.g., "bedroom" not "bedroom_2").  Multiple bedroom photos end up
# grouped under "quarto_1" — still correct for estimation purposes.
# ---------------------------------------------------------------------------
_APIFY_TAG_MAP: dict[str, RoomType] = {
    "kitchen": RoomType.KITCHEN,
    "bedroom": RoomType.BEDROOM,
    "bathroom": RoomType.BATHROOM,
    "livingroom": RoomType.LIVING_ROOM,      # normalised (strip spaces/dashes)
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
}


def classify_from_tag(image_url: str, tag: str) -> ImageClassification | None:
    """
    Classify an image using Apify's free tag metadata — no GPT call needed.

    Apify's Idealista actor attaches a "tag" string to every image. When the
    tag maps to a known RoomType we return an ImageClassification directly at
    confidence=0.9 (slightly below 1.0 to signal it wasn't manually verified).

    Args:
        image_url: URL of the image (used as identifier in the result).
        tag: Raw tag string from Apify (e.g. "kitchen", "bedroom").

    Returns:
        ImageClassification if the tag is mappable, None otherwise.
        Callers that receive None should send the image to GPT.
    """
    # Normalise: lowercase + strip whitespace
    normalised = tag.strip().lower()
    room_type = _APIFY_TAG_MAP.get(normalised)

    if room_type is None:
        return None  # Unknown tag — caller must fall back to GPT

    return ImageClassification(
        image_url=image_url,
        room_type=room_type,
        room_number=1,      # Apify tags carry no room-number information
        confidence=0.9,     # High confidence but not 1.0 (not human-verified)
    )


class ImageClassifierService:
    """Service for classifying property images using GPT-4 Vision."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o-mini",  # Use mini for classification (cheaper, fast enough)
        max_concurrent: int = 5,  # Limit concurrent API calls
    ):
        """
        Initialize the image classifier.

        Args:
            openai_api_key: OpenAI API key
            model: Model to use for classification (default: gpt-4o-mini for cost efficiency)
            max_concurrent: Maximum concurrent API calls to prevent rate limiting
        """
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def classify_single_image(self, image_url: str) -> ImageClassification:
        """
        Classify a single image to identify the room type.

        Args:
            image_url: URL of the image to classify

        Returns:
            ImageClassification with room type and confidence
        """
        async with self.semaphore:  # Rate limiting
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": IMAGE_CLASSIFICATION_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url, "detail": "low"},
                                },
                            ],
                        }
                    ],
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )

                # Parse the JSON response
                content = response.choices[0].message.content
                data = json.loads(content)

                # Map the room type string to our enum
                room_type_str = data.get("room_type", "outro").lower()
                room_type = self._map_room_type(room_type_str)

                return ImageClassification(
                    image_url=image_url,
                    room_type=room_type,
                    room_number=max(1, int(data.get("room_number") or 1)),
                    confidence=float(data.get("confidence", 0.5)),
                )

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse classification JSON for {image_url}: {e}")
                return ImageClassification(
                    image_url=image_url,
                    room_type=RoomType.OTHER,
                    room_number=1,
                    confidence=0.0,
                )
            except Exception as e:
                logger.error(f"Error classifying image {image_url}: {e}")
                return ImageClassification(
                    image_url=image_url,
                    room_type=RoomType.OTHER,
                    room_number=1,
                    confidence=0.0,
                )

    def _map_room_type(self, room_type_str: str) -> RoomType:
        """
        Map a room type string to the RoomType enum.

        Args:
            room_type_str: Room type string from GPT response

        Returns:
            Corresponding RoomType enum value
        """
        mapping = {
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
        }
        return mapping.get(room_type_str.lower(), RoomType.OTHER)

    async def classify_images(
        self,
        image_urls: list[str],
        image_tags: dict[str, str] | None = None,
        progress_callback=None,
    ) -> list[ImageClassification]:
        """
        Classify multiple images, using Apify tags to skip GPT where possible.

        Two-phase strategy:
        1. Tag phase (free): for each URL that has a known Apify tag, call
           classify_from_tag(). These complete instantly with confidence=0.9.
        2. GPT phase (paid): URLs with no tag or an unknown tag are sent to
           classify_single_image() concurrently, respecting the semaphore.

        Progress callbacks are fired for EVERY image regardless of which phase
        classified it, so the frontend counter is always accurate.

        Args:
            image_urls:      Ordered list of image URLs to classify.
            image_tags:      Optional dict mapping image URL → Apify tag string.
                             When None, all images go through GPT (original behaviour).
            progress_callback: Optional async callback(current, total, classification)
                               called after each image is classified.

        Returns:
            List of ImageClassification objects (order matches image_urls).
        """
        classifications: list[ImageClassification] = []
        total = len(image_urls)
        completed = 0

        # --- Phase 1: Tag-based classification (no API cost) ---
        tagged: list[ImageClassification] = []
        untagged_urls: list[str] = []

        if image_tags:
            for url in image_urls:
                tag = image_tags.get(url)
                if tag:
                    result = classify_from_tag(url, tag)
                    if result is not None:
                        tagged.append(result)
                        continue
                untagged_urls.append(url)

            logger.info(
                f"Classification strategy: {len(tagged)} tag-based (free), "
                f"{len(untagged_urls)} via GPT"
            )
        else:
            # No tags provided — all images need GPT
            untagged_urls = list(image_urls)

        # Emit progress for tag-classified images first
        for classification in tagged:
            classifications.append(classification)
            completed += 1
            if progress_callback:
                await progress_callback(completed, total, classification)

        # --- Phase 2: GPT-based classification (concurrent, rate-limited) ---
        if untagged_urls:
            tasks = [self.classify_single_image(url) for url in untagged_urls]
            for task in asyncio.as_completed(tasks):
                classification = await task
                classifications.append(classification)
                completed += 1
                if progress_callback:
                    await progress_callback(completed, total, classification)

        return classifications

    def group_by_room(
        self, classifications: list[ImageClassification]
    ) -> dict[str, list[ImageClassification]]:
        """
        Group classified images by room.

        This is crucial for avoiding duplicate estimates. Multiple photos of the same
        kitchen should be grouped together and analyzed as ONE kitchen, not counted
        as multiple kitchens.

        Args:
            classifications: List of image classifications

        Returns:
            Dictionary mapping room keys (e.g., "cozinha_1", "quarto_2") to list of
            classifications for that room
        """
        grouped: dict[str, list[ImageClassification]] = defaultdict(list)

        for classification in classifications:
            # Create a unique key for this room
            # e.g., "cozinha_1", "quarto_1", "quarto_2", "casa_de_banho_1"
            room_key = f"{classification.room_type.value}_{classification.room_number}"
            grouped[room_key].append(classification)

        return dict(grouped)
