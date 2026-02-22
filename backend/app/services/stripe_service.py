"""Stripe API wrapper."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.config import StripeConfig
from app.models.billing import SubscriptionSnapshot

try:  # pragma: no cover - exercised in runtime environments with Stripe installed
    import stripe
except ImportError:  # pragma: no cover
    stripe = None


def _to_datetime(timestamp: int | None) -> datetime | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


class StripeService:
    """Encapsulates Stripe SDK calls used by billing routes."""

    def __init__(self, config: StripeConfig) -> None:
        if not config.secret_key:
            raise ValueError("Stripe secret key is required")
        if stripe is None:
            raise ImportError("stripe package is not installed")

        self.config = config
        stripe.api_key = config.secret_key

    @property
    def price_mapping(self) -> dict[str, str]:
        return {
            self.config.price_pro_monthly: "pro_monthly",
            self.config.price_pro_quarterly: "pro_quarterly",
            self.config.price_pro_yearly: "pro_yearly",
        }

    def price_id_for_plan(self, plan_code: str) -> str | None:
        for price_id, mapped_plan in self.price_mapping.items():
            if mapped_plan == plan_code and price_id:
                return price_id
        return None

    async def create_checkout_session(
        self,
        *,
        user_id: str,
        user_email: str | None,
        plan_code: str,
        customer_id: str | None = None,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, str]:
        price_id = self.price_id_for_plan(plan_code)
        if not price_id:
            raise ValueError(f"No Stripe price configured for plan '{plan_code}'")

        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "allow_promotion_codes": True,
            "client_reference_id": user_id,
            "metadata": {"user_id": user_id, "plan_code": plan_code},
            "success_url": success_url or self.config.checkout_success_url,
            "cancel_url": cancel_url or self.config.checkout_cancel_url,
        }

        if customer_id:
            params["customer"] = customer_id
        elif user_email:
            params["customer_email"] = user_email

        session = await asyncio.to_thread(stripe.checkout.Session.create, **params)
        return {"id": session.id, "url": session.url}

    async def create_portal_session(
        self, *, customer_id: str, return_url: str | None = None
    ) -> dict[str, str]:
        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=return_url or self.config.portal_return_url,
        )
        return {"id": session.id, "url": session.url}

    def verify_webhook_event(self, payload: bytes, signature: str | None) -> dict:
        if not self.config.webhook_secret:
            raise ValueError("Stripe webhook secret is not configured")
        if not signature:
            raise ValueError("Missing Stripe-Signature header")

        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=self.config.webhook_secret,
        )
        return dict(event)

    async def fetch_subscription_snapshot(
        self, subscription_id: str, *, user_id: str | None = None
    ) -> SubscriptionSnapshot:
        subscription = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
        return self.subscription_snapshot_from_object(subscription, user_id=user_id)

    def subscription_snapshot_from_object(
        self, subscription_obj: dict | Any, *, user_id: str | None = None
    ) -> SubscriptionSnapshot:
        subscription = (
            subscription_obj
            if isinstance(subscription_obj, dict)
            else subscription_obj.to_dict_recursive()
        )

        items = subscription.get("items", {}).get("data", [])
        if not items:
            raise ValueError("Stripe subscription has no items")

        price_id = items[0].get("price", {}).get("id")
        if not price_id:
            raise ValueError("Stripe subscription is missing price id")

        metadata = subscription.get("metadata", {}) or {}
        derived_user_id = user_id or metadata.get("user_id")

        return SubscriptionSnapshot(
            subscription_id=str(subscription.get("id", "")),
            customer_id=str(subscription.get("customer", "")),
            status=str(subscription.get("status", "")),
            price_id=str(price_id),
            current_period_start=_to_datetime(subscription.get("current_period_start")),
            current_period_end=_to_datetime(subscription.get("current_period_end")),
            user_id=derived_user_id,
        )
