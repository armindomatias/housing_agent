"""
Idealista scraping service using Apify.

This service fetches property data from Idealista listings using the
dz_omar/idealista-scraper-api Apify actor in STANDBY mode. A single POST
returns results directly via NDJSON — no polling required.
Then parsed and return the PropertyData pydantic model

Usage:
    service = IdealistaService(apify_token="...")
    property_data = await service.scrape_property("https://www.idealista.pt/imovel/...")
"""

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import ApifyConfig
from app.models.property import PropertyData

logger = logging.getLogger(__name__)


class IdealistaService:
    """Service for scraping property data from Idealista using Apify."""

    def __init__(self, apify_token: str, apify_config: ApifyConfig | None = None):
        """
        Initialize the Idealista service.

        Args:
            apify_token:  Apify API token for authentication
            apify_config: Apify operational config (URL, retries, timeouts).
        """
        self.apify_token = apify_token
        self.apify_config = apify_config or ApifyConfig()
        self._client = httpx.AsyncClient(
            timeout=self.apify_config.request_timeout_seconds
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    def _validate_url(self, url: str) -> bool:
        """
        Validate that the URL is a valid Idealista property listing.

        Args:
            url: URL to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            parsed = urlparse(url)
            if not parsed.netloc.endswith("idealista.pt"):
                return False
            if "/imovel/" not in parsed.path:
                return False
            return True
        except Exception:
            return False

    def _extract_property_id(self, url: str) -> str | None:
        """
        Extract the property ID from an Idealista URL.

        Args:
            url: Idealista property URL

        Returns:
            Property ID string or None if not found
        """
        match = re.search(r"/imovel/(\d+)", url)
        return match.group(1) if match else None

    @staticmethod
    def _parse_ndjson_response(text: str) -> list[dict]:
        """
        Parse a newline-delimited JSON response into a list of dicts.

        Args:
            text: Raw NDJSON string (one JSON object per line)

        Returns:
            List of parsed dictionaries
        """
        results: list[dict] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            results.append(json.loads(stripped))
        return results

    # Method that calls the Apify Actor 
    async def _request_with_retry(self, url: str, payload: dict) -> httpx.Response:
        """
        POST to the given URL with retry logic for transient failures.

        Retries up to MAX_RETRIES times with exponential backoff on:
        - HTTP 5xx errors
        - Timeout errors
        - Connection errors

        Does NOT retry on 4xx errors or ValueErrors.

        Args:
            url: The endpoint URL
            payload: JSON body to send

        Returns:
            httpx.Response on success

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors or exhausted retries
            httpx.TimeoutException: If all retries time out
            httpx.ConnectError: If all retries fail to connect
        """
        last_exception: Exception | None = None
        max_retries = self.apify_config.max_retries
        retry_base_delay = self.apify_config.retry_base_delay_seconds

        for attempt in range(max_retries):
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.apify_token}"},
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
                last_exception = exc
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exception = exc

            delay = retry_base_delay * (2 ** attempt)
            logger.warning(
                "Apify request attempt %d/%d failed: %s. Retrying in %ds...",
                attempt + 1,
                max_retries,
                last_exception,
                delay,
            )
            await asyncio.sleep(delay)

        raise last_exception  # type: ignore[misc]

    # Method that controls the whole process of scraping and parsing the data 
    async def scrape_property(self, url: str) -> PropertyData:
        """
        Scrape property data from an Idealista listing.

        Uses the dz_omar/idealista-scraper-api actor in STANDBY mode.

        Args:
            url: Full Idealista property URL

        Returns:
            PropertyData object with scraped information

        Raises:
            ValueError: If URL is invalid or property cannot be found
            httpx.HTTPError: If Apify API request fails after retries
        """
        if not self._validate_url(url):
            raise ValueError(
                "URL inválido. Deve ser um anúncio do Idealista Portugal "
                "(ex: https://www.idealista.pt/imovel/12345678/)"
            )

        property_id = self._extract_property_id(url)
        if not property_id:
            raise ValueError("Não foi possível extrair o ID do imóvel do URL")

        if not self.apify_token:
            return self._get_mock_data(url, property_id)

        payload = {"Property_urls": [{"url": url}]}
        response = await self._request_with_retry(self.apify_config.standby_url, payload)

        items = self._parse_ndjson_response(response.text)

        if not items:
            raise ValueError(f"Não foi possível obter dados do imóvel {property_id}")

        # Find the property data item (type: "property")
        property_item = next(
            (item for item in items if item.get("type") == "property"),
            None
        )

        if not property_item:
            raise ValueError(f"Não foi possível obter dados do imóvel {property_id}")

        # Check for actor-level failure
        if property_item.get("status") == "failed":
            error_msg = property_item.get("error", "Unknown error")
            raise ValueError(
                f"O scraper não conseguiu extrair dados do imóvel: {error_msg}"
            )

        # Extract the actual data from the property item
        property_data = property_item.get("data", {})
        return self._parse_apify_result(url, property_data)

    def _parse_apify_result(self, url: str, data: dict) -> PropertyData:
        """
        Parse dz_omar/idealista-scraper-api result into PropertyData.

        Args:
            url: Original property URL
            data: Raw data from the actor

        Returns:
            PropertyData model instance
        """
        more = data.get("moreCharacteristics", {}) or {}
        ubication = data.get("ubication", {}) or {}
        price_info = data.get("priceInfo", {}) or {}
        multimedia = data.get("multimedia", {}) or {}

        images_raw = multimedia.get("images", []) or []
        image_urls = [img["url"] for img in images_raw if isinstance(img, dict) and "url" in img]
        image_tags = {
            img["url"]: img["tag"]
            for img in images_raw
            if isinstance(img, dict) and "url" in img and "tag" in img
        }

        # Location: join city and region
        location_parts = []
        city = ubication.get("administrativeAreaLevel2", "")
        region = ubication.get("administrativeAreaLevel1", "")
        if city:
            location_parts.append(city)
        if region:
            location_parts.append(region)

        # Extract orientation from translated texts if available
        orientation = ""
        translated_texts = data.get("translatedTexts", {}) or {}
        char_descriptions = translated_texts.get("characteristicsDescriptions", []) or []
        for desc_group in char_descriptions:
            if desc_group.get("key") == "features":
                for feature in desc_group.get("detailFeatures", []):
                    phrase = feature.get("phrase", "").lower()
                    if "orientation" in phrase:
                        # Extract orientation value (e.g., "Orientation west" -> "west")
                        orientation = phrase.split("orientation")[-1].strip()
                        break

        # Calculate price per m2
        price = float(price_info.get("amount", 0) or data.get("price", 0))
        constructed_area = float(more.get("constructedArea", 0))
        price_per_m2 = round(price / constructed_area, 2) if constructed_area > 0 else 0

        # Extract videos and virtual tours
        videos = multimedia.get("videos", []) or []
        virtual_tours = multimedia.get("virtual3DTours", []) or []

        return PropertyData(
            url=url,
            title=data.get("title") or ubication.get("title", ""),
            price=price,
            area_m2=constructed_area,
            usable_area_m2=float(more.get("usableArea", 0)),
            num_rooms=int(more.get("roomNumber", 0)),
            num_bathrooms=int(more.get("bathNumber", 0)),
            floor=str(more.get("floor", "")),
            location=", ".join(location_parts),
            description=data.get("propertyComment", ""),
            image_urls=image_urls,
            operation=data.get("operation", ""),
            property_type=data.get("extendedPropertyType", ""),
            latitude=ubication.get("latitude"),
            longitude=ubication.get("longitude"),
            image_tags=image_tags,
            has_elevator=more.get("lift"),
            condition_status=str(more.get("status", "")),
            # Additional features
            energy_certificate=str(more.get("energyCertificationType", "")),
            has_swimming_pool=bool(more.get("swimmingPool", False)),
            has_garden=bool(more.get("garden", False)),
            has_boxroom=bool(more.get("boxroom", False)),
            is_duplex=bool(more.get("isDuplex", False)),
            is_penthouse=bool(more.get("isPenthouse", False)),
            is_studio=bool(more.get("isStudio", False)),
            furniture_status=str(more.get("housingFurnitures", "")),
            orientation=orientation,
            price_per_m2=price_per_m2,
            # Rich media
            videos=videos,
            virtual_tours=virtual_tours,
            raw_data=data,
        )

    def _get_mock_data(self, url: str, property_id: str) -> PropertyData:
        """
        Return mock data for development when no Apify token is available.

        Args:
            url: Property URL
            property_id: Extracted property ID

        Returns:
            Mock PropertyData for testing
        """
        mock_images = [
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8b/1204330314.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8c/1204330315.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8d/1204330316.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8e/1204330317.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8f/1204330318.jpg",
        ]

        mock_image_tags = {
            mock_images[0]: "kitchen",
            mock_images[1]: "bedroom",
            mock_images[2]: "bathroom",
            mock_images[3]: "living_room",
            mock_images[4]: "exterior",
        }

        return PropertyData(
            url=url,
            title=f"Apartamento T2 para venda - Mock {property_id}",
            price=185000.0,
            area_m2=75.0,
            usable_area_m2=68.0,
            num_rooms=2,
            num_bathrooms=1,
            floor="3",
            location="Lisboa, Arroios",
            description=(
                "Apartamento T2 com 75m² em prédio de 1960. "
                "Necessita de algumas obras de modernização. "
                "Cozinha e casa de banho originais."
            ),
            image_urls=mock_images,
            operation="sale",
            property_type="flat",
            latitude=38.7223,
            longitude=-9.1393,
            image_tags=mock_image_tags,
            has_elevator=False,
            condition_status="good",
            # Additional features
            energy_certificate="d",
            has_swimming_pool=False,
            has_garden=False,
            has_boxroom=False,
            is_duplex=False,
            is_penthouse=False,
            is_studio=False,
            furniture_status="unfurnished",
            orientation="south",
            price_per_m2=2466.67,
            # Rich media
            videos=[],
            virtual_tours=[],
            raw_data={"mock": True, "property_id": property_id},
        )


def create_idealista_service(
    apify_token: str, apify_config: ApifyConfig | None = None
) -> IdealistaService:
    """Create an IdealistaService instance."""
    return IdealistaService(apify_token, apify_config)


if __name__ == "__main__":
    apify_token = None
    idealista_service = IdealistaService(apify_token=apify_token)

    idealista_url = "https://www.idealista.pt/imovel/34810407/"
    property_data = asyncio.run(idealista_service.scrape_property(url=idealista_url))
    print(property_data)