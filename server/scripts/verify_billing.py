"""Verification of the billing money-paths against a REAL Postgres.

No Cashfree network calls and no Gemini spend — the gateway is stubbed, but
every balance/ledger/order write is the real thing, because the properties
worth checking here (can two concurrent spends both win? can a webhook replay
credit twice?) only exist at the database level.

Exercises:
  1. free signup grant is handed out exactly once
  2. balance can never go negative; the ledger mirrors every move
  3. CONCURRENT /generate: exactly one wins, one debit, no double pipeline
  4. insufficient credits rolls the session status claim back too
  5. webhook signature verification (good, tampered, wrong secret)
  6. settle() is idempotent — webhook + return-url verify credit once
  7. amount mismatch refuses to credit

Run:  cd server && ./.venv/bin/python scripts/verify_billing.py
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "unused-mock-key")
os.environ["BILLING_ENABLED"] = "1"
os.environ["FREE_STORY_CREDITS"] = "2"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config  # noqa: E402
from app.db.database import db  # noqa: E402
from app.db.queries import sessions as session_queries  # noqa: E402
from app.services.billing import cashfree, credits, orders  # noqa: E402

_failures: list[str] = []


def _assert(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        _failures.append(label)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _mk_user() -> str:
    uid = uuid.uuid4().hex
    with db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, username) VALUES (?, ?, ?)",
            (uid, f"{uid[:12]}@verify.local", f"verify_{uid[:12]}"),
        )
    return uid


def _mk_session(owner_id: str) -> str:
    sid = uuid.uuid4().hex
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, status, setup_genre, setup_art_style,"
            " setup_setting, setup_protagonist_name, setup_protagonist_personality,"
            " setup_tone, owner_id) VALUES (?, 'verify', 'created', 'Fantasy', 'anime',"
            " 'a place', 'Rin', 'brave', 'Dark', ?)",
            (sid, owner_id),
        )
    return sid


def _cleanup(user_ids: list[str]) -> None:
    with db() as conn:
        for uid in user_ids:
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))  # cascades


def _status(session_id: str) -> str:
    return session_queries.get_by_id(session_id)["status"]


def _ledger_count(user_id: str, reason: str) -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM credit_ledger WHERE user_id = ? AND reason = ?",
            (user_id, reason),
        ).fetchone()["n"]


# --------------------------------------------------------------------------
def check_grant(uid: str) -> None:
    print("\n[1] free signup grant")
    acct = credits.get_or_create_account(uid)
    _assert(acct["balance"] == 2, "first touch grants FREE_STORY_CREDITS (2)")
    _assert(acct["free_granted"] == 2, "grant size is recorded on the account")

    credits.get_or_create_account(uid)
    credits.get_or_create_account(uid)
    _assert(credits.balance(uid) == 2, "repeated reads do NOT re-grant")
    _assert(_ledger_count(uid, credits.SIGNUP_GRANT) == 1, "exactly one grant ledger row")


def check_floor(uid: str) -> None:
    print("\n[2] balance floor + ledger mirror")
    with db() as conn:
        after = credits.apply(conn, uid, -1, credits.GENERATION, ref_type="session", ref_id="s1")
    _assert(after == 1, "spending 1 of 2 leaves 1")

    with db() as conn:
        refused = credits.apply(conn, uid, -5, credits.GENERATION, ref_type="session", ref_id="s2")
    _assert(refused is None, "overspend is refused (returns None)")
    _assert(credits.balance(uid) == 1, "refused spend left the balance untouched")

    entries = credits.ledger(uid)
    _assert(len(entries) == 2, "ledger has grant + the one accepted spend, not the refusal")
    _assert(entries[0]["balance_after"] == 1, "newest ledger row carries the running balance")


def check_race() -> str:
    print("\n[3] concurrent /generate — exactly one winner")
    uid = _mk_user()
    credits.get_or_create_account(uid)
    with db() as conn:  # trim to exactly 1 credit
        credits.apply(conn, uid, -1, credits.ADMIN)
    sid = _mk_session(uid)

    from app.routes.generation import _InsufficientCredits, _claim_and_charge

    def attempt(_):
        try:
            return _claim_and_charge(sid, uid)
        except _InsufficientCredits:
            return "insufficient"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    wins = [r for r in results if r is None]
    _assert(len(wins) == 1, f"exactly 1 of 8 concurrent calls won (got {len(wins)})")
    _assert(credits.balance(uid) == 0, "exactly one credit was spent")
    _assert(_ledger_count(uid, credits.GENERATION) == 1, "exactly one debit ledger row")
    _assert(_status(sid) == "generating", "session ended up claimed")
    return uid


def check_rollback() -> str:
    print("\n[4] insufficient credits rolls back the status claim")
    uid = _mk_user()
    credits.get_or_create_account(uid)
    with db() as conn:
        credits.apply(conn, uid, -2, credits.ADMIN)  # spend the grant
    _assert(credits.balance(uid) == 0, "user starts broke")

    sid = _mk_session(uid)
    from app.routes.generation import _InsufficientCredits, _claim_and_charge

    raised = False
    try:
        _claim_and_charge(sid, uid)
    except _InsufficientCredits:
        raised = True

    _assert(raised, "charge raises when the balance is short")
    _assert(_status(sid) == "created",
            "session is still 'created' — the claim rolled back with the debit")
    return uid


def check_signature() -> None:
    print("\n[5] webhook signature verification")
    import base64
    import hashlib
    import hmac

    secret = "test_secret_key"
    config.CASHFREE_SECRET_KEY = secret
    config.CASHFREE_WEBHOOK_SECRET = None

    body = b'{"type":"PAYMENT_SUCCESS_WEBHOOK","data":{"order":{"order_id":"sp_x"}}}'
    ts = "1755690000"
    good = base64.b64encode(
        hmac.new(secret.encode(), (ts + body.decode()).encode(), hashlib.sha256).digest()
    ).decode()

    _assert(cashfree.verify_webhook(body, ts, good), "correct signature verifies")
    _assert(not cashfree.verify_webhook(body + b" ", ts, good), "tampered body is rejected")
    _assert(not cashfree.verify_webhook(body, "1755690001", good), "wrong timestamp is rejected")
    _assert(not cashfree.verify_webhook(body, ts, "nonsense"), "garbage signature is rejected")

    config.CASHFREE_SECRET_KEY = "different_secret"
    _assert(not cashfree.verify_webhook(body, ts, good), "signature from another secret is rejected")
    config.CASHFREE_SECRET_KEY = secret


def check_settle_idempotency() -> str:
    print("\n[6] settlement is idempotent (webhook + verify race)")
    uid = _mk_user()
    credits.get_or_create_account(uid)
    start = credits.balance(uid)

    order_id = f"sp_{uuid.uuid4().hex}"
    with db() as conn:
        conn.execute(
            "INSERT INTO payment_orders (order_id, user_id, pack_id, credits, amount_paise,"
            " currency, status) VALUES (?, ?, 'author', 5, 89900, 'INR', 'created')",
            (order_id, uid),
        )

    first = orders.settle(order_id, cf_payment_id="pay_1", raw_payload="{}")
    _assert(first["credited"] is True, "first settle credits")
    _assert(credits.balance(uid) == start + 5, "balance rose by the pack's 5 credits")

    second = orders.settle(order_id, cf_payment_id="pay_1", raw_payload="{}")
    _assert(second["credited"] is False, "second settle is a no-op")
    _assert(credits.balance(uid) == start + 5, "balance did NOT move on the replay")
    _assert(_ledger_count(uid, credits.PURCHASE) == 1, "exactly one purchase ledger row")

    with db() as conn:
        acct = conn.execute(
            "SELECT lifetime_purchased FROM credit_accounts WHERE user_id = ?", (uid,)
        ).fetchone()
    _assert(acct["lifetime_purchased"] == 5, "lifetime_purchased counted once")

    # Concurrent settle: the FOR UPDATE lock must serialize these.
    order2 = f"sp_{uuid.uuid4().hex}"
    with db() as conn:
        conn.execute(
            "INSERT INTO payment_orders (order_id, user_id, pack_id, credits, amount_paise,"
            " currency, status) VALUES (?, ?, 'taster', 1, 19900, 'INR', 'created')",
            (order2, uid),
        )
    before = credits.balance(uid)
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(
            lambda _: orders.settle(order2, cf_payment_id="p", raw_payload="{}")["credited"],
            range(6),
        ))
    _assert(sum(outcomes) == 1, f"exactly 1 of 6 concurrent settles credited (got {sum(outcomes)})")
    _assert(credits.balance(uid) == before + 1, "concurrent settles granted 1 credit total")
    return uid


def check_amount_mismatch() -> str:
    print("\n[7] a short payment does not buy a full pack")
    uid = _mk_user()
    credits.get_or_create_account(uid)
    before = credits.balance(uid)

    order_id = f"sp_{uuid.uuid4().hex}"
    with db() as conn:
        conn.execute(
            "INSERT INTO payment_orders (order_id, user_id, pack_id, credits, amount_paise,"
            " currency, status) VALUES (?, ?, 'studio', 10, 169900, 'INR', 'created')",
            (order_id, uid),
        )

    real_get_order = cashfree.get_order
    # Gateway says PAID, but for Rs.1 instead of the Rs.1699 we recorded.
    cashfree.get_order = lambda oid: {"order_status": "PAID", "order_amount": 1.00}
    try:
        result = orders.sync_from_cashfree(order_id)
    finally:
        cashfree.get_order = real_get_order

    _assert(result["credited"] is False, "mismatched amount is not credited")
    _assert(result["status"] == "amount_mismatch", "reported as amount_mismatch")
    _assert(credits.balance(uid) == before, "balance untouched")
    _assert(orders.get(order_id)["status"] == "failed", "order marked failed")
    return uid


def main() -> None:
    print("Billing verification — real Postgres, stubbed gateway")
    print(f"DB: {config.DATABASE_URL.split('@')[-1]}")
    created: list[str] = []
    try:
        uid = _mk_user()
        created.append(uid)
        check_grant(uid)
        check_floor(uid)
        created.append(check_race())
        created.append(check_rollback())
        check_signature()
        created.append(check_settle_idempotency())
        created.append(check_amount_mismatch())
    finally:
        _cleanup(created)
        print(f"\n(cleaned up {len(created)} test users)")

    if _failures:
        print(f"\n{len(_failures)} CHECK(S) FAILED ❌")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nALL CHECKS PASSED ✅")


if __name__ == "__main__":
    main()
