"""
Shared test fixtures for the Rehabify backend test suite.
"""

import pytest
import structlog
from fastapi.testclient import TestClient

from app.models.property import (
    ImageClassification,
    PropertyData,
    RenovationItem,
    RoomAnalysis,
    RoomCondition,
    RoomType,
)


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required environment variables for tests so Settings can be instantiated."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-testing")
    monkeypatch.setenv("APIFY_TOKEN", "apify-test-fake-token")
    # Disable LangSmith tracing in tests
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


@pytest.fixture(autouse=True)
def _configure_structlog_for_tests():
    """Configure structlog for tests using a simple, deterministic setup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient wrapping the main application."""
    # Clear the lru_cache so settings pick up test env vars
    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import app

    return TestClient(app)


@pytest.fixture
def sample_property_data() -> PropertyData:
    """Realistic sample PropertyData for a Portuguese property."""
    return PropertyData(
        url="https://www.idealista.pt/imovel/12345678/",
        title="Apartamento T2 para venda em Arroios",
        price=185000.0,
        area_m2=75.0,
        num_rooms=2,
        num_bathrooms=1,
        floor="3",
        location="Lisboa, Arroios",
        description="Apartamento T2 com 75m² em prédio de 1960.",
        image_urls=[
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/img1.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/img2.jpg",
            "https://img3.idealista.pt/blur/WEB_DETAIL/0/img3.jpg",
        ],
        raw_data={"mock": True},
    )


@pytest.fixture
def sample_classification() -> ImageClassification:
    """Sample ImageClassification for a kitchen image."""
    return ImageClassification(
        image_url="https://img3.idealista.pt/blur/WEB_DETAIL/0/img1.jpg",
        room_type=RoomType.KITCHEN,
        room_number=1,
        confidence=0.92,
    )


@pytest.fixture
def sample_room_analysis() -> RoomAnalysis:
    """Sample RoomAnalysis with renovation items for a kitchen."""
    return RoomAnalysis(
        room_type=RoomType.KITCHEN,
        room_number=1,
        room_label="Cozinha",
        images=["https://img3.idealista.pt/blur/WEB_DETAIL/0/img1.jpg"],
        condition=RoomCondition.POOR,
        condition_notes="Cozinha original dos anos 60, necessita remodelação completa.",
        renovation_items=[
            RenovationItem(
                item="Armários de cozinha",
                cost_min=3000.0,
                cost_max=6000.0,
                priority="alta",
                notes="Substituição completa",
            ),
            RenovationItem(
                item="Bancada",
                cost_min=800.0,
                cost_max=2000.0,
                priority="alta",
            ),
            RenovationItem(
                item="Pintura",
                cost_min=300.0,
                cost_max=600.0,
                priority="media",
            ),
        ],
        cost_min=4100.0,
        cost_max=8600.0,
        confidence=0.75,
    )
