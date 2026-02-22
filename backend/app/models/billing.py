"""Billing and entitlement models."""

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PlanCode(str, Enum):
    """Supported billing plans."""

    FREE = "free"
    PRO_MONTHLY = "pro_monthly"
    PRO_QUARTERLY = "pro_quarterly"
    PRO_YEARLY = "pro_yearly"
    MASTER = "master"


class AccessReason(str, Enum):
    """Reason for an entitlement decision."""

    BILLING_DISABLED = "billing_disabled"
    MASTER_ACCESS = "master_access"
    FREE_TIER_AVAILABLE = "free_tier_available"
    FREE_LIMIT_REACHED = "free_limit_reached"
    SUBSCRIPTION_AVAILABLE = "subscription_available"
    SUBSCRIPTION_LIMIT_REACHED = "subscription_limit_reached"
    DAILY_CAP_REACHED = "daily_cap_reached"


class BillingAccount(BaseModel):
    """Persisted billing state for a user."""

    user_id: str
    free_analyses_used: int = Field(default=0, ge=0)
    cycle_analyses_used: int = Field(default=0, ge=0)
    daily_usage_count: int = Field(default=0, ge=0)
    daily_usage_date: date | None = None
    plan_code: PlanCode = PlanCode.FREE
    subscription_status: str = ""
    cycle_start_at: datetime | None = None
    cycle_end_at: datetime | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    is_master_override: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BillingStatus(BaseModel):
    """Computed billing status returned to the frontend."""

    billing_enabled: bool
    enforce_analysis_access: bool
    is_master: bool
    plan_code: PlanCode
    subscription_status: str | None = None
    analyses_remaining: int | None = None
    free_analyses_remaining: int = 0
    daily_remaining: int | None = None
    requires_upgrade: bool = False


class EntitlementDecision(BillingStatus):
    """Decision returned when trying to start an analysis."""

    allowed: bool
    reason: AccessReason
    reservation_id: str | None = None


class UsageReservation(BaseModel):
    """Tracks a pending usage reservation."""

    reservation_id: str
    user_id: str
    bucket: Literal["free", "paid"]
    plan_code: PlanCode
    created_at: datetime


class SubscriptionSnapshot(BaseModel):
    """Normalized Stripe subscription payload."""

    subscription_id: str
    customer_id: str
    status: str
    price_id: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    user_id: str | None = None
