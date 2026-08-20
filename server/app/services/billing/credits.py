"""Credit balances and the append-only ledger.

Every balance change goes through `apply()`, which is a lock-free
compare-and-swap: a single conditional UPDATE that refuses to take the balance
below zero, plus one ledger row. Two concurrent spends can't both win — the
loser gets rowcount 0 and is told there aren't enough credits.

The write helpers take an explicit `conn` so callers can put a debit in the
SAME transaction as the thing being paid for (see routes/generation.py, where
the debit and the session status claim must commit or roll back together).
"""
from __future__ import annotations

import uuid

from app.config import config
from app.db.database import db

# Ledger reasons.
SIGNUP_GRANT = "signup_grant"
PURCHASE = "purchase"
GENERATION = "generation"
REFUND = "refund"
ADMIN = "admin"


def _row(conn, user_id: str) -> dict | None:
    return conn.execute(
        "SELECT user_id, balance, lifetime_purchased, free_granted"
        " FROM credit_accounts WHERE user_id = ?",
        (user_id,),
    ).fetchone()


def apply(
    conn,
    user_id: str,
    delta: int,
    reason: str,
    *,
    ref_type: str | None = None,
    ref_id: str | None = None,
    idempotency_key: str | None = None,
) -> int | None:
    """Move `user_id`'s balance by `delta` inside the CALLER'S transaction.

    Returns the new balance, or None if the move was refused because it would
    have gone negative. The guard is in the WHERE clause, so it is decided by
    the database under concurrency, not by a read-then-write in Python.

    `idempotency_key` is UNIQUE on the ledger — pass one for anything that can
    be delivered twice (purchases) and the second attempt raises rather than
    double-crediting.
    """
    updated = conn.execute(
        "UPDATE credit_accounts"
        " SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP"
        "  WHERE user_id = ? AND balance + ? >= 0"
        " RETURNING balance",
        (delta, user_id, delta),
    ).fetchone()
    if not updated:
        return None

    balance_after = int(updated["balance"])
    conn.execute(
        "INSERT INTO credit_ledger"
        " (id, user_id, delta, reason, balance_after, ref_type, ref_id, idempotency_key)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, user_id, delta, reason, balance_after,
         ref_type, ref_id, idempotency_key),
    )
    if delta > 0 and reason == PURCHASE:
        conn.execute(
            "UPDATE credit_accounts SET lifetime_purchased = lifetime_purchased + ?"
            " WHERE user_id = ?",
            (delta, user_id),
        )
    return balance_after


def get_or_create_account(user_id: str) -> dict:
    """Read a user's account, creating it — with the free signup grant — on
    first touch. Lazy rather than granted at signup so accounts that predate
    billing get backfilled the first time they load the billing page.

    `free_granted` records what was actually handed out, so changing
    FREE_STORY_CREDITS later never re-grants to an existing user.
    """
    with db() as conn:
        row = _row(conn, user_id)
        if row:
            return row

        grant = max(0, int(config.FREE_STORY_CREDITS))
        created = conn.execute(
            "INSERT INTO credit_accounts (user_id, balance, free_granted)"
            " VALUES (?, ?, ?) ON CONFLICT (user_id) DO NOTHING"
            " RETURNING user_id",
            (user_id, grant, grant),
        ).fetchone()

        # No row back means a concurrent request created the account first;
        # skip the grant ledger entry and just read what they wrote.
        if created and grant:
            conn.execute(
                "INSERT INTO credit_ledger"
                " (id, user_id, delta, reason, balance_after, idempotency_key)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, user_id, grant, SIGNUP_GRANT, grant,
                 f"{SIGNUP_GRANT}:{user_id}"),
            )
        return _row(conn, user_id) or {
            "user_id": user_id, "balance": 0, "lifetime_purchased": 0, "free_granted": 0,
        }


def balance(user_id: str) -> int:
    return int(get_or_create_account(user_id)["balance"])


def ensure_account(conn, user_id: str) -> None:
    """Create the account row (with grant) if missing, inside the caller's
    transaction. Used before a debit so a first-ever action can't fail merely
    because the row hasn't been materialized yet."""
    if _row(conn, user_id):
        return
    grant = max(0, int(config.FREE_STORY_CREDITS))
    created = conn.execute(
        "INSERT INTO credit_accounts (user_id, balance, free_granted)"
        " VALUES (?, ?, ?) ON CONFLICT (user_id) DO NOTHING RETURNING user_id",
        (user_id, grant, grant),
    ).fetchone()
    if created and grant:
        conn.execute(
            "INSERT INTO credit_ledger"
            " (id, user_id, delta, reason, balance_after, idempotency_key)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, grant, SIGNUP_GRANT, grant,
             f"{SIGNUP_GRANT}:{user_id}"),
        )


def refund(user_id: str, amount: int, *, ref_type: str, ref_id: str,
           idempotency_key: str | None = None) -> int | None:
    """Give credits back in a transaction of its own — used by the generation
    pipeline's failure path, which runs long after the request has returned."""
    with db() as conn:
        ensure_account(conn, user_id)
        return apply(conn, user_id, abs(amount), REFUND,
                     ref_type=ref_type, ref_id=ref_id, idempotency_key=idempotency_key)


def ledger(user_id: str, limit: int = 50) -> list[dict]:
    with db() as conn:
        return conn.execute(
            "SELECT delta, reason, balance_after, ref_type, ref_id, created_at"
            " FROM credit_ledger WHERE user_id = ?"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, max(1, min(int(limit), 200))),
        ).fetchall()
