"""Billing API endpoints."""

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.models.billing import BillingStatus, PlanCode
from app.services.billing_service import BillingService
from app.services.stripe_service import StripeService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    """Checkout session request."""

    plan_code: PlanCode = Field(description="Requested paid plan")
    success_url: str | None = Field(default=None, description="Optional override URL")
    cancel_url: str | None = Field(default=None, description="Optional override URL")


class CheckoutResponse(BaseModel):
    """Checkout session response."""

    checkout_url: str
    session_id: str


class PortalRequest(BaseModel):
    """Customer portal request."""

    return_url: str | None = None


class PortalResponse(BaseModel):
    """Customer portal response."""

    portal_url: str


class WebhookResponse(BaseModel):
    """Stripe webhook processing response."""

    received: bool
    processed: bool


def _get_billing_service(request: Request) -> BillingService:
    service = getattr(request.app.state, "billing_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Serviço de billing indisponível")
    return service


def _get_stripe_service(request: Request) -> StripeService:
    service = getattr(request.app.state, "stripe_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Stripe não configurado")
    return service


@router.get("/status", response_model=BillingStatus)
async def billing_status(request: Request, user: CurrentUser) -> BillingStatus:
    """Return computed entitlement status for the authenticated user."""
    service = _get_billing_service(request)
    return await service.get_status(user.id)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    request: Request,
    user: CurrentUser,
) -> CheckoutResponse:
    """Create a Stripe Checkout session for a paid plan."""
    if body.plan_code not in {
        PlanCode.PRO_MONTHLY,
        PlanCode.PRO_QUARTERLY,
        PlanCode.PRO_YEARLY,
    }:
        raise HTTPException(status_code=400, detail="Plano inválido para checkout")

    billing_service = _get_billing_service(request)
    stripe_service = _get_stripe_service(request)
    account = await billing_service.repository.get_account(user.id)
    customer_id = account.stripe_customer_id if account else None

    try:
        checkout = await stripe_service.create_checkout_session(
            user_id=user.id,
            user_email=user.email,
            plan_code=body.plan_code.value,
            customer_id=customer_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CheckoutResponse(checkout_url=checkout["url"], session_id=checkout["id"])


@router.post("/portal", response_model=PortalResponse)
async def create_portal_session(
    body: PortalRequest,
    request: Request,
    user: CurrentUser,
) -> PortalResponse:
    """Create a Stripe Customer Portal session."""
    billing_service = _get_billing_service(request)
    stripe_service = _get_stripe_service(request)
    account = await billing_service.repository.get_account(user.id)
    customer_id = account.stripe_customer_id if account else None
    if not customer_id:
        raise HTTPException(status_code=400, detail="Cliente Stripe não encontrado")

    portal = await stripe_service.create_portal_session(
        customer_id=customer_id,
        return_url=body.return_url,
    )
    return PortalResponse(portal_url=portal["url"])


@router.post("/webhook", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> WebhookResponse:
    """Process Stripe webhooks and sync subscription state."""
    billing_service = _get_billing_service(request)
    stripe_service = _get_stripe_service(request)
    payload = await request.body()

    try:
        event = stripe_service.verify_webhook_event(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=400, detail="Assinatura de webhook inválida")

    event_id = str(event.get("id", ""))
    if not event_id:
        raise HTTPException(status_code=400, detail="Evento Stripe sem ID")

    is_new = await billing_service.process_webhook_event_id(event_id)
    if not is_new:
        return WebhookResponse(received=True, processed=False)

    event_type = str(event.get("type", ""))
    data_object = event.get("data", {}).get("object", {})

    price_mapping = {
        k: PlanCode(v)
        for k, v in stripe_service.price_mapping.items()
        if k
    }

    if event_type == "checkout.session.completed":
        subscription_id = data_object.get("subscription")
        customer_id = data_object.get("customer")
        user_id = data_object.get("client_reference_id") or data_object.get("metadata", {}).get("user_id")
        if subscription_id and customer_id:
            try:
                snapshot = await stripe_service.fetch_subscription_snapshot(
                    str(subscription_id), user_id=user_id
                )
                await billing_service.apply_subscription_snapshot(
                    snapshot, price_mapping=price_mapping
                )
            except ValueError as e:
                logger.warning(
                    "stripe_checkout_snapshot_invalid",
                    event_id=event_id,
                    error=str(e),
                )
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        try:
            snapshot = stripe_service.subscription_snapshot_from_object(data_object)
            await billing_service.apply_subscription_snapshot(
                snapshot, price_mapping=price_mapping
            )
        except ValueError as e:
            logger.warning(
                "stripe_subscription_snapshot_invalid",
                event_id=event_id,
                error=str(e),
            )
    elif event_type == "invoice.payment_failed":
        customer_id = data_object.get("customer")
        if customer_id:
            account = await billing_service.repository.get_account_by_customer_id(str(customer_id))
            if account:
                account.subscription_status = "past_due"
                await billing_service.repository.upsert_account(account)

    logger.info("stripe_webhook_processed", event_id=event_id, event_type=event_type)
    return WebhookResponse(received=True, processed=True)
