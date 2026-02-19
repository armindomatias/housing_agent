"""
Integration tests for scrape_node — tag remapping with base64 images.

Verifies that when use_base64_images=True the image_tags stored in state
use the resolved (base64) URLs as keys, so classify_node can still match
tags without falling back to GPT for every image.
"""

from unittest.mock import AsyncMock

import pytest

from app.graphs.main_graph import scrape_node
from app.models.property import PropertyData
from app.services.idealista import IdealistaService
from app.services.image_downloader import ImageDownloaderService


def _make_property(
    image_urls: list[str],
    image_tags: dict[str, str],
) -> PropertyData:
    return PropertyData(
        url="https://www.idealista.pt/imovel/12345678/",
        title="Test property",
        price=150000,
        image_urls=image_urls,
        image_tags=image_tags,
    )


@pytest.fixture
def base_state() -> dict:
    return {"url": "https://www.idealista.pt/imovel/12345678/", "stream_events": []}


class TestScrapeNodeTagRemapping:
    """scrape_node must remap image_tags keys when URLs are resolved to base64."""

    @pytest.mark.asyncio
    async def test_tags_remapped_for_base64_urls(self, base_state: dict):
        """When base64 download succeeds, image_tags in state use base64 keys."""
        orig_url = "https://cdn.idealista.pt/img1.jpg"
        base64_uri = "data:image/jpeg;base64,/9j/abc"

        prop = _make_property(
            image_urls=[orig_url],
            image_tags={orig_url: "kitchen"},
        )

        mock_idealista = AsyncMock(spec=IdealistaService)
        mock_idealista.scrape_property.return_value = prop

        mock_downloader = AsyncMock(spec=ImageDownloaderService)
        mock_downloader.download_images.return_value = {orig_url: base64_uri}

        result = await scrape_node(
            base_state,
            idealista_service=mock_idealista,
            downloader=mock_downloader,
            use_base64_images=True,
        )

        # image_urls in state should be the base64 URI, not the original URL
        assert result["image_urls"] == [base64_uri]

        # image_tags keys must match image_urls keys (base64 URI)
        assert base64_uri in result["image_tags"]
        assert result["image_tags"][base64_uri] == "kitchen"

        # Original URL must NOT be a key any more
        assert orig_url not in result["image_tags"]

    @pytest.mark.asyncio
    async def test_tags_remapped_with_partial_download_failure(self, base_state: dict):
        """When a download fails, the fallback original URL is used as the tag key."""
        good_url = "https://cdn.idealista.pt/good.jpg"
        bad_url = "https://cdn.idealista.pt/bad.jpg"
        base64_uri = "data:image/jpeg;base64,/9j/good"

        prop = _make_property(
            image_urls=[good_url, bad_url],
            image_tags={good_url: "kitchen", bad_url: "bedroom"},
        )

        mock_idealista = AsyncMock(spec=IdealistaService)
        mock_idealista.scrape_property.return_value = prop

        mock_downloader = AsyncMock(spec=ImageDownloaderService)
        # Only good_url downloaded successfully; bad_url is missing from result
        mock_downloader.download_images.return_value = {good_url: base64_uri}

        result = await scrape_node(
            base_state,
            idealista_service=mock_idealista,
            downloader=mock_downloader,
            use_base64_images=True,
        )

        # good_url maps to base64 URI; bad_url stays as original URL (fallback)
        assert result["image_urls"] == [base64_uri, bad_url]

        tags = result["image_tags"]
        assert tags[base64_uri] == "kitchen"  # resolved key
        assert tags[bad_url] == "bedroom"     # fallback key (still original URL)

    @pytest.mark.asyncio
    async def test_tags_unchanged_when_base64_disabled(self, base_state: dict):
        """When use_base64_images=False, image_tags is stored as-is (original URLs)."""
        orig_url = "https://cdn.idealista.pt/img1.jpg"

        prop = _make_property(
            image_urls=[orig_url],
            image_tags={orig_url: "bathroom"},
        )

        mock_idealista = AsyncMock(spec=IdealistaService)
        mock_idealista.scrape_property.return_value = prop

        result = await scrape_node(
            base_state,
            idealista_service=mock_idealista,
            downloader=None,
            use_base64_images=False,
        )

        # URLs and tags should be the original values unchanged
        assert result["image_urls"] == [orig_url]
        assert result["image_tags"] == {orig_url: "bathroom"}

    @pytest.mark.asyncio
    async def test_empty_tags_handled_without_error(self, base_state: dict):
        """Empty image_tags dict must not raise even with base64 enabled."""
        orig_url = "https://cdn.idealista.pt/img1.jpg"
        base64_uri = "data:image/jpeg;base64,/9j/abc"

        prop = _make_property(image_urls=[orig_url], image_tags={})

        mock_idealista = AsyncMock(spec=IdealistaService)
        mock_idealista.scrape_property.return_value = prop

        mock_downloader = AsyncMock(spec=ImageDownloaderService)
        mock_downloader.download_images.return_value = {orig_url: base64_uri}

        result = await scrape_node(
            base_state,
            idealista_service=mock_idealista,
            downloader=mock_downloader,
            use_base64_images=True,
        )

        # image_tags should be the empty dict (falsy branch in the remap logic)
        assert result["image_tags"] == {}
        assert result["image_urls"] == [base64_uri]
