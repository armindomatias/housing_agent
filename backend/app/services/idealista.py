"""
Idealista scraping service using Apify.

This service fetches property data from Idealista listings using the
dz_omar/idealista-scraper-api Apify actor in STANDBY mode. A single POST
returns results directly via NDJSON — no polling required.

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

from app.models.property import PropertyData

logger = logging.getLogger(__name__)

APIFY_STANDBY_URL = "https://dz-omar--idealista-scraper-api.apify.actor/"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


class IdealistaService:
    """Service for scraping property data from Idealista using Apify."""

    def __init__(self, apify_token: str):
        """
        Initialize the Idealista service.

        Args:
            apify_token: Apify API token for authentication
        """
        self.apify_token = apify_token
        self._client = httpx.AsyncClient(timeout=120.0)

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

        for attempt in range(MAX_RETRIES):
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

            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Apify request attempt %d/%d failed: %s. Retrying in %ds...",
                attempt + 1,
                MAX_RETRIES,
                last_exception,
                delay,
            )
            await asyncio.sleep(delay)

        raise last_exception  # type: ignore[misc]

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
        response = await self._request_with_retry(APIFY_STANDBY_URL, payload)

        items = self._parse_ndjson_response(response.text)

        if not items:
            raise ValueError(f"Não foi possível obter dados do imóvel {property_id}")

        # Check for actor-level failure
        if items[0].get("status") == "failed":
            error_msg = items[0].get("error", "Unknown error")
            raise ValueError(
                f"O scraper não conseguiu extrair dados do imóvel: {error_msg}"
            )

        return self._parse_apify_result(url, items[0])

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

        return PropertyData(
            url=url,
            title=data.get("title") or ubication.get("title", ""),
            price=float(price_info.get("amount", 0) or data.get("price", 0)),
            area_m2=float(more.get("constructedArea", 0)),
            num_rooms=int(more.get("roomNumber", 0)),
            num_bathrooms=int(more.get("bathNumber", 0)),
            floor=str(more.get("floor", "")),
            location=", ".join(location_parts),
            description=data.get("description", ""),
            image_urls=image_urls,
            operation=data.get("operation", ""),
            property_type=data.get("extendedPropertyType", ""),
            latitude=ubication.get("latitude"),
            longitude=ubication.get("longitude"),
            image_tags=image_tags,
            has_elevator=more.get("lift"),
            condition_status=str(more.get("status", "")),
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
            raw_data={"mock": True, "property_id": property_id},
        )


def create_idealista_service(apify_token: str) -> IdealistaService:
    """Create an IdealistaService instance."""
    return IdealistaService(apify_token)
