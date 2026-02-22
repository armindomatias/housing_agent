"""Billing entitlement service and repositories."""

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Protocol

import structlog

from app.config import BillingConfig
from app.models.billing import (
    AccessReason,
    BillingAccount,
    BillingStatus,
    EntitlementDecision,
    PlanCode,
    SubscriptionSnapshot,
    UsageReservation,
)

logger = structlog.get_logger(__name__)

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BillingRepository(Protocol):
    """Storage contract for billing state."""

    async def get_account(self, user_id: str) -> BillingAccount | None:
        """Fetch a user account."""

    async def get_account_by_customer_id(self, customer_id: str) -> BillingAccount | None:
        """Fetch account by Stripe customer ID."""

    async def upsert_account(self, account: BillingAccount) -> BillingAccount:
        """Persist account state."""

    async def mark_webhook_processed(self, event_id: str) -> bool:
        """Record webhook idempotency key.

        Returns True when the event is new; False if already seen.
        """


class InMemoryBillingRepository:
    """In-memory repository used for tests and local fallback."""

    def __init__(self) -> None:
        self.accounts: dict[str, BillingAccount] = {}
        self.customer_to_user: dict[str, str] = {}
        self.processed_events: set[str] = set()

    async def get_account(self, user_id: str) -> BillingAccount | None:
        account = self.accounts.get(user_id)
        return account.model_copy(deep=True) if account else None

    async def get_account_by_customer_id(self, customer_id: str) -> BillingAccount | None:
        user_id = self.customer_to_user.get(customer_id)
        if not user_id:
            return None
        return await self.get_account(user_id)

    async def upsert_account(self, account: BillingAccount) -> BillingAccount:
        stored = account.model_copy(deep=True)
        self.accounts[stored.user_id] = stored
        if stored.stripe_customer_id:
            self.customer_to_user[stored.stripe_customer_id] = stored.user_id
        return stored.model_copy(deep=True)

    async def mark_webhook_processed(self, event_id: str) -> bool:
        if event_id in self.processed_events:
            return False
        self.processed_events.add(event_id)
        return True


class SupabaseBillingRepository:
    """Supabase-backed repository for billing state."""

    def __init__(self, client, accounts_table: str, webhook_events_table: str):
        self.client = client
        self.accounts_table = accounts_table
        self.webhook_events_table = webhook_events_table

    async def get_account(self, user_id: str) -> BillingAccount | None:
        response = (
            await self.client.table(self.accounts_table)
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return BillingAccount.model_validate(rows[0])

    async def get_account_by_customer_id(self, customer_id: str) -> BillingAccount | None:
        response = (
            await self.client.table(self.accounts_table)
            .select("*")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return BillingAccount.model_validate(rows[0])

    async def upsert_account(self, account: BillingAccount) -> BillingAccount:
        payload = account.model_dump(mode="json", exclude_none=True)
        response = (
            await self.client.table(self.accounts_table)
            .upsert(payload, on_conflict="user_id")
            .execute()
        )
        rows = response.data or []
        if not rows:
            # Some Supabase responses return no data unless `returning=representation`.
            return account
        return BillingAccount.model_validate(rows[0])

    async def mark_webhook_processed(self, event_id: str) -> bool:
        existing = (
            await self.client.table(self.webhook_events_table)
            .select("event_id")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return False

        await self.client.table(self.webhook_events_table).insert(
            {"event_id": event_id, "processed_at": _utcnow().isoformat()}
        ).execute()
        return True


class BillingService:
    """Determines if users can run analyses and tracks usage reservations."""

    def __init__(
        self,
        repository: BillingRepository,
        config: BillingConfig,
        now_provider=_utcnow,
    ) -> None:
        self.repository = repository
        self.config = config
        self.now_provider = now_provider
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._reservations: dict[str, UsageReservation] = {}

    def _plan_quota(self, plan_code: PlanCode) -> int | None:
        if plan_code == PlanCode.PRO_MONTHLY:
            return self.config.pro_monthly_quota
        if plan_code == PlanCode.PRO_QUARTERLY:
            return self.config.pro_quarterly_quota
        if plan_code == PlanCode.PRO_YEARLY:
            return self.config.pro_yearly_quota
        return None

    def _is_master(self, account: BillingAccount) -> bool:
        return account.is_master_override or account.user_id in self.config.master_user_ids

    def _active_paid_plan(self, account: BillingAccount) -> PlanCode | None:
        if account.plan_code not in {
            PlanCode.PRO_MONTHLY,
            PlanCode.PRO_QUARTERLY,
            PlanCode.PRO_YEARLY,
        }:
            return None
        if account.subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
            return None
        return account.plan_code

    def _reset_daily_if_needed(self, account: BillingAccount, today: date) -> None:
        if account.daily_usage_date != today:
            account.daily_usage_count = 0
            account.daily_usage_date = today

    def _reset_cycle_if_needed(self, account: BillingAccount, now: datetime) -> None:
        if account.cycle_end_at and now >= account.cycle_end_at:
            account.cycle_analyses_used = 0

    async def _load_or_create_account(self, user_id: str) -> BillingAccount:
        account = await self.repository.get_account(user_id)
        if account is None:
            account = BillingAccount(user_id=user_id, daily_usage_date=self.now_provider().date())
        return account

    def _status_from_account(self, account: BillingAccount) -> BillingStatus:
        now = self.now_provider()
        today = now.date()
        self._reset_daily_if_needed(account, today)
        self._reset_cycle_if_needed(account, now)

        if self._is_master(account):
            return BillingStatus(
                billing_enabled=self.config.enabled,
                enforce_analysis_access=self.config.enforce_analysis_access,
                is_master=True,
                plan_code=PlanCode.MASTER,
                subscription_status=account.subscription_status or None,
                analyses_remaining=None,
                free_analyses_remaining=max(
                    0, self.config.free_analyses_lifetime - account.free_analyses_used
                ),
                daily_remaining=None,
                requires_upgrade=False,
            )

        daily_remaining = max(0, self.config.daily_hard_cap - account.daily_usage_count)
        free_remaining = max(0, self.config.free_analyses_lifetime - account.free_analyses_used)

        active_plan = self._active_paid_plan(account)
        if active_plan:
            quota = self._plan_quota(active_plan)
            remaining = None if quota is None else max(0, quota - account.cycle_analyses_used)
            requires_upgrade = remaining == 0
            return BillingStatus(
                billing_enabled=self.config.enabled,
                enforce_analysis_access=self.config.enforce_analysis_access,
                is_master=False,
                plan_code=active_plan,
                subscription_status=account.subscription_status or None,
                analyses_remaining=remaining,
                free_analyses_remaining=free_remaining,
                daily_remaining=daily_remaining,
                requires_upgrade=requires_upgrade,
            )

        return BillingStatus(
            billing_enabled=self.config.enabled,
            enforce_analysis_access=self.config.enforce_analysis_access,
            is_master=False,
            plan_code=PlanCode.FREE,
            subscription_status=account.subscription_status or None,
            analyses_remaining=free_remaining,
            free_analyses_remaining=free_remaining,
            daily_remaining=daily_remaining,
            requires_upgrade=free_remaining == 0,
        )

    async def get_status(self, user_id: str) -> BillingStatus:
        async with self._locks[user_id]:
            account = await self._load_or_create_account(user_id)
            status = self._status_from_account(account)
            await self.repository.upsert_account(account)
            return status

    async def reserve_analysis(self, user_id: str) -> EntitlementDecision:
        async with self._locks[user_id]:
            account = await self._load_or_create_account(user_id)
            status = self._status_from_account(account)

            if not self.config.enabled or not self.config.enforce_analysis_access:
                await self.repository.upsert_account(account)
                return EntitlementDecision(
                    **status.model_dump(),
                    allowed=True,
                    reason=AccessReason.BILLING_DISABLED,
                )

            if status.is_master:
                await self.repository.upsert_account(account)
                return EntitlementDecision(
                    **status.model_dump(),
                    allowed=True,
                    reason=AccessReason.MASTER_ACCESS,
                )

            if status.daily_remaining is not None and status.daily_remaining <= 0:
                await self.repository.upsert_account(account)
                return EntitlementDecision(
                    **status.model_dump(),
                    allowed=False,
                    reason=AccessReason.DAILY_CAP_REACHED,
                )

            reservation_id = str(uuid.uuid4())

            if status.plan_code == PlanCode.FREE:
                if status.free_analyses_remaining <= 0:
                    await self.repository.upsert_account(account)
                    return EntitlementDecision(
                        **status.model_dump(),
                        allowed=False,
                        reason=AccessReason.FREE_LIMIT_REACHED,
                    )

                account.free_analyses_used += 1
                account.daily_usage_count += 1
                account.daily_usage_date = self.now_provider().date()
                await self.repository.upsert_account(account)
                self._reservations[reservation_id] = UsageReservation(
                    reservation_id=reservation_id,
                    user_id=user_id,
                    bucket="free",
                    plan_code=PlanCode.FREE,
                    created_at=self.now_provider(),
                )

                updated_status = self._status_from_account(account)
                return EntitlementDecision(
                    **updated_status.model_dump(),
                    allowed=True,
                    reason=AccessReason.FREE_TIER_AVAILABLE,
                    reservation_id=reservation_id,
                )

            plan_quota = self._plan_quota(status.plan_code)
            if plan_quota is not None and account.cycle_analyses_used >= plan_quota:
                await self.repository.upsert_account(account)
                return EntitlementDecision(
                    **status.model_dump(),
                    allowed=False,
                    reason=AccessReason.SUBSCRIPTION_LIMIT_REACHED,
                )

            account.cycle_analyses_used += 1
            account.daily_usage_count += 1
            account.daily_usage_date = self.now_provider().date()
            await self.repository.upsert_account(account)
            self._reservations[reservation_id] = UsageReservation(
                reservation_id=reservation_id,
                user_id=user_id,
                bucket="paid",
                plan_code=status.plan_code,
                created_at=self.now_provider(),
            )

            updated_status = self._status_from_account(account)
            return EntitlementDecision(
                **updated_status.model_dump(),
                allowed=True,
                reason=AccessReason.SUBSCRIPTION_AVAILABLE,
                reservation_id=reservation_id,
            )

    async def commit_reservation(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        self._reservations.pop(reservation_id, None)

    async def release_reservation(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return

        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            return

        async with self._locks[reservation.user_id]:
            account = await self._load_or_create_account(reservation.user_id)
            if reservation.bucket == "free":
                account.free_analyses_used = max(0, account.free_analyses_used - 1)
            elif reservation.bucket == "paid":
                account.cycle_analyses_used = max(0, account.cycle_analyses_used - 1)

            account.daily_usage_count = max(0, account.daily_usage_count - 1)
            await self.repository.upsert_account(account)

    def _map_price_to_plan(self, price_id: str, price_mapping: dict[str, PlanCode]) -> PlanCode | None:
        return price_mapping.get(price_id)

    async def apply_subscription_snapshot(
        self,
        snapshot: SubscriptionSnapshot,
        *,
        price_mapping: dict[str, PlanCode],
    ) -> BillingAccount | None:
        account: BillingAccount | None = None
        if snapshot.user_id:
            account = await self.repository.get_account(snapshot.user_id)
        if account is None:
            account = await self.repository.get_account_by_customer_id(snapshot.customer_id)

        if account is None:
            if not snapshot.user_id:
                logger.warning(
                    "billing_subscription_user_missing",
                    customer_id=snapshot.customer_id,
                    subscription_id=snapshot.subscription_id,
                )
                return None
            account = BillingAccount(user_id=snapshot.user_id)

        previous_plan = account.plan_code
        mapped_plan = self._map_price_to_plan(snapshot.price_id, price_mapping)

        account.stripe_customer_id = snapshot.customer_id
        account.stripe_subscription_id = snapshot.subscription_id
        account.subscription_status = snapshot.status

        if mapped_plan is None:
            account.plan_code = PlanCode.FREE
            account.cycle_analyses_used = 0
            account.cycle_start_at = None
            account.cycle_end_at = None
        else:
            account.plan_code = mapped_plan
            account.cycle_start_at = snapshot.current_period_start
            account.cycle_end_at = snapshot.current_period_end
            if previous_plan != mapped_plan:
                account.cycle_analyses_used = 0

        if snapshot.status not in ACTIVE_SUBSCRIPTION_STATUSES:
            account.plan_code = PlanCode.FREE
            account.cycle_analyses_used = 0

        return await self.repository.upsert_account(account)

    async def process_webhook_event_id(self, event_id: str) -> bool:
        return await self.repository.mark_webhook_processed(event_id)
