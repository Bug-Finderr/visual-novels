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


def record_failure(order_id: str, event_type: str, payload: dict) -> None:
    """Store WHY a payment didn't land, from PAYMENT_FAILED_WEBHOOK or
    PAYMENT_USER_DROPPED_WEBHOOK.

    'abandoned' (customer walked away at the OTP / UPI-PIN step) is recorded
    separately from 'failed' (the bank said no) because they mean different
    things: the first is usually a checkout-friction problem you can fix, the
    second usually isn't.

    Never touches an order that already paid — a customer may fail once and
    succeed on retry, and the successful attempt is the one that counts.
    """
    payment = (payload.get("data") or {}).get("payment") or {}
    err = payment.get("error_details") or {}
    status = "abandoned" if event_type == "PAYMENT_USER_DROPPED_WEBHOOK" else "failed"

    with db() as conn:
        conn.execute(
            "UPDATE payment_orders SET status = ?, failure_code = ?, failure_reason = ?,"
            " failure_description = ?, last_event_type = ?,"
            " cf_payment_id = COALESCE(?, cf_payment_id),"
            " updated_at = CURRENT_TIMESTAMP"
            " WHERE order_id = ? AND credited_at IS NULL",
            (
                status,
                err.get("error_code"),
                err.get("error_reason"),
                err.get("error_description") or payment.get("payment_message"),
                event_type,
                str(payment.get("cf_payment_id") or "") or None,
                order_id,
            ),
        )
    logger.info("billing: order %s -> %s (%s)", order_id, status,
                err.get("error_reason") or err.get("error_code") or "no reason given")


def apply_refund(payload: dict, raw: str) -> dict:
    """Record a refund and take its credits back.

    Refunds are issued from the Cashfree dashboard, so this webhook is the ONLY
    way the app learns money went back. Without it the customer keeps both the
    refund and the credits.

    Credits are reclaimed in proportion to the amount refunded, so a partial
    refund takes back a proportional share. The clawback is allowed to push the
    balance negative: if they already spent the credits, that debt is the true
    state and blocks further generation until they top up again.
    """
    refund = (payload.get("data") or {}).get("refund") or {}
    cf_refund_id = str(refund.get("cf_refund_id") or "")
    order_id = refund.get("order_id") or ""
    if not cf_refund_id or not order_id:
        raise BillingError("Refund webhook missing cf_refund_id/order_id")

    status = (refund.get("refund_status") or "").upper()
    amount_paise = round(float(refund.get("refund_amount") or 0) * 100)

    with db() as conn:
        order = conn.execute(
            "SELECT * FROM payment_orders WHERE order_id = ? FOR UPDATE", (order_id,)
        ).fetchone()
        if not order:
            raise BillingError(f"Refund for unknown order '{order_id}'")

        existing = conn.execute(
            "SELECT credits_reclaimed FROM refunds WHERE cf_refund_id = ?", (cf_refund_id,)
        ).fetchone()

        if not existing:
            conn.execute(
                "INSERT INTO refunds (cf_refund_id, order_id, user_id, refund_id,"
                " amount_paise, status, refund_type, status_description, processed_at,"
                " raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cf_refund_id, order_id, order["user_id"], refund.get("refund_id"),
                 amount_paise, status, refund.get("refund_type"),
                 refund.get("status_description"), refund.get("processed_at"), raw[:8000]),
            )
        else:
            conn.execute(
                "UPDATE refunds SET status = ?, status_description = ?, raw_payload = ?"
                " WHERE cf_refund_id = ?",
                (status, refund.get("status_description"), raw[:8000], cf_refund_id),
            )

        # Only a SUCCESS moves credits, and only once — credits_reclaimed being
        # non-null is the guard against a re-delivered webhook clawing twice.
        if status != "SUCCESS" or (existing and existing["credits_reclaimed"] is not None):
            return {"reclaimed": 0, "status": status, "orderId": order_id}

        paid_paise = int(order["amount_paise"]) or 1
        # Cap against what is STILL reclaimable, not just against the pack
        # size: several refunds can land on one order, and their sum must
        # never take back more credits than the order granted. Without this a
        # duplicate refund under a fresh cf_refund_id would put an honest
        # customer into false debt.
        remaining = int(order["credits"]) - int(order["credits_reclaimed"] or 0)
        credits_back = max(0, min(
            remaining,
            round(int(order["credits"]) * amount_paise / paid_paise),
        ))
        if credits_back <= 0:
            conn.execute(
                "UPDATE refunds SET credits_reclaimed = 0, reclaimed_at = CURRENT_TIMESTAMP"
                " WHERE cf_refund_id = ?", (cf_refund_id,))
            return {"reclaimed": 0, "status": status, "orderId": order_id}

        credits.ensure_account(conn, order["user_id"])
        balance = credits.apply(
            conn, order["user_id"], -credits_back, credits.REFUND_REVERSAL,
            ref_type="refund", ref_id=cf_refund_id,
            idempotency_key=f"refund:{cf_refund_id}",
            allow_negative=True,
        )
        conn.execute(
            "UPDATE refunds SET credits_reclaimed = ?, reclaimed_at = CURRENT_TIMESTAMP"
            " WHERE cf_refund_id = ?", (credits_back, cf_refund_id))

        total_refunded = int(order["refunded_paise"]) + amount_paise
        conn.execute(
            "UPDATE payment_orders SET refunded_paise = ?,"
            " credits_reclaimed = credits_reclaimed + ?, refunded_at = CURRENT_TIMESTAMP,"
            " status = ?, last_event_type = ?, updated_at = CURRENT_TIMESTAMP"
            " WHERE order_id = ?",
            (total_refunded, credits_back,
             "refunded" if total_refunded >= paid_paise else "partially_refunded",
             payload.get("type"), order_id),
        )

    logger.info("billing: refund %s on order %s reclaimed %d credit(s) from %s (balance now %s)",
                cf_refund_id, order_id, credits_back, order["user_id"], balance)
    return {"reclaimed": credits_back, "status": status, "orderId": order_id,
            "balance": balance}


def _describe_attempts(order_id: str, local: dict, raw: str) -> dict:
    """Turn the order's payment attempts into something the UI can say out loud.

    Returns one of: 'pending' (nothing tried yet, or still in flight),
    'failed' (declined), 'abandoned' (walked away mid-checkout). The reason
    is carried through so the customer sees 'card declined' rather than a
    spinner that never resolves.
    """
    try:
        payments = cashfree.get_order_payments(order_id)
    except cashfree.CashfreeError as err:
        logger.warning("billing: could not read attempts for %s: %s", order_id, err)
        return {"credited": False, "status": "pending", "credits": local["credits"]}

    attempt = cashfree.latest_attempt(payments)
    if not attempt:
        # Nobody has tried to pay yet — the customer may still be on the
        # checkout page, or closed it without entering anything.
        return {"credited": False, "status": "pending", "credits": local["credits"]}

    attempt_status = (attempt.get("payment_status") or "").upper()
    if attempt_status in cashfree.ATTEMPT_PENDING or attempt_status == "SUCCESS":
        # SUCCESS here with a non-PAID order means Cashfree hasn't settled it
        # yet; the webhook or a later verify will pick it up.
        return {"credited": False, "status": "pending", "credits": local["credits"]}

    err = attempt.get("error_details") or {}
    reason = (err.get("error_description") or err.get("error_reason")
              or attempt.get("payment_message"))
    dropped = attempt_status in cashfree.ATTEMPT_DROPPED

    with db() as conn:
        conn.execute(
            "UPDATE payment_orders SET status = ?, failure_code = ?, failure_reason = ?,"
            " failure_description = ?, cf_payment_id = COALESCE(?, cf_payment_id),"
            " raw_status_payload = ?, updated_at = CURRENT_TIMESTAMP"
            " WHERE order_id = ? AND credited_at IS NULL",
            ("abandoned" if dropped else "failed", err.get("error_code"),
             err.get("error_reason"), reason,
             str(attempt.get("cf_payment_id") or "") or None, raw, order_id),
        )

    logger.info("billing: order %s attempt %s (%s)", order_id, attempt_status,
                reason or "no reason given")
    return {
        "credited": False,
        "status": "abandoned" if dropped else "failed",
        "reason": reason,
        "credits": local["credits"],
    }


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
            return {"credited": False, "status": "expired" if status == "EXPIRED" else "failed",
                    "credits": local["credits"]}
        # Order still ACTIVE. That does NOT mean "still processing" — a
        # declined or abandoned attempt leaves the order open for a retry. Ask
        # about the attempts themselves, so the customer gets told what
        # actually happened instead of an indefinite "confirming...".
        return _describe_attempts(order_id, local, raw)

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
