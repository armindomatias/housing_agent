"""
Idealista scraping service using Apify.

This service fetches property data from Idealista listings using Apify's web scraping
infrastructure. Apify handles the actual scraping, which helps with legal compliance
and maintenance since we're using a third-party service.

Usage:
    service = IdealistaService(apify_token="...")
    property_data = await service.scrape_property("https://www.idealista.pt/imovel/...")
"""

import re
from urllib.parse import urlparse

import httpx

from app.models.property import PropertyData


class IdealistaService:
    """Service for scraping property data from Idealista using Apify."""

    # Apify actor for Idealista scraping (public actor)
    # Note: This is a commonly used public actor for Idealista scraping
    APIFY_ACTOR_ID = "jupri/idealista-scraper"
    APIFY_API_URL = "https://api.apify.com/v2"

    def __init__(self, apify_token: str):
        """
        Initialize the Idealista service.

        Args:
            apify_token: Apify API token for authentication
        """
        self.apify_token = apify_token
        self._client = httpx.AsyncClient(timeout=120.0)  # Long timeout for scraping

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
            # Must be idealista.pt domain
            if not parsed.netloc.endswith("idealista.pt"):
                return False
            # Must be an individual property listing (contains /imovel/)
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
        # Pattern: /imovel/12345678/
        match = re.search(r"/imovel/(\d+)", url)
        return match.group(1) if match else None

    async def scrape_property(self, url: str) -> PropertyData:
        """
        Scrape property data from an Idealista listing.

        This method uses Apify to fetch the property data. The actor runs synchronously
        and returns the scraped data.

        Args:
            url: Full Idealista property URL

        Returns:
            PropertyData object with scraped information

        Raises:
            ValueError: If URL is invalid or property cannot be found
            httpx.HTTPError: If Apify API request fails
        """
        if not self._validate_url(url):
            raise ValueError(
                f"URL inválido. Deve ser um anúncio do Idealista Portugal "
                f"(ex: https://www.idealista.pt/imovel/12345678/)"
            )

        property_id = self._extract_property_id(url)
        if not property_id:
            raise ValueError("Não foi possível extrair o ID do imóvel do URL")

        # If no Apify token, return mock data for development
        if not self.apify_token:
            return self._get_mock_data(url, property_id)

        # Run Apify actor to scrape the property
        actor_input = {
            "startUrls": [{"url": url}],
            "maxItems": 1,
            "proxy": {"useApifyProxy": True},
        }

        # Start actor run
        run_url = f"{self.APIFY_API_URL}/acts/{self.APIFY_ACTOR_ID}/runs"
        response = await self._client.post(
            run_url,
            params={"token": self.apify_token},
            json=actor_input,
        )
        response.raise_for_status()
        run_data = response.json()
        run_id = run_data["data"]["id"]

        # Wait for run to complete and get results
        dataset_url = f"{self.APIFY_API_URL}/actor-runs/{run_id}/dataset/items"
        response = await self._client.get(
            dataset_url,
            params={"token": self.apify_token},
        )
        response.raise_for_status()
        items = response.json()

        if not items:
            raise ValueError(f"Não foi possível obter dados do imóvel {property_id}")

        return self._parse_apify_result(url, items[0])

    def _parse_apify_result(self, url: str, data: dict) -> PropertyData:
        """
        Parse Apify scraping result into PropertyData model.

        Args:
            url: Original property URL
            data: Raw data from Apify actor

        Returns:
            PropertyData model instance
        """
        # Extract image URLs from various possible field names
        images = []
        for key in ["images", "photos", "multimedia", "imageUrls"]:
            if key in data and data[key]:
                if isinstance(data[key], list):
                    for img in data[key]:
                        if isinstance(img, str):
                            images.append(img)
                        elif isinstance(img, dict) and "url" in img:
                            images.append(img["url"])
                break

        return PropertyData(
            url=url,
            title=data.get("title", data.get("propertyTitle", "")),
            price=float(data.get("price", data.get("priceInfo", {}).get("price", 0))),
            area_m2=float(data.get("size", data.get("area", 0))),
            num_rooms=int(data.get("rooms", data.get("bedrooms", 0))),
            num_bathrooms=int(data.get("bathrooms", 0)),
            floor=str(data.get("floor", "")),
            location=data.get("address", data.get("location", "")),
            description=data.get("description", data.get("propertyComment", "")),
            image_urls=images,
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
        # Sample images from a real-looking property (using placeholder URLs)
        mock_images = [
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8b/1204330314.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8c/1204330315.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8d/1204330316.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8e/1204330317.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/d4/a7/8f/1204330318.jpg",
        ]

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
            raw_data={"mock": True, "property_id": property_id},
        )


# Factory function for dependency injection
def create_idealista_service(apify_token: str) -> IdealistaService:
    """Create an IdealistaService instance."""
    return IdealistaService(apify_token)
