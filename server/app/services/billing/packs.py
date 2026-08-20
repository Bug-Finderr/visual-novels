"""The purchasable credit packs.

Single source of truth for pricing: the frontend renders whatever this serves,
and an order's price is looked up here (never taken from the request body), so
the UI and the charge can't drift apart.

Sizing: one credit is one story generation, which costs ~Rs.110 in Gemini spend
(26 images at $0.039 plus ~Rs.24 of text, measured). Bulk tiers discount toward
Rs.170/story, which is the floor that still leaves a real margin after
Cashfree's ~2.4% and infrastructure.
"""
from __future__ import annotations

PACKS: dict[str, dict] = {
    "taster": {"id": "taster", "name": "Taster", "credits": 1, "amount_paise": 19900},
    "author": {"id": "author", "name": "Author", "credits": 5, "amount_paise": 89900},
    "studio": {"id": "studio", "name": "Studio", "credits": 10, "amount_paise": 169900},
}


def get(pack_id: str) -> dict | None:
    return PACKS.get((pack_id or "").strip().lower())


def listed() -> list[dict]:
    """Packs for the storefront, cheapest first, with display fields derived
    here so the client never does money arithmetic."""
    out = []
    for pack in sorted(PACKS.values(), key=lambda p: p["amount_paise"]):
        out.append({
            **pack,
            "amountRupees": pack["amount_paise"] / 100,
            "perCreditRupees": round(pack["amount_paise"] / 100 / pack["credits"]),
        })
    return out
