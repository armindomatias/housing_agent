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

logger = structlog.get_logger(__name__)

# Safety cap: never hold more than this many images in memory at once
MAX_IMAGES = 25

# Max concurrent downloads (bounded to avoid overwhelming the CDN)
_SEMAPHORE_SLOTS = 10

# Per-image download timeout in seconds
_TIMEOUT_SECONDS = 10.0

# Fallback content type when the CDN doesn't set a Content-Type header
_DEFAULT_CONTENT_TYPE = "image/jpeg"

# Content types we recognise; anything else gets the fallback label
_KNOWN_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ImageDownloaderService:
    """
    Downloads images from URLs and converts them to base64 data URIs.

    Each image is fetched exactly once and stored as a data URI so that
    downstream OpenAI calls receive inline image data instead of external URLs.
    """

    async def download_images(self, urls: list[str]) -> dict[str, str]:
        """
        Download images concurrently and return a mapping of URL → base64 data URI.

        Only the first MAX_IMAGES URLs are processed. Failed downloads are omitted
        from the result — callers should fall back to the original URL in that case.

        Args:
            urls: List of image URLs to download.

        Returns:
            Dict mapping each successfully downloaded URL to its base64 data URI,
            e.g. ``{"https://cdn.example.com/img.jpg": "data:image/jpeg;base64,..."}``
        """
        if not urls:
            return {}

        capped_urls = urls[:MAX_IMAGES]
        if len(urls) > MAX_IMAGES:
            logger.warning(
                "image_downloader_cap_exceeded",
                total=len(urls),
                cap=MAX_IMAGES,
            )

        semaphore = asyncio.Semaphore(_SEMAPHORE_SLOTS)
        timeout = httpx.Timeout(_TIMEOUT_SECONDS)

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

                content_type = response.headers.get("content-type", _DEFAULT_CONTENT_TYPE)
                # Strip parameters like "; charset=utf-8"
                mime_type = content_type.split(";")[0].strip()
                if mime_type not in _KNOWN_TYPES:
                    mime_type = _DEFAULT_CONTENT_TYPE

                encoded = base64.b64encode(response.content).decode("ascii")
                data_uri = f"data:{mime_type};base64,{encoded}"
                logger.debug("image_downloaded", url=url, mime_type=mime_type, bytes=len(response.content))
                return data_uri

            except Exception as e:
                logger.warning("image_download_failed", url=url, error=str(e))
                raise
