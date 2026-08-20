"""Order lifecycle: create -> pay at Cashfree -> settle (idempotently).

Two independent things can tell us an order was paid: the browser coming back
to the return URL, and the Cashfree webhook. Both funnel into `settle()`, which
is guarded three ways — a `SELECT ... FOR UPDATE` row lock, the
`payment_orders.credited_at` stamp, and the UNIQUE ledger idempotency key — so
whichever arrives second is a no-op rather than a double credit.

Neither path trusts its caller about whether money moved: `sync_from_cashfree`
always re-reads the order from Cashfree's API and checks the amount against
what we recorded when the order was created.
"""
from __future__ import annotations

import json
import uuid

from app.config import config
from app.db.database import db
from app.logger import logger
from app.services.billing import cashfree, credits, packs


class BillingError(RuntimeError):
    """A billing operation could not proceed (bad pack, unknown order, ...)."""


def _return_url(order_id: str) -> str:
    return f"{config.web_base}/billing/return?order_id={order_id}"


def _notify_url() -> str | None:
    base = (config.PUBLIC_API_BASE or "").rstrip("/")
    return f"{base}/api/v1/billing/webhook/cashfree" if base else None


def start_order(user: dict, pack_id: str, phone: str) -> dict:
    """Create a local order, then the matching Cashfree order.

    The local row is written FIRST on purpose: an order we know about that was
    never paid is harmless, whereas a payment against an order we have no
    record of is money we can't attribute.
    """
    pack = packs.get(pack_id)
    if not pack:
        raise BillingError(f"Unknown pack '{pack_id}'")

    phone = "".join(ch for ch in (phone or "") if ch.isdigit())[-10:]
    if len(phone) != 10:
        raise BillingError("A valid 10-digit phone number is required by the payment gateway.")

    order_id = f"sp_{uuid.uuid4().hex}"
    with db() as conn:
        conn.execute(
            "INSERT INTO payment_orders"
            " (order_id, user_id, pack_id, credits, amount_paise, currency, status, customer_phone)"
            " VALUES (?, ?, ?, ?, ?, 'INR', 'created', ?)",
            (order_id, user["id"], pack["id"], pack["credits"], pack["amount_paise"], phone),
        )

    try:
        created = cashfree.create_order(
            order_id=order_id,
            amount_paise=pack["amount_paise"],
            customer_id=user["id"],
            customer_email=user.get("email"),
            customer_phone=phone,
            return_url=_return_url(order_id),
            notify_url=_notify_url(),
        )
    except cashfree.CashfreeError:
        with db() as conn:
            conn.execute(
                "UPDATE payment_orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP"
                " WHERE order_id = ?",
                (order_id,),
            )
        raise

    session_id = created.get("payment_session_id")
    with db() as conn:
        conn.execute(
            "UPDATE payment_orders"
            " SET cf_order_id = ?, payment_session_id = ?, updated_at = CURRENT_TIMESTAMP"
            " WHERE order_id = ?",
            (created.get("cf_order_id"), session_id, order_id),
        )

    return {
        "orderId": order_id,
        "paymentSessionId": session_id,
        "mode": config.CASHFREE_ENV,
        "credits": pack["credits"],
        "amountRupees": pack["amount_paise"] / 100,
    }


def get(order_id: str) -> dict | None:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM payment_orders WHERE order_id = ?", (order_id,)
        ).fetchone()


def settle(order_id: str, *, cf_payment_id: str | None, raw_payload: str | None) -> dict:
    """Mark an order paid and grant its credits — exactly once.

    Returns {credited: bool, balance: int|None, status: str}. `credited` is
    False when the order was already settled, which is the normal outcome for
    whichever of (webhook, return-url verify) arrives second.
    """
    with db() as conn:
        # FOR UPDATE serializes the webhook against the return-url verify;
        # without it both could read credited_at as NULL and both credit.
        order = conn.execute(
            "SELECT * FROM payment_orders WHERE order_id = ? FOR UPDATE", (order_id,)
        ).fetchone()
        if not order:
            raise BillingError(f"Unknown order '{order_id}'")

        if order.get("credited_at") is not None:
            return {"credited": False, "balance": None, "status": "paid",
                    "credits": order["credits"]}

        conn.execute(
            "UPDATE payment_orders SET status = 'paid', credited_at = CURRENT_TIMESTAMP,"
            " cf_payment_id = COALESCE(?, cf_payment_id), raw_status_payload = ?,"
            " updated_at = CURRENT_TIMESTAMP WHERE order_id = ?",
            (cf_payment_id, raw_payload, order_id),
        )
        credits.ensure_account(conn, order["user_id"])
        balance = credits.apply(
            conn, order["user_id"], int(order["credits"]), credits.PURCHASE,
            ref_type="order", ref_id=order_id,
            idempotency_key=f"order:{order_id}",
        )

    logger.info("billing: credited %s credits to %s for order %s",
                order["credits"], order["user_id"], order_id)
    return {"credited": True, "balance": balance, "status": "paid",
            "credits": order["credits"]}


def mark_failed(order_id: str, status: str, raw_payload: str | None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE payment_orders SET status = ?, raw_status_payload = ?,"
            " updated_at = CURRENT_TIMESTAMP"
            " WHERE order_id = ? AND credited_at IS NULL",
            (status, raw_payload, order_id),
        )


def sync_from_cashfree(order_id: str) -> dict:
    """Re-read the order from Cashfree and settle it if genuinely paid.

    This is the ONLY place an order becomes paid. Both the return-url verify
    and the webhook route through here, so neither can credit on its own say-so
    — and the amount is checked against what we snapshotted at order time, so a
    short payment can't buy a full pack.
    """
    local = get(order_id)
    if not local:
        raise BillingError(f"Unknown order '{order_id}'")
    if local.get("credited_at") is not None:
        return {"credited": False, "status": "paid", "credits": local["credits"]}

    remote = cashfree.get_order(order_id)
    status = (remote.get("order_status") or "").upper()
    raw = json.dumps(remote, ensure_ascii=False)[:8000]

    if status != cashfree.PAID:
        if status in cashfree.FAILED_STATES:
            mark_failed(order_id, "expired" if status == "EXPIRED" else "failed", raw)
        return {"credited": False, "status": status.lower() or "pending",
                "credits": local["credits"]}

    paid_paise = round(float(remote.get("order_amount") or 0) * 100)
    if paid_paise != int(local["amount_paise"]):
        logger.error(
            "billing: order %s amount mismatch — charged %s paise, expected %s; not crediting",
            order_id, paid_paise, local["amount_paise"],
        )
        mark_failed(order_id, "failed", raw)
        return {"credited": False, "status": "amount_mismatch", "credits": local["credits"]}

    return settle(order_id, cf_payment_id=None, raw_payload=raw)


def record_webhook(signature: str, event_type: str | None, order_id: str | None,
                   payload: str) -> bool:
    """Log the webhook. Returns False if this exact signature was already seen,
    which means it's a replay and the caller should stop."""
    with db() as conn:
        inserted = conn.execute(
            "INSERT INTO webhook_events (id, signature, event_type, order_id, payload)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT (signature) DO NOTHING RETURNING id",
            (uuid.uuid4().hex, signature, event_type, order_id, payload[:8000]),
        ).fetchone()
    return bool(inserted)


def mark_webhook_processed(signature: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE webhook_events SET processed_at = CURRENT_TIMESTAMP WHERE signature = ?",
            (signature,),
        )
