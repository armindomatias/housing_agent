"""Integration tests for billing API endpoints."""

from datetime import UTC, datetime

from app.auth import AuthenticatedUser, get_current_user
from app.config import BillingConfig
from app.models.billing import BillingAccount, PlanCode, SubscriptionSnapshot
from app.services.billing_service import BillingService, InMemoryBillingRepository


async def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(id="user-1", email="user@example.com")


class FakeStripeService:
    def __init__(self):
        self.price_mapping = {
            "price_month": "pro_monthly",
            "price_quarter": "pro_quarterly",
            "price_year": "pro_yearly",
        }

    async def create_checkout_session(self, **_kwargs):
        return {"id": "cs_test", "url": "https://checkout.test/session"}

    async def create_portal_session(self, **_kwargs):
        return {"id": "bps_test", "url": "https://billing.test/portal"}

    def verify_webhook_event(self, _payload, signature):
        if signature == "bad":
            raise RuntimeError("bad signature")
        return {
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_1",
                    "customer": "cus_1",
                    "client_reference_id": "user-1",
                    "metadata": {"user_id": "user-1"},
                }
            },
        }

    async def fetch_subscription_snapshot(self, _subscription_id, *, user_id=None):
        return SubscriptionSnapshot(
            subscription_id="sub_1",
            customer_id="cus_1",
            status="active",
            price_id="price_month",
            current_period_start=datetime(2026, 2, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 3, 1, tzinfo=UTC),
            user_id=user_id,
        )

    def subscription_snapshot_from_object(self, _subscription_obj, *, user_id=None):
        return SubscriptionSnapshot(
            subscription_id="sub_2",
            customer_id="cus_1",
            status="active",
            price_id="price_month",
            user_id=user_id,
        )


class TestBillingStatusEndpoint:
    def test_returns_status(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.get("/api/v1/billing/status")

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        data = response.json()
        assert data["plan_code"] == "free"
        assert data["free_analyses_remaining"] == 2


class TestBillingCheckoutEndpoint:
    def test_checkout_requires_stripe_config(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = None
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post("/api/v1/billing/checkout", json={"plan_code": "pro_monthly"})

        client.app.dependency_overrides.clear()
        assert response.status_code == 503

    def test_checkout_returns_url(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post("/api/v1/billing/checkout", json={"plan_code": "pro_monthly"})

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert response.json()["checkout_url"].startswith("https://checkout.test")

    def test_checkout_rejects_free_plan(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post("/api/v1/billing/checkout", json={"plan_code": "free"})

        client.app.dependency_overrides.clear()
        assert response.status_code == 400


class TestBillingPortalEndpoint:
    def test_portal_requires_customer_id(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post("/api/v1/billing/portal", json={})

        client.app.dependency_overrides.clear()
        assert response.status_code == 400

    def test_portal_returns_url(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()
        client.app.dependency_overrides[get_current_user] = _fake_user
        # Preload account with Stripe customer ID
        client.app.state.billing_service.repository.accounts["user-1"] = BillingAccount(
            user_id="user-1", stripe_customer_id="cus_1", plan_code=PlanCode.FREE
        )

        response = client.post("/api/v1/billing/portal", json={})

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert response.json()["portal_url"].startswith("https://billing.test")


class TestBillingWebhookEndpoint:
    def test_webhook_rejects_bad_signature(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()

        response = client.post(
            "/api/v1/billing/webhook",
            headers={"Stripe-Signature": "bad"},
            content=b'{"x":1}',
        )

        assert response.status_code == 400

    def test_webhook_processes_once(self, client):
        repo = InMemoryBillingRepository()
        billing = BillingService(repo, BillingConfig())
        client.app.state.billing_service = billing
        client.app.state.stripe_service = FakeStripeService()

        first = client.post(
            "/api/v1/billing/webhook",
            headers={"Stripe-Signature": "ok"},
            content=b'{"x":1}',
        )
        second = client.post(
            "/api/v1/billing/webhook",
            headers={"Stripe-Signature": "ok"},
            content=b'{"x":1}',
        )

        assert first.status_code == 200
        assert first.json()["processed"] is True
        assert second.status_code == 200
        assert second.json()["processed"] is False
