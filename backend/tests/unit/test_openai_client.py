"""Unit tests for the centralized OpenAI client factory."""

import pytest
from openai import AsyncOpenAI

from app.services.openai_client import get_openai_client


class TestGetOpenAIClient:
    def test_returns_async_client(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        client = get_openai_client("sk-test-key")
        assert isinstance(client, AsyncOpenAI)

    def test_uses_provided_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        client = get_openai_client("sk-custom-key")
        assert client.api_key == "sk-custom-key"

    def test_uses_settings_key_when_none_provided(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        # _set_test_env fixture sets OPENAI_API_KEY to "sk-test-fake-key-for-testing"
        from app.config import get_settings

        get_settings.cache_clear()
        client = get_openai_client()
        assert client.api_key == "sk-test-fake-key-for-testing"

    def test_no_wrapping_when_tracing_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        client = get_openai_client("sk-test-key")
        # When tracing is disabled the client should be a plain AsyncOpenAI,
        # not wrapped by LangSmith (which produces a different type).
        assert type(client).__name__ == "AsyncOpenAI"
