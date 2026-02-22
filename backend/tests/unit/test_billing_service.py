"""Unit tests for billing entitlement logic."""

from datetime import UTC, datetime, timedelta

from app.config import BillingConfig
from app.models.billing import AccessReason, BillingAccount, PlanCode, SubscriptionSnapshot
from app.services.billing_service import BillingService, InMemoryBillingRepository


class MutableClock:
    """Deterministic clock helper for tests."""

    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def make_service(
    *,
    clock: MutableClock | None = None,
    config: BillingConfig | None = None,
    repository: InMemoryBillingRepository | None = None,
) -> tuple[BillingService, InMemoryBillingRepository, MutableClock]:
    active_clock = clock or MutableClock(datetime(2026, 2, 22, 12, 0, tzinfo=UTC))
    repo = repository or InMemoryBillingRepository()
    service = BillingService(
        repo,
        config or BillingConfig(),
        now_provider=active_clock.now,
    )
    return service, repo, active_clock


class TestBillingServiceFreeTier:
    async def test_new_user_gets_full_free_allowance(self):
        service, _, _ = make_service()

        status = await service.get_status("user-a")

        assert status.plan_code == PlanCode.FREE
        assert status.free_analyses_remaining == 2
        assert status.analyses_remaining == 2
        assert status.requires_upgrade is False

    async def test_reserve_consumes_two_free_then_denies(self):
        service, _, _ = make_service()

        d1 = await service.reserve_analysis("user-a")
        d2 = await service.reserve_analysis("user-a")
        d3 = await service.reserve_analysis("user-a")

        assert d1.allowed is True
        assert d1.reason == AccessReason.FREE_TIER_AVAILABLE
        assert d2.allowed is True
        assert d3.allowed is False
        assert d3.reason == AccessReason.FREE_LIMIT_REACHED
        assert d3.requires_upgrade is True

    async def test_release_refunds_reserved_free_usage(self):
        service, _, _ = make_service()
        decision = await service.reserve_analysis("user-a")
        assert decision.reservation_id is not None

        await service.release_reservation(decision.reservation_id)
        status = await service.get_status("user-a")

        assert status.free_analyses_remaining == 2

    async def test_commit_keeps_consumed_usage(self):
        service, _, _ = make_service()
        decision = await service.reserve_analysis("user-a")

        await service.commit_reservation(decision.reservation_id)
        status = await service.get_status("user-a")

        assert status.free_analyses_remaining == 1


class TestBillingServiceCaps:
    async def test_daily_cap_blocks_even_with_free_remaining(self):
        cfg = BillingConfig(daily_hard_cap=1)
        service, _, _ = make_service(config=cfg)

        first = await service.reserve_analysis("user-a")
        second = await service.reserve_analysis("user-a")

        assert first.allowed is True
        assert second.allowed is False
        assert second.reason == AccessReason.DAILY_CAP_REACHED

    async def test_daily_cap_resets_on_next_day(self):
        cfg = BillingConfig(daily_hard_cap=1)
        clock = MutableClock(datetime(2026, 2, 22, 12, 0, tzinfo=UTC))
        service, _, _ = make_service(config=cfg, clock=clock)

        first = await service.reserve_analysis("user-a")
        clock.advance(timedelta(days=1))
        second = await service.reserve_analysis("user-a")

        assert first.allowed is True
        assert second.allowed is True

    async def test_master_user_bypasses_all_limits(self):
        cfg = BillingConfig(master_user_ids=["master-1"], daily_hard_cap=0)
        service, _, _ = make_service(config=cfg)

        for _ in range(5):
            decision = await service.reserve_analysis("master-1")
            assert decision.allowed is True
            assert decision.reason == AccessReason.MASTER_ACCESS
            assert decision.plan_code == PlanCode.MASTER


class TestBillingServicePaidPlan:
    async def test_active_subscription_uses_cycle_quota(self):
        cfg = BillingConfig(pro_monthly_quota=2)
        service, repo, _ = make_service(config=cfg)
        await repo.upsert_account(
            BillingAccount(
                user_id="user-paid",
                plan_code=PlanCode.PRO_MONTHLY,
                subscription_status="active",
                cycle_start_at=datetime(2026, 2, 1, tzinfo=UTC),
                cycle_end_at=datetime(2026, 3, 1, tzinfo=UTC),
            )
        )

        d1 = await service.reserve_analysis("user-paid")
        d2 = await service.reserve_analysis("user-paid")
        d3 = await service.reserve_analysis("user-paid")

        assert d1.allowed is True
        assert d2.allowed is True
        assert d3.allowed is False
        assert d3.reason == AccessReason.SUBSCRIPTION_LIMIT_REACHED

    async def test_cycle_usage_resets_after_cycle_end(self):
        cfg = BillingConfig(pro_monthly_quota=1)
        clock = MutableClock(datetime(2026, 2, 28, 12, 0, tzinfo=UTC))
        service, repo, _ = make_service(config=cfg, clock=clock)
        await repo.upsert_account(
            BillingAccount(
                user_id="user-paid",
                plan_code=PlanCode.PRO_MONTHLY,
                subscription_status="active",
                cycle_analyses_used=1,
                cycle_end_at=datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
            )
        )

        decision = await service.reserve_analysis("user-paid")
        assert decision.allowed is True

    async def test_release_refunds_paid_cycle_usage(self):
        cfg = BillingConfig(pro_monthly_quota=2)
        service, repo, _ = make_service(config=cfg)
        await repo.upsert_account(
            BillingAccount(
                user_id="user-paid",
                plan_code=PlanCode.PRO_MONTHLY,
                subscription_status="active",
                cycle_end_at=datetime(2026, 3, 1, tzinfo=UTC),
            )
        )

        decision = await service.reserve_analysis("user-paid")
        await service.release_reservation(decision.reservation_id)
        status = await service.get_status("user-paid")

        assert status.analyses_remaining == 2


class TestBillingServiceSubscriptionSync:
    async def test_apply_subscription_snapshot_maps_price_to_plan(self):
        service, repo, _ = make_service()
        await repo.upsert_account(BillingAccount(user_id="u1"))
        snapshot = SubscriptionSnapshot(
            subscription_id="sub_1",
            customer_id="cus_1",
            status="active",
            price_id="price_month",
            user_id="u1",
            current_period_start=datetime(2026, 2, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 3, 1, tzinfo=UTC),
        )

        account = await service.apply_subscription_snapshot(
            snapshot,
            price_mapping={"price_month": PlanCode.PRO_MONTHLY},
        )

        assert account is not None
        assert account.plan_code == PlanCode.PRO_MONTHLY
        assert account.subscription_status == "active"
        assert account.stripe_customer_id == "cus_1"

    async def test_apply_subscription_snapshot_unknown_price_falls_back_to_free(self):
        service, repo, _ = make_service()
        await repo.upsert_account(BillingAccount(user_id="u1"))
        snapshot = SubscriptionSnapshot(
            subscription_id="sub_1",
            customer_id="cus_1",
            status="active",
            price_id="price_unknown",
            user_id="u1",
        )

        account = await service.apply_subscription_snapshot(snapshot, price_mapping={})

        assert account is not None
        assert account.plan_code == PlanCode.FREE

    async def test_inactive_subscription_downgrades_to_free(self):
        service, repo, _ = make_service()
        await repo.upsert_account(
            BillingAccount(
                user_id="u1",
                plan_code=PlanCode.PRO_MONTHLY,
                subscription_status="active",
            )
        )
        snapshot = SubscriptionSnapshot(
            subscription_id="sub_1",
            customer_id="cus_1",
            status="canceled",
            price_id="price_month",
            user_id="u1",
        )

        account = await service.apply_subscription_snapshot(
            snapshot,
            price_mapping={"price_month": PlanCode.PRO_MONTHLY},
        )

        assert account is not None
        assert account.plan_code == PlanCode.FREE
        assert account.subscription_status == "canceled"

    async def test_process_webhook_event_id_is_idempotent(self):
        service, _, _ = make_service()

        first = await service.process_webhook_event_id("evt_1")
        second = await service.process_webhook_event_id("evt_1")

        assert first is True
        assert second is False


class TestBillingServiceConfigModes:
    async def test_not_enforced_mode_allows_without_consuming(self):
        cfg = BillingConfig(enforce_analysis_access=False)
        service, _, _ = make_service(config=cfg)

        decision = await service.reserve_analysis("user-a")
        status = await service.get_status("user-a")

        assert decision.allowed is True
        assert decision.reason == AccessReason.BILLING_DISABLED
        assert decision.reservation_id is None
        assert status.free_analyses_remaining == 2
