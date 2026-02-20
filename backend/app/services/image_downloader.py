"""
Image downloader service — fetches images from URLs and converts them to base64 data URIs.

Downloading images once at the start of the pipeline eliminates repeated CDN fetches
across the classify → cluster → estimate stages, preventing rate-limiting and
anti-hotlinking blocks from the Idealista CDN.

Usage:
    downloader = ImageDownloaderService()
    image_data = await downloader.download_images(urls)
    # Returns: {"https://cdn.example.com/img.jpg": "data:image/jpeg;base64,/9j/..."}
    # On download failure: URL is absent from the returned dict.
"""

import asyncio
import base64

import httpx
import structlog

from app.config import ImageProcessingConfig
from app.constants import DEFAULT_IMAGE_CONTENT_TYPE, KNOWN_IMAGE_TYPES

logger = structlog.get_logger(__name__)


class ImageDownloaderService:
    """
    Downloads images from URLs and converts them to base64 data URIs.

    Each image is fetched exactly once and stored as a data URI so that
    downstream OpenAI calls receive inline image data instead of external URLs.
    """

    def __init__(self, config: ImageProcessingConfig | None = None):
        """
        Initialize the image downloader.

        Args:
            config: Image processing configuration (limits, timeouts, concurrency).
                    Defaults to ImageProcessingConfig() with built-in defaults.
        """
        self.config = config or ImageProcessingConfig()

    async def download_images(self, urls: list[str]) -> dict[str, str]:
        """
        Download images concurrently and return a mapping of URL → base64 data URI.

        Only the first config.max_images_in_memory URLs are processed. Failed
        downloads are omitted from the result — callers should fall back to the
        original URL in that case.

        Args:
            urls: List of image URLs to download.

        Returns:
            Dict mapping each successfully downloaded URL to its base64 data URI,
            e.g. ``{"https://cdn.example.com/img.jpg": "data:image/jpeg;base64,..."}``
        """
        if not urls:
            return {}

        max_images = self.config.max_images_in_memory
        capped_urls = urls[:max_images]
        if len(urls) > max_images:
            logger.warning(
                "image_downloader_cap_exceeded",
                total=len(urls),
                cap=max_images,
            )

        semaphore = asyncio.Semaphore(self.config.max_concurrent_downloads)
        timeout = httpx.Timeout(self.config.download_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            tasks = [self._fetch_one(client, semaphore, url) for url in capped_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        image_data: dict[str, str] = {}
        for url, result in zip(capped_urls, results):
            if isinstance(result, str):
                image_data[url] = result
            # Exceptions are already logged inside _fetch_one; just skip here.

        logger.info(
            "image_downloader_complete",
            total=len(capped_urls),
            succeeded=len(image_data),
            failed=len(capped_urls) - len(image_data),
        )
        return image_data

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        url: str,
    ) -> str:
        """
        Fetch a single image and return it as a base64 data URI.

        Args:
            client:    Shared httpx client.
            semaphore: Concurrency limiter.
            url:       Image URL to fetch.

        Returns:
            Base64 data URI string, e.g. ``"data:image/jpeg;base64,/9j/..."``

        Raises:
            Exception: On any network or HTTP error (caller handles via gather).
        """
        async with semaphore:
            try:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", DEFAULT_IMAGE_CONTENT_TYPE)
                # Strip parameters like "; charset=utf-8"
                mime_type = content_type.split(";")[0].strip()
                if mime_type not in KNOWN_IMAGE_TYPES:
                    mime_type = DEFAULT_IMAGE_CONTENT_TYPE

                encoded = base64.b64encode(response.content).decode("ascii")
                data_uri = f"data:{mime_type};base64,{encoded}"
                logger.debug("image_downloaded", url=url, mime_type=mime_type, bytes=len(response.content))
                return data_uri

            except Exception as e:
                logger.warning("image_download_failed", url=url, error=str(e))
                raise
