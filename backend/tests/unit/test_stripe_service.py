"""Unit tests for Stripe service wrapper."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.config import StripeConfig
from app.services import stripe_service as stripe_service_module
from app.services.stripe_service import StripeService


class FakeStripeModule:
    """Test double for stripe SDK."""

    def __init__(self):
        self.api_key = None
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._checkout_create))
        self.billing_portal = SimpleNamespace(
            Session=SimpleNamespace(create=self._portal_create)
        )
        self.Webhook = SimpleNamespace(construct_event=self._construct_event)
        self.Subscription = SimpleNamespace(retrieve=self._retrieve_subscription)
        self._event = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {}}}
        self._subscription = {
            "id": "sub_1",
            "customer": "cus_1",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_month"}}]},
            "current_period_start": 1735689600,
            "current_period_end": 1738368000,
            "metadata": {"user_id": "u1"},
        }

    @staticmethod
    def _checkout_create(**_kwargs):
        return SimpleNamespace(id="cs_1", url="https://checkout.test/session")

    @staticmethod
    def _portal_create(**_kwargs):
        return SimpleNamespace(id="bps_1", url="https://billing.test/portal")

    def _construct_event(self, payload, sig_header, secret):
        if sig_header == "bad":
            raise RuntimeError("bad signature")
        assert payload == b'{"ok":true}'
        assert secret == "whsec_test"
        return self._event

    def _retrieve_subscription(self, _subscription_id):
        return self._subscription


def _config() -> StripeConfig:
    return StripeConfig(
        secret_key="sk_test_123",
        webhook_secret="whsec_test",
        price_pro_monthly="price_month",
        price_pro_quarterly="price_quarter",
        price_pro_yearly="price_year",
    )


class TestStripeService:
    async def test_creates_checkout_session(self, monkeypatch: pytest.MonkeyPatch):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        result = await service.create_checkout_session(
            user_id="u1",
            user_email="u1@example.com",
            plan_code="pro_monthly",
        )

        assert result["id"] == "cs_1"
        assert result["url"].startswith("https://checkout.test")

    async def test_creates_portal_session(self, monkeypatch: pytest.MonkeyPatch):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        result = await service.create_portal_session(customer_id="cus_1")

        assert result["id"] == "bps_1"
        assert result["url"].startswith("https://billing.test")

    def test_verifies_webhook_event(self, monkeypatch: pytest.MonkeyPatch):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        event = service.verify_webhook_event(b'{"ok":true}', "sig_ok")

        assert event["id"] == "evt_1"

    def test_verify_webhook_event_rejects_missing_signature(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        with pytest.raises(ValueError, match="Missing Stripe-Signature"):
            service.verify_webhook_event(b'{"ok":true}', None)

    async def test_fetch_subscription_snapshot(self, monkeypatch: pytest.MonkeyPatch):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        snapshot = await service.fetch_subscription_snapshot("sub_1")

        assert snapshot.subscription_id == "sub_1"
        assert snapshot.customer_id == "cus_1"
        assert snapshot.price_id == "price_month"
        assert snapshot.current_period_start == datetime(2025, 1, 1, tzinfo=UTC)
        assert snapshot.user_id == "u1"

    def test_subscription_snapshot_from_object_requires_price_id(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeStripeModule()
        monkeypatch.setattr(stripe_service_module, "stripe", fake)
        service = StripeService(_config())

        with pytest.raises(ValueError, match="missing price id"):
            service.subscription_snapshot_from_object(
                {"id": "sub_1", "customer": "cus_1", "status": "active", "items": {"data": [{}]}}
            )
