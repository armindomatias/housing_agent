"""
Application configuration using pydantic-settings.
Loads environment variables from .env file.

Nested config groups (OpenAIConfig, ImageProcessingConfig, ApifyConfig) are
env-overridable via the double-underscore delimiter, e.g.:
    OPENAI_CONFIG__CLASSIFICATION_MAX_TOKENS=300
    IMAGE_PROCESSING__MAX_CONCURRENT_ESTIMATIONS=5
    APIFY__MAX_RETRIES=5
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAIConfig(BaseModel):
    """OpenAI API call parameters."""

    classification_max_tokens: int = 200
    clustering_max_tokens: int = 1000
    room_analysis_max_tokens: int = 2000
    floor_plan_max_tokens: int = 1500
    summary_max_tokens: int = 500
    classification_detail: str = "low"   # "low" or "auto" — used for classify/cluster
    estimation_detail: str = "high"      # "high" or "auto" — used for room analysis


class ImageProcessingConfig(BaseModel):
    """Image download and processing limits."""

    max_images_in_memory: int = 25
    download_timeout_seconds: float = 10.0
    max_concurrent_downloads: int = 10
    max_concurrent_classifications: int = 5
    max_concurrent_estimations: int = 3
    max_clustering_images: int = 10
    images_per_room_analysis: int = 4


class ApifyConfig(BaseModel):
    """Apify scraper configuration."""

    standby_url: str = "https://dz-omar--idealista-scraper-api.apify.actor"
    max_retries: int = 3
    retry_base_delay_seconds: int = 2
    request_timeout_seconds: float = 120.0


class StripeConfig(BaseModel):
    """Stripe integration configuration."""

    secret_key: str = ""
    webhook_secret: str = ""
    price_pro_monthly: str = "10"
    price_pro_quarterly: str = "20"
    price_pro_yearly: str = "50"
    checkout_success_url: str = "http://localhost:3000/?billing=success"
    checkout_cancel_url: str = "http://localhost:3000/pricing?billing=cancelled"
    portal_return_url: str = "http://localhost:3000/"


class BillingConfig(BaseModel):
    """Billing and entitlement configuration."""

    enabled: bool = True
    enforce_analysis_access: bool = True
    free_analyses_lifetime: int = 2
    daily_hard_cap: int = 10
    pro_monthly_quota: int = 30
    pro_quarterly_quota: int = 100
    pro_yearly_quota: int = 420
    master_user_ids: list[str] = Field(default_factory=list)
    accounts_table: str = "billing_accounts"
    webhook_events_table: str = "billing_webhook_events"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # API Keys
    openai_api_key: str
    apify_token: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""

    # OpenAI Model Configuration
    openai_vision_model: str = "gpt-4o"
    openai_classification_model: str = "gpt-4o-mini"

    # LangSmith / Observability
    langsmith_api_key: str = ""
    langsmith_project: str = "rehabify"
    langchain_tracing_v2: bool = False  # Explicit opt-in

    # Image Pipeline
    use_base64_images: bool = Field(default=True)  # Download images once and pass as base64

    # App Settings
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # Nested config groups (env-overridable via SECTION__KEY format)
    openai_config: OpenAIConfig = Field(default_factory=OpenAIConfig)
    image_processing: ImageProcessingConfig = Field(default_factory=ImageProcessingConfig)
    apify: ApifyConfig = Field(default_factory=ApifyConfig)
    stripe: StripeConfig = Field(default_factory=StripeConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
