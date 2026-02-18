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

from app.models.property import ImageClassification, RoomCluster, RoomType
from app.prompts.renovation import IMAGE_CLASSIFICATION_PROMPT, ROOM_CLUSTERING_PROMPT

logger = logging.getLogger(__name__)

# Room types that can have multiple distinct physical rooms and benefit from vision clustering
MULTI_ROOM_TYPES: set[RoomType] = {RoomType.BEDROOM, RoomType.BATHROOM}

# Maximum images to send in a single clustering API call
MAX_CLUSTERING_IMAGES = 10


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

    def group_by_room_simple(
        self, classifications: list[ImageClassification]
    ) -> dict[str, list[ImageClassification]]:
        """
        Group classified images by room using the naive key-based approach.

        Groups by composite key ``{room_type}_{room_number}``. This is the
        original strategy — fast but unable to detect that multiple photos
        with room_number=1 may show different physical rooms.

        Kept as a reference implementation and for use in tests.

        Args:
            classifications: List of image classifications

        Returns:
            Dictionary mapping room keys (e.g., "cozinha_1", "quarto_2") to
            list of classifications for that room.
        """
        grouped: dict[str, list[ImageClassification]] = defaultdict(list)

        for classification in classifications:
            room_key = f"{classification.room_type.value}_{classification.room_number}"
            grouped[room_key].append(classification)

        return dict(grouped)

    async def cluster_room_images(
        self,
        room_type: RoomType,
        image_urls: list[str],
        image_detail: str = "low",
    ) -> list[RoomCluster]:
        """
        Use GPT-4o-mini vision to cluster photos of one room type into physical rooms.

        Sends all photos of the same room type (e.g. all bedroom photos) to GPT
        in a single call so it can compare them visually and determine which ones
        show the same physical room.

        Args:
            room_type: The room type being clustered (e.g. BEDROOM).
            image_urls: URLs of all images of this room type.
            image_detail: GPT image detail level ("low" or "auto").

        Returns:
            List of RoomCluster objects. On any failure returns a single cluster
            containing all images with confidence=0.3.
        """
        if len(image_urls) <= 1:
            return [
                RoomCluster(
                    room_number=1,
                    image_indices=list(range(len(image_urls))),
                    confidence=1.0,
                    visual_cues="",
                )
            ]

        # Get base label ("Quarto", "Casa de Banho") — split on space, take first word pair
        room_label = get_room_label(room_type, 1)
        prompt_text = ROOM_CLUSTERING_PROMPT.format(
            num_images=len(image_urls),
            room_type_label=room_label,
        )

        content: list[dict] = [{"type": "text", "text": prompt_text}]
        for url in image_urls:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": image_detail},
                }
            )

        try:
            async with self.semaphore:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )

            raw = response.choices[0].message.content
            data = json.loads(raw)

            raw_clusters = data.get("clusters", [])
            parsed: list[RoomCluster] = []
            for c in raw_clusters:
                parsed.append(
                    RoomCluster(
                        room_number=int(c.get("room_number", 1)),
                        image_indices=[int(i) for i in c.get("image_indices", [])],
                        confidence=float(c.get("confidence", 0.5)),
                        visual_cues=str(c.get("visual_cues", "")),
                    )
                )

            validated = self._validate_clusters(parsed, len(image_urls))
            if validated is None:
                logger.warning(
                    f"GPT clustering output invalid for {room_type.value}, "
                    "falling back to single-group"
                )
                return [
                    RoomCluster(
                        room_number=1,
                        image_indices=list(range(len(image_urls))),
                        confidence=0.3,
                        visual_cues="",
                    )
                ]
            return validated

        except Exception as e:
            logger.error(f"Error clustering {room_type.value} images: {e}")
            return [
                RoomCluster(
                    room_number=1,
                    image_indices=list(range(len(image_urls))),
                    confidence=0.3,
                    visual_cues="",
                )
            ]

    def _validate_clusters(
        self,
        clusters: list[RoomCluster],
        num_images: int,
    ) -> list[RoomCluster] | None:
        """
        Validate and normalise GPT clustering output.

        Rules:
        - Every index 0..num_images-1 must appear in exactly one cluster.
        - Duplicate or out-of-range indices → return None (signal fallback).
        - Missing indices → appended as individual singleton clusters.
        - room_numbers are re-sequenced 1..N at the end.

        Args:
            clusters: Raw clusters from GPT.
            num_images: Total number of images that were clustered.

        Returns:
            Validated and renumbered list, or None if GPT output is corrupt.
        """
        if not clusters:
            return None

        seen: set[int] = set()
        for cluster in clusters:
            for idx in cluster.image_indices:
                if idx < 0 or idx >= num_images:
                    logger.warning(f"Cluster index {idx} out of range [0, {num_images})")
                    return None
                if idx in seen:
                    logger.warning(f"Duplicate cluster index {idx}")
                    return None
                seen.add(idx)

        # Append any images GPT omitted as individual singleton clusters
        result = list(clusters)
        for missing_idx in range(num_images):
            if missing_idx not in seen:
                result.append(
                    RoomCluster(
                        room_number=len(result) + 1,
                        image_indices=[missing_idx],
                        confidence=0.5,
                        visual_cues="",
                    )
                )

        # Re-number sequentially 1..N
        for i, cluster in enumerate(result, start=1):
            cluster.room_number = i

        return result

    @staticmethod
    def _metadata_fallback(
        num_images: int,
        expected_rooms: int | None,
    ) -> list[RoomCluster]:
        """
        Create a safe fallback clustering when GPT is unavailable or fails.

        Strategy:
        - If expected_rooms is known: distribute images evenly across that many rooms.
        - If expected_rooms is None: one image per group (maximum under-grouping).

        Args:
            num_images: Total number of images to distribute.
            expected_rooms: Number of physical rooms expected (from property metadata).

        Returns:
            List of RoomCluster objects covering all images.
        """
        if num_images == 0:
            return []

        if expected_rooms is None or expected_rooms <= 0:
            return [
                RoomCluster(
                    room_number=i + 1,
                    image_indices=[i],
                    confidence=0.3,
                    visual_cues="",
                )
                for i in range(num_images)
            ]

        # Distribute as evenly as possible (e.g., 7 images / 3 rooms → 3, 2, 2)
        base, remainder = divmod(num_images, expected_rooms)
        clusters: list[RoomCluster] = []
        idx = 0
        for room_num in range(1, expected_rooms + 1):
            size = base + (1 if room_num <= remainder else 0)
            clusters.append(
                RoomCluster(
                    room_number=room_num,
                    image_indices=list(range(idx, idx + size)),
                    confidence=0.3,
                    visual_cues="",
                )
            )
            idx += size

        return clusters

    async def group_by_room(
        self,
        classifications: list[ImageClassification],
        num_rooms: int | None = None,
        num_bathrooms: int | None = None,
        image_detail: str = "low",
    ) -> dict[str, list[ImageClassification]]:
        """
        Group classified images by room using GPT vision clustering for multi-room types.

        Algorithm:
        1. Pass 1 — bucket by room_type (ignore existing room_number).
        2. Pass 2 — for BEDROOM and BATHROOM buckets with >1 image:
             - Send up to MAX_CLUSTERING_IMAGES to cluster_room_images().
             - For larger buckets: cluster the first batch, then handle overflow.
             - On failure: fall back to _metadata_fallback().
           Singleton-type buckets (KITCHEN, etc.) keep room_number=1.
        3. Run all clustering coroutines concurrently via asyncio.gather.

        Args:
            classifications: List of image classifications from classify_images().
            num_rooms: Number of bedrooms from property metadata (for fallback).
            num_bathrooms: Number of bathrooms from property metadata (for fallback).
            image_detail: GPT image detail level passed to cluster_room_images().

        Returns:
            Dictionary mapping room keys (e.g., "quarto_1", "quarto_2") to
            lists of ImageClassification objects.
        """
        if not classifications:
            return {}

        # Pass 1: bucket by room_type only
        type_buckets: dict[RoomType, list[ImageClassification]] = defaultdict(list)
        for c in classifications:
            type_buckets[c.room_type].append(c)

        # Separate types that need clustering from singletons
        cluster_tasks: list[tuple[RoomType, list[ImageClassification], int | None]] = []
        non_multi_buckets: dict[RoomType, list[ImageClassification]] = {}

        for room_type, items in type_buckets.items():
            if room_type in MULTI_ROOM_TYPES and len(items) > 1:
                expected = num_rooms if room_type == RoomType.BEDROOM else num_bathrooms
                cluster_tasks.append((room_type, items, expected))
            else:
                non_multi_buckets[room_type] = items

        # Pass 2: run clustering concurrently
        async def _cluster_one(
            room_type: RoomType,
            items: list[ImageClassification],
            expected_rooms: int | None,
        ) -> tuple[RoomType, list[RoomCluster]]:
            urls = [c.image_url for c in items]

            if len(urls) <= MAX_CLUSTERING_IMAGES:
                clusters = await self.cluster_room_images(room_type, urls, image_detail)
            else:
                first_batch = urls[:MAX_CLUSTERING_IMAGES]
                first_clusters = await self.cluster_room_images(
                    room_type, first_batch, image_detail
                )

                overflow_urls = urls[MAX_CLUSTERING_IMAGES:]
                overflow_start = MAX_CLUSTERING_IMAGES

                if expected_rooms is not None and len(first_clusters) >= expected_rooms:
                    # Distribute overflow sequentially across existing clusters
                    for overflow_offset, _ in enumerate(overflow_urls):
                        target = first_clusters[overflow_offset % len(first_clusters)]
                        target.image_indices.append(overflow_start + overflow_offset)
                    clusters = first_clusters
                else:
                    # Run a second pass on the overflow to find additional rooms
                    second_clusters = await self.cluster_room_images(
                        room_type, overflow_urls, image_detail
                    )
                    room_num_offset = len(first_clusters)
                    offset_second = [
                        RoomCluster(
                            room_number=sc.room_number + room_num_offset,
                            image_indices=[
                                idx + overflow_start for idx in sc.image_indices
                            ],
                            confidence=sc.confidence,
                            visual_cues=sc.visual_cues,
                        )
                        for sc in second_clusters
                    ]
                    clusters = first_clusters + offset_second

            validated = self._validate_clusters(clusters, len(items))
            if validated is None:
                validated = self._metadata_fallback(len(items), expected_rooms)

            return room_type, validated

        clustering_results: dict[RoomType, list[RoomCluster]] = {}
        if cluster_tasks:
            results = await asyncio.gather(
                *[_cluster_one(rt, items, exp) for rt, items, exp in cluster_tasks]
            )
            for room_type, clusters in results:
                clustering_results[room_type] = clusters

        # Pass 3: build the final grouped dict
        grouped: dict[str, list[ImageClassification]] = {}

        # Non-multi types: all images into room_number=1
        for room_type, items in non_multi_buckets.items():
            room_key = f"{room_type.value}_1"
            grouped[room_key] = items

        # Multi types: map each ImageClassification to its cluster
        for room_type, items, _ in cluster_tasks:
            clusters = clustering_results.get(room_type, [])
            if not clusters:
                clusters = self._metadata_fallback(len(items), None)
            for cluster in clusters:
                room_key = f"{room_type.value}_{cluster.room_number}"
                grouped[room_key] = [items[i] for i in cluster.image_indices]

        return grouped


# Factory function for dependency injection
def create_image_classifier(
    openai_api_key: str, model: str = "gpt-4o-mini"
) -> ImageClassifierService:
    """Create an ImageClassifierService instance."""
    return ImageClassifierService(openai_api_key, model)
