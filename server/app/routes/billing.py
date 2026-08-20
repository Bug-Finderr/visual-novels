"""Billing routes: credit balance, packs, Cashfree checkout, and the webhook.

Flow: the SPA asks for /packs, POSTs /orders to get a `paymentSessionId`,
hands that to the Cashfree JS SDK, and the user pays on Cashfree's hosted page.
Settlement then arrives twice — once when the browser returns to
/billing/return (which calls /orders/{id}/verify) and once via the webhook.
Both are idempotent; see services/billing/orders.py.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.config import config
from app.logger import logger
from app.services.billing import cashfree, credits, orders, packs

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


class CreateOrderRequest(BaseModel):
    packId: str
    phone: str


def _account_payload(user_id: str) -> dict:
    account = credits.get_or_create_account(user_id)
    return {
        "balance": int(account["balance"]),
        "lifetimePurchased": int(account["lifetime_purchased"]),
        "freeGranted": int(account["free_granted"]),
        "creditsPerStory": config.CREDITS_PER_GENERATION,
        "billingEnabled": config.BILLING_ENABLED,
    }


@router.get("/packs")
def list_packs():
    """Public storefront. `checkoutReady` is False when Cashfree credentials
    aren't configured yet — the UI shows prices but disables the buy button."""
    return {
        "packs": packs.listed(),
        "billingEnabled": config.BILLING_ENABLED,
        "checkoutReady": config.cashfree_configured,
        "mode": config.CASHFREE_ENV,
        "creditsPerStory": config.CREDITS_PER_GENERATION,
    }


@router.get("/account")
def get_account(user: dict = Depends(get_current_user)):
    return _account_payload(user["id"])


@router.get("/ledger")
def get_ledger(limit: int = 50, user: dict = Depends(get_current_user)):
    rows = credits.ledger(user["id"], limit)
    return {
        "entries": [
            {
                "delta": r["delta"],
                "reason": r["reason"],
                "balanceAfter": r["balance_after"],
                "refType": r["ref_type"],
                "refId": r["ref_id"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("/orders", status_code=201)
def create_order(payload: CreateOrderRequest, user: dict = Depends(get_current_user)):
    if not config.BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Billing is not enabled.")
    if not config.cashfree_configured:
        raise HTTPException(status_code=503, detail="Payments are not configured yet.")
    try:
        return orders.start_order(user, payload.packId, payload.phone)
    except orders.BillingError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except cashfree.CashfreeError as err:
        logger.error("billing: order creation failed for %s: %s", user["id"], err)
        raise HTTPException(status_code=502, detail="Could not reach the payment gateway.")


@router.post("/orders/{order_id}/verify")
def verify_order(order_id: str, user: dict = Depends(get_current_user)):
    """Called when the browser returns from checkout. Gives the user an
    immediate answer instead of waiting on webhook delivery — and is the only
    settlement path testable locally, since Cashfree can't reach localhost."""
    order = orders.get(order_id)
    if not order or order["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        result = orders.sync_from_cashfree(order_id)
    except cashfree.CashfreeError as err:
        logger.error("billing: verify failed for %s: %s", order_id, err)
        raise HTTPException(status_code=502, detail="Could not reach the payment gateway.")
    return {**result, "balance": credits.balance(user["id"])}


@router.post("/webhook/cashfree")
async def cashfree_webhook(request: Request):
    """Cashfree's server-to-server notification. No auth — authenticity comes
    from the HMAC signature, which is why the RAW body must be read before
    anything parses it (re-serializing the JSON changes the bytes and the
    signature would no longer match)."""
    raw = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")

    if not cashfree.verify_webhook(raw, timestamp, signature):
        logger.warning("billing: rejected webhook with a bad signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed payload")

    data = body.get("data") or {}
    event_type = body.get("type") or ""
    # Refund events carry the order id under data.refund, payment events under
    # data.order.
    order_id = (
        (data.get("order") or {}).get("order_id")
        or (data.get("refund") or {}).get("order_id")
        or ""
    )
    raw_text = raw.decode("utf-8", "replace")

    # Replayed signature -> already handled; ack so Cashfree stops retrying.
    if not orders.record_webhook(signature, event_type, order_id, raw_text):
        logger.info("billing: ignoring replayed webhook for order %s", order_id)
        return {"ok": True, "duplicate": True}

    try:
        if event_type in ("REFUND_STATUS_WEBHOOK", "AUTO_REFUND_STATUS_WEBHOOK"):
            # Refunds are raised from the Cashfree dashboard, so this is the
            # only signal that money went back — without it the customer keeps
            # the credits they were refunded for.
            orders.apply_refund(body, raw_text)

        elif event_type in ("PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK"):
            if order_id:
                orders.record_failure(order_id, event_type, body)

        elif order_id:
            # Success (and anything unrecognised that names an order): re-read
            # from Cashfree rather than trusting the payload that money moved.
            orders.sync_from_cashfree(order_id)

    except (orders.BillingError, cashfree.CashfreeError) as err:
        # 200 anyway: a retry would hit the same error, and the order can still
        # be settled by the user's verify call or by hand. The raw payload is
        # already stored, so nothing is lost.
        logger.error("billing: webhook processing failed for %s (%s): %s",
                     order_id, event_type, err)
        return {"ok": True, "processed": False}

    orders.mark_webhook_processed(signature)
    return {"ok": True}
