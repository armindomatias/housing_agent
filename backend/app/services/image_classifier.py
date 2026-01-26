"""
Image classification service using GPT-4 Vision.

This service classifies property images to identify which room type they show.
It handles the two-phase process:
1. Classify each image individually
2. Group images by room type for deduplication

The grouping is important because property listings often have multiple photos
of the same room from different angles. We want to analyze all photos of a room
together but only generate ONE estimate per room.

Usage:
    classifier = ImageClassifierService(openai_api_key="...")
    classifications = await classifier.classify_images(image_urls)
    grouped = classifier.group_by_room(classifications)
"""

import asyncio
import json
import logging
from collections import defaultdict

from openai import AsyncOpenAI

from app.models.property import ImageClassification, RoomType
from app.prompts.renovation import IMAGE_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)


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
                    room_number=int(data.get("room_number", 1)),
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
        self, image_urls: list[str], progress_callback=None
    ) -> list[ImageClassification]:
        """
        Classify multiple images concurrently.

        Args:
            image_urls: List of image URLs to classify
            progress_callback: Optional async callback(current, total, classification)
                              called after each image is classified

        Returns:
            List of ImageClassification objects
        """
        classifications = []
        total = len(image_urls)

        # Create tasks for all images
        tasks = [self.classify_single_image(url) for url in image_urls]

        # Process with progress tracking
        for i, task in enumerate(asyncio.as_completed(tasks)):
            classification = await task
            classifications.append(classification)

            if progress_callback:
                await progress_callback(i + 1, total, classification)

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

    def get_room_label(self, room_type: RoomType, room_number: int) -> str:
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


# Factory function for dependency injection
def create_image_classifier(
    openai_api_key: str, model: str = "gpt-4o-mini"
) -> ImageClassifierService:
    """Create an ImageClassifierService instance."""
    return ImageClassifierService(openai_api_key, model)
