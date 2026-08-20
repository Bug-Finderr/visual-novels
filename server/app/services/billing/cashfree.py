"""Cashfree Payment Gateway REST client.

Deliberately a thin httpx wrapper rather than the `cashfree-pg` SDK: httpx is
already a dependency, and this is three calls (create order, read order, verify
webhook signature). The SDK is a generated OpenAPI client and would pin us to
its release cadence for no benefit at this size.

API surface per the current reference (x-api-version 2026-01-01):
  POST {base}/orders            -> cf_order_id, payment_session_id, order_status
  GET  {base}/orders/{order_id} -> order_status in
                                   ACTIVE|PAID|EXPIRED|TERMINATED|TERMINATION_REQUESTED
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.config import config
from app.logger import logger

_BASE = {
    "sandbox": "https://sandbox.cashfree.com/pg",
    "production": "https://api.cashfree.com/pg",
}

# Terminal order states — nothing further will happen to the order.
PAID = "PAID"
FAILED_STATES = {"EXPIRED", "TERMINATED"}


class CashfreeError(RuntimeError):
    """A Cashfree call failed. Carries the upstream status + body for logs."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def base_url() -> str:
    return _BASE.get(config.CASHFREE_ENV, _BASE["sandbox"])


def _headers(idempotency_key: str | None = None) -> dict[str, str]:
    if not config.cashfree_configured:
        raise CashfreeError("Cashfree is not configured (CASHFREE_APP_ID / CASHFREE_SECRET_KEY)")
    headers = {
        "x-api-version": config.CASHFREE_API_VERSION,
        "x-client-id": config.CASHFREE_APP_ID,
        "x-client-secret": config.CASHFREE_SECRET_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }
    if idempotency_key:
        headers["x-idempotency-key"] = idempotency_key
    return headers


def _request(method: str, path: str, *, json: dict | None = None,
             idempotency_key: str | None = None) -> dict:
    url = f"{base_url()}{path}"
    try:
        resp = httpx.request(
            method, url, json=json, headers=_headers(idempotency_key),
            timeout=config.CASHFREE_TIMEOUT,
        )
    except httpx.HTTPError as err:
        raise CashfreeError(f"Cashfree request failed: {err}") from err

    if resp.status_code >= 400:
        # Cashfree returns {"message": ..., "code": ..., "type": ...} on error.
        detail = ""
        try:
            detail = resp.json().get("message") or ""
        except Exception:
            detail = resp.text[:500]
        logger.error("Cashfree %s %s -> %s: %s", method, path, resp.status_code, detail)
        raise CashfreeError(
            detail or f"Cashfree returned {resp.status_code}",
            status_code=resp.status_code,
            body=resp.text[:2000],
        )
    return resp.json()


def create_order(
    *,
    order_id: str,
    amount_paise: int,
    customer_id: str,
    customer_email: str | None,
    customer_phone: str,
    return_url: str,
    notify_url: str | None = None,
) -> dict:
    """Create a Cashfree order. Returns the raw order entity — the caller wants
    `payment_session_id`, which the JS SDK exchanges for a hosted checkout."""
    body = {
        "order_id": order_id,
        # Cashfree takes a decimal rupee amount; we hold paise internally and
        # convert only here, at the boundary.
        "order_amount": round(amount_paise / 100, 2),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": customer_id,
            "customer_email": customer_email or "",
            "customer_phone": customer_phone,
        },
        "order_meta": {"return_url": return_url},
    }
    if notify_url:
        body["order_meta"]["notify_url"] = notify_url
    # Our order_id is already unique per attempt, so it doubles as the
    # idempotency key: a retried create can't mint a second Cashfree order.
    return _request("POST", "/orders", json=body, idempotency_key=order_id)


def get_order(order_id: str) -> dict:
    """Authoritative server-side order state. Never trust the browser's word
    that a payment succeeded — always confirm through this."""
    return _request("GET", f"/orders/{order_id}")


def verify_webhook(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Cashfree signs `timestamp + raw_body` with the client secret,
    HMAC-SHA256, base64-encoded.

    `raw_body` MUST be the exact bytes received — re-serializing the parsed
    JSON changes whitespace/key order and the signature will not match.
    """
    secret = config.cashfree_webhook_secret
    if not (secret and timestamp and signature):
        return False
    mac = hmac.new(
        secret.encode("utf-8"),
        (timestamp + raw_body.decode("utf-8")).encode("utf-8"),
        hashlib.sha256,
    )
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(expected, signature)
