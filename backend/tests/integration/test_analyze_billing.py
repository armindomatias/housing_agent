"""Integration tests for billing enforcement in analyze endpoints."""

from typing import Any, AsyncGenerator

from app.auth import AuthenticatedUser, get_current_user
from app.models.billing import AccessReason, EntitlementDecision, PlanCode


async def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(id="user-1", email="user@example.com")


class FakeGraph:
    def __init__(self, *, final_state: dict[str, Any] | None = None, stream_events=None, error: Exception | None = None):
        self.final_state = final_state if final_state is not None else {}
        self.stream_events = stream_events or []
        self.error = error
        self.ainvoke_called = 0
        self.astream_called = 0

    async def ainvoke(self, _state: dict[str, Any]) -> dict[str, Any]:
        self.ainvoke_called += 1
        if self.error:
            raise self.error
        return self.final_state

    async def astream(self, _state: dict[str, Any]) -> AsyncGenerator[dict[str, Any], None]:
        self.astream_called += 1
        if self.error:
            raise self.error
        emitted: list[dict[str, Any]] = []
        for event in self.stream_events:
            emitted.append(event)
            yield {"node": {"stream_events": list(emitted)}}


class FakeBillingService:
    def __init__(self, decision: EntitlementDecision):
        self.decision = decision
        self.reserve_calls: list[str] = []
        self.commit_calls: list[str | None] = []
        self.release_calls: list[str | None] = []

    async def reserve_analysis(self, user_id: str) -> EntitlementDecision:
        self.reserve_calls.append(user_id)
        return self.decision

    async def commit_reservation(self, reservation_id: str | None) -> None:
        self.commit_calls.append(reservation_id)

    async def release_reservation(self, reservation_id: str | None) -> None:
        self.release_calls.append(reservation_id)


def allowed_decision(reservation_id: str = "res_1") -> EntitlementDecision:
    return EntitlementDecision(
        billing_enabled=True,
        enforce_analysis_access=True,
        is_master=False,
        plan_code=PlanCode.FREE,
        subscription_status=None,
        analyses_remaining=1,
        free_analyses_remaining=1,
        daily_remaining=9,
        requires_upgrade=False,
        allowed=True,
        reason=AccessReason.FREE_TIER_AVAILABLE,
        reservation_id=reservation_id,
    )


def denied_decision() -> EntitlementDecision:
    return EntitlementDecision(
        billing_enabled=True,
        enforce_analysis_access=True,
        is_master=False,
        plan_code=PlanCode.FREE,
        subscription_status=None,
        analyses_remaining=0,
        free_analyses_remaining=0,
        daily_remaining=9,
        requires_upgrade=True,
        allowed=False,
        reason=AccessReason.FREE_LIMIT_REACHED,
        reservation_id=None,
    )


class TestAnalyzeSyncBilling:
    def test_sync_denied_returns_402(self, client):
        graph = FakeGraph(final_state={"estimate": {"ok": True}})
        billing = FakeBillingService(denied_decision())
        client.app.state.graph = graph
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post(
            "/api/v1/analyze/sync",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )

        client.app.dependency_overrides.clear()
        assert response.status_code == 402
        assert graph.ainvoke_called == 0

    def test_sync_success_commits_reservation(self, client):
        graph = FakeGraph(
            final_state={
                "estimate": {
                    "property_url": "https://www.idealista.pt/imovel/12345678/",
                    "room_analyses": [],
                    "total_cost_min": 1000,
                    "total_cost_max": 2000,
                    "overall_confidence": 0.8,
                    "summary": "ok",
                }
            }
        )
        billing = FakeBillingService(allowed_decision("res_sync"))
        client.app.state.graph = graph
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post(
            "/api/v1/analyze/sync",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert billing.commit_calls == ["res_sync"]
        assert billing.release_calls == []

    def test_sync_error_result_releases_reservation(self, client):
        graph = FakeGraph(final_state={"error": "boom"})
        billing = FakeBillingService(allowed_decision("res_sync"))
        client.app.state.graph = graph
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post(
            "/api/v1/analyze/sync",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert billing.release_calls == ["res_sync"]


class TestAnalyzeStreamBilling:
    def test_stream_success_commits_reservation(self, client):
        graph = FakeGraph(
            stream_events=[
                {"type": "status", "message": "ok", "step": 1, "total_steps": 5},
                {"type": "result", "message": "done", "step": 5, "total_steps": 5, "data": {"estimate": {"x": 1}}},
            ]
        )
        billing = FakeBillingService(allowed_decision("res_stream"))
        client.app.state.graph = graph
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post(
            "/api/v1/analyze",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert "result" in response.text
        assert billing.commit_calls == ["res_stream"]
        assert billing.release_calls == []

    def test_stream_error_releases_reservation(self, client):
        graph = FakeGraph(
            stream_events=[
                {"type": "error", "message": "bad", "step": 3, "total_steps": 5},
            ]
        )
        billing = FakeBillingService(allowed_decision("res_stream"))
        client.app.state.graph = graph
        client.app.state.billing_service = billing
        client.app.dependency_overrides[get_current_user] = _fake_user

        response = client.post(
            "/api/v1/analyze",
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
        )

        client.app.dependency_overrides.clear()
        assert response.status_code == 200
        assert "error" in response.text
        assert billing.release_calls == ["res_stream"]
