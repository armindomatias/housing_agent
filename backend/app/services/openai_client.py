"""Centralized OpenAI client factory with LangSmith tracing."""

import os

from openai import AsyncOpenAI

from app.config import get_settings


def get_openai_client(api_key: str | None = None) -> AsyncOpenAI:
    """
    Create an AsyncOpenAI client, optionally wrapped with LangSmith tracing.

    Uses wrap_openai when LANGCHAIN_TRACING_V2 is enabled (checks env var
    directly since LangSmith itself reads it from the environment).

    Args:
        api_key: OpenAI API key. Defaults to settings.openai_api_key.

    Returns:
        AsyncOpenAI client (wrapped if tracing is enabled).
    """
    settings = get_settings()
    key = api_key or settings.openai_api_key

    client = AsyncOpenAI(api_key=key)

    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        from langsmith.wrappers import wrap_openai

        client = wrap_openai(client)

    return client
