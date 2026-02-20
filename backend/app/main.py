"""
Rehabify Backend - Main FastAPI Application.

This is the entry point for the Rehabify backend API.
It provides endpoints for analyzing Portuguese property listings
and estimating renovation costs.

Run with:
    uvicorn app.main:app --reload
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import acreate_client
from supabase._async.client import AsyncClient as AsyncSupabaseClient

from app.api.v1.analyze import router as analyze_router
from app.config import get_settings
from app.constants import API_TITLE, API_VERSION
from app.graphs.main_graph import build_renovation_graph
from app.logging_config import setup_logging
from app.middleware import RequestContextMiddleware
from app.services.idealista import IdealistaService
from app.services.image_classifier import ImageClassifierService
from app.services.image_downloader import ImageDownloaderService
from app.services.renovation_estimator import RenovationEstimatorService

# Get settings before logging setup so we know the debug flag
settings = get_settings()

# Propagate LangSmith settings into os.environ so the SDK can find them.
# pydantic-settings reads .env into the Settings model but does NOT inject
# values into os.environ, which is where langsmith and openai_client.py look.
if settings.langchain_tracing_v2 and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

# Configure logging
setup_logging(settings.debug)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for startup and shutdown."""
    logger.info("api_startup", cors_origins=settings.cors_origins)

    if not settings.openai_api_key:
        logger.warning("openai_key_missing", detail="AI features will not work")
    else:
        logger.info("openai_configured")

    if not settings.apify_token:
        logger.warning("apify_token_missing", detail="Using mock data for Idealista scraping")
    else:
        logger.info("apify_configured")

    # Initialize Supabase async client
    supabase_client: AsyncSupabaseClient | None = None
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            supabase_client = await acreate_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
            logger.info("supabase_configured")
        except Exception as e:
            logger.warning("supabase_init_failed", error=str(e))
    else:
        logger.warning("supabase_not_configured", detail="Auth endpoints will return 503")

    _app.state.supabase = supabase_client

    # Create services once at startup
    idealista_service = IdealistaService(settings.apify_token, settings.apify)
    classifier_service = ImageClassifierService(
        settings.openai_api_key,
        model=settings.openai_classification_model,
        max_concurrent=settings.image_processing.max_concurrent_classifications,
        openai_config=settings.openai_config,
    )
    estimator_service = RenovationEstimatorService(
        settings.openai_api_key,
        model=settings.openai_vision_model,
        max_concurrent=settings.image_processing.max_concurrent_estimations,
        openai_config=settings.openai_config,
        image_processing=settings.image_processing,
    )
    downloader = ImageDownloaderService(settings.image_processing) if settings.use_base64_images else None

    if settings.use_base64_images:
        logger.info("base64_image_pipeline_enabled")
    else:
        logger.info("base64_image_pipeline_disabled", detail="passing URLs directly to OpenAI")

    # Compile graph once and store on app state
    graph = build_renovation_graph(
        settings, idealista_service, classifier_service, estimator_service, downloader
    )

    _app.state.idealista_service = idealista_service
    _app.state.classifier_service = classifier_service
    _app.state.estimator_service = estimator_service
    _app.state.graph = graph

    logger.info("services_initialized")

    yield

    await idealista_service.close()
    logger.info("api_shutdown")


# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    description=(
        "API para análise de imóveis e estimativa de custos de remodelação. "
        "Analisa anúncios do Idealista e fornece estimativas detalhadas "
        "de custos de renovação usando inteligência artificial."
    ),
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Request context middleware must come before CORS so every response gets
# the X-Request-ID header (including preflight OPTIONS responses).
app.add_middleware(RequestContextMiddleware)

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
        "name": API_TITLE,
        "version": API_VERSION,
        "description": "API para análise de imóveis e estimativa de custos de remodelação",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
