"""Billing: prepaid story credits, paid for with Cashfree (INR).

- `packs`    — the purchasable credit packs (single source of truth for price).
- `credits`  — balances + the append-only ledger; all the money-safe writes.
- `cashfree` — thin REST client for the Cashfree Payment Gateway.
- `orders`   — order lifecycle: create → pay → settle (idempotently).
"""
