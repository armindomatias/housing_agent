"""
Rehabify Backend - Main FastAPI Application.

This is the entry point for the Rehabify backend API.
It provides endpoints for analyzing Portuguese property listings
and estimating renovation costs.

Run with:
    uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.analyze import router as analyze_router
from app.config import get_settings
from app.graphs.main_graph import build_renovation_graph
from app.services.idealista import IdealistaService
from app.services.image_classifier import ImageClassifierService
from app.services.renovation_estimator import RenovationEstimatorService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for startup and shutdown."""
    # Startup
    logger.info("Rehabify API starting up...")
    logger.info(f"CORS origins: {settings.cors_origins}")

    # Check for required API keys
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set - AI features will not work")
    else:
        logger.info("OpenAI API key configured")

    if not settings.apify_token:
        logger.warning("APIFY_TOKEN not set - using mock data for Idealista scraping")
    else:
        logger.info("Apify token configured")

    # Create services once at startup
    idealista_service = IdealistaService(settings.apify_token)
    classifier_service = ImageClassifierService(
        settings.openai_api_key,
        model=settings.openai_classification_model,
    )
    estimator_service = RenovationEstimatorService(
        settings.openai_api_key,
        model=settings.openai_vision_model,
    )

    # Compile graph once and store on app state
    graph = build_renovation_graph(
        settings, idealista_service, classifier_service, estimator_service
    )

    _app.state.idealista_service = idealista_service
    _app.state.classifier_service = classifier_service
    _app.state.estimator_service = estimator_service
    _app.state.graph = graph

    logger.info("Services initialized and graph compiled")

    yield

    # Shutdown - close HTTP clients
    await idealista_service.close()
    logger.info("Rehabify API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Rehabify API",
    description=(
        "API para análise de imóveis e estimativa de custos de remodelação. "
        "Analisa anúncios do Idealista e fornece estimativas detalhadas "
        "de custos de renovação usando inteligência artificial."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(analyze_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": "Rehabify API",
        "version": "0.1.0",
        "description": "API para análise de imóveis e estimativa de custos de remodelação",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
