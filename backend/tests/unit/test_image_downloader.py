"""
Tests for the ImageDownloaderService.

All HTTP calls are mocked via unittest.mock — no real network traffic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.image_downloader import MAX_IMAGES, ImageDownloaderService


@pytest.fixture
def downloader() -> ImageDownloaderService:
    return ImageDownloaderService()


def _make_mock_response(
    content: bytes = b"\xff\xd8\xff",
    content_type: str = "image/jpeg",
    status_code: int = 200,
) -> MagicMock:
    """Build a minimal fake httpx.Response."""
    resp = MagicMock()
    resp.content = content
    resp.headers = {"content-type": content_type}
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestDownloadImages:
    """Tests for ImageDownloaderService.download_images()."""

    @pytest.mark.asyncio
    async def test_happy_path_all_succeed(self, downloader: ImageDownloaderService):
        """All URLs succeed — every URL maps to a data URI."""
        urls = ["http://cdn.example.com/a.jpg", "http://cdn.example.com/b.jpg"]
        fake_resp = _make_mock_response(b"\xde\xad\xbe\xef", "image/jpeg")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images(urls)

        assert len(result) == 2
        for url in urls:
            assert url in result
            assert result[url].startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_partial_failure_skips_failed_urls(self, downloader: ImageDownloaderService):
        """Failed downloads are omitted; successful ones are returned."""
        good_url = "http://cdn.example.com/good.jpg"
        bad_url = "http://cdn.example.com/bad.jpg"

        good_resp = _make_mock_response(b"\xff\xd8", "image/jpeg")

        async def _get(url: str, **_):
            if url == bad_url:
                raise Exception("Connection refused")
            return good_resp

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = _get

            result = await downloader.download_images([good_url, bad_url])

        assert good_url in result
        assert bad_url not in result
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, downloader: ImageDownloaderService):
        """Empty input should return an empty dict with no HTTP calls."""
        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            result = await downloader.download_images([])

        mock_client_cls.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_cap_exceeded_truncates_to_max(self, downloader: ImageDownloaderService):
        """URLs beyond MAX_IMAGES are silently dropped."""
        urls = [f"http://cdn.example.com/img{i}.jpg" for i in range(MAX_IMAGES + 5)]
        fake_resp = _make_mock_response(b"\x89PNG", "image/png")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images(urls)

        assert len(result) == MAX_IMAGES

    @pytest.mark.asyncio
    async def test_content_type_jpeg(self, downloader: ImageDownloaderService):
        """JPEG content type is preserved in the data URI."""
        url = "http://example.com/photo.jpg"
        fake_resp = _make_mock_response(b"\xff\xd8", "image/jpeg")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        assert result[url].startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_content_type_png(self, downloader: ImageDownloaderService):
        """PNG content type is preserved in the data URI."""
        url = "http://example.com/photo.png"
        fake_resp = _make_mock_response(b"\x89PNG\r\n", "image/png")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        assert result[url].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_content_type_webp(self, downloader: ImageDownloaderService):
        """WebP content type is preserved in the data URI."""
        url = "http://example.com/photo.webp"
        fake_resp = _make_mock_response(b"RIFF", "image/webp")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        assert result[url].startswith("data:image/webp;base64,")

    @pytest.mark.asyncio
    async def test_unknown_content_type_falls_back_to_jpeg(self, downloader: ImageDownloaderService):
        """Unknown content types fall back to image/jpeg."""
        url = "http://example.com/photo.xyz"
        fake_resp = _make_mock_response(b"\xde\xad", "application/octet-stream")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        assert result[url].startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_content_type_with_parameters_stripped(self, downloader: ImageDownloaderService):
        """Content-Type with charset/boundary params is stripped to bare MIME type."""
        url = "http://example.com/photo.jpg"
        fake_resp = _make_mock_response(b"\xff\xd8", "image/jpeg; charset=utf-8")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        assert result[url].startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_base64_encoding_is_valid(self, downloader: ImageDownloaderService):
        """The base64 portion of the data URI must decode back to the original bytes."""
        import base64

        original_bytes = b"hello world image data"
        url = "http://example.com/img.jpg"
        fake_resp = _make_mock_response(original_bytes, "image/jpeg")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=fake_resp)

            result = await downloader.download_images([url])

        data_uri = result[url]
        _, encoded = data_uri.split(",", 1)
        assert base64.b64decode(encoded) == original_bytes

    @pytest.mark.asyncio
    async def test_all_fail_returns_empty(self, downloader: ImageDownloaderService):
        """When every download fails, an empty dict is returned."""
        urls = ["http://a.com/1.jpg", "http://b.com/2.jpg"]

        async def _get(url, **_):
            raise Exception("Timeout")

        with patch("app.services.image_downloader.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = _get

            result = await downloader.download_images(urls)

        assert result == {}
