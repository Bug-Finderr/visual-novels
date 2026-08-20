"""Billing operations report — revenue, failures, refunds, and stuck orders.

Read-only. Answers the questions you actually have in week one: how much came
in, what is going wrong at checkout, did anything get paid without being
credited, and is anyone carrying a negative balance after a refund.

Run:  cd server && ./.venv/bin/python scripts/billing_report.py
      ./.venv/bin/python scripts/billing_report.py --days 7
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import db  # noqa: E402


def _rupees(paise) -> str:
    return f"Rs.{(paise or 0) / 100:,.2f}"


def _table(rows: list[dict], cols: list[tuple[str, str]]) -> None:
    """Print rows as an aligned table. cols is [(key, heading)]."""
    if not rows:
        print("    (none)")
        return
    widths = {k: max(len(h), max(len(str(r.get(k) or "")) for r in rows)) for k, h in cols}
    print("    " + "  ".join(h.ljust(widths[k]) for k, h in cols))
    print("    " + "  ".join("-" * widths[k] for k, _ in cols))
    for r in rows:
        print("    " + "  ".join(str(r.get(k) or "").ljust(widths[k]) for k, _ in cols))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="window to report on (default 30)")
    args = ap.parse_args()
    since = f"CURRENT_TIMESTAMP - INTERVAL '{int(args.days)} days'"

    print(f"\n{'=' * 68}\n  StoryPlex billing — last {args.days} days\n{'=' * 68}")

    with db() as conn:
        # ---------------------------------------------------------------
        print("\n  REVENUE")
        rev = conn.execute(
            f"SELECT COUNT(*) AS orders, COALESCE(SUM(amount_paise),0) AS gross,"
            f" COALESCE(SUM(credits),0) AS credits"
            f" FROM payment_orders WHERE credited_at IS NOT NULL AND created_at >= {since}"
        ).fetchone()
        ref = conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(amount_paise),0) AS amt,"
            f" COALESCE(SUM(credits_reclaimed),0) AS credits"
            f" FROM refunds WHERE status = 'SUCCESS' AND created_at >= {since}"
        ).fetchone()
        net = (rev["gross"] or 0) - (ref["amt"] or 0)
        print(f"    paid orders     {rev['orders']}")
        print(f"    gross           {_rupees(rev['gross'])}")
        print(f"    refunded        {_rupees(ref['amt'])}  ({ref['n']} refund(s))")
        print(f"    net             {_rupees(net)}")
        print(f"    credits sold    {rev['credits']}  (reclaimed {ref['credits']})")

        # ---------------------------------------------------------------
        print("\n  CHECKOUT OUTCOMES")
        outcomes = conn.execute(
            f"SELECT status, COUNT(*) AS n, SUM(amount_paise) AS paise"
            f" FROM payment_orders WHERE created_at >= {since}"
            f" GROUP BY status ORDER BY n DESC"
        ).fetchall()
        total = sum(o["n"] for o in outcomes) or 1
        _table(
            [{"status": o["status"], "count": o["n"],
              "share": f"{o['n'] / total * 100:.0f}%", "value": _rupees(o["paise"])}
             for o in outcomes],
            [("status", "STATUS"), ("count", "COUNT"), ("share", "SHARE"), ("value", "VALUE")],
        )
        paid = next((o["n"] for o in outcomes if o["status"] == "paid"), 0)
        print(f"\n    conversion      {paid / total * 100:.0f}% of orders started end up paid")

        # ---------------------------------------------------------------
        print("\n  WHY PAYMENTS FAIL")
        fails = conn.execute(
            f"SELECT COALESCE(failure_reason, failure_code, '(not reported)') AS reason,"
            f" last_event_type AS event, COUNT(*) AS n"
            f" FROM payment_orders"
            f" WHERE status IN ('failed','abandoned') AND created_at >= {since}"
            f" GROUP BY 1, 2 ORDER BY n DESC LIMIT 15"
        ).fetchall()
        _table(
            [{"reason": f["reason"][:44], "event": (f["event"] or "").replace("_WEBHOOK", ""),
              "count": f["n"]} for f in fails],
            [("reason", "REASON"), ("event", "EVENT"), ("count", "COUNT")],
        )

        # ---------------------------------------------------------------
        print("\n  NEEDS ATTENTION")
        stuck = conn.execute(
            "SELECT order_id, status, amount_paise, created_at FROM payment_orders"
            " WHERE credited_at IS NULL AND status = 'created'"
            "   AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'"
            " ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        print("    Orders open over an hour (customer may have paid without being credited —")
        print("    re-run POST /billing/orders/{id}/verify, it is idempotent):")
        _table(
            [{"order": s["order_id"], "value": _rupees(s["amount_paise"]),
              "opened": str(s["created_at"])[:19]} for s in stuck],
            [("order", "ORDER"), ("value", "VALUE"), ("opened", "OPENED")],
        )

        negative = conn.execute(
            "SELECT u.username, ca.balance FROM credit_accounts ca"
            " JOIN users u ON u.id = ca.user_id WHERE ca.balance < 0 ORDER BY ca.balance"
        ).fetchall()
        print("\n    Negative balances (credits spent, then refunded — blocked until they top up):")
        _table([{"user": n["username"], "balance": n["balance"]} for n in negative],
               [("user", "USER"), ("balance", "BALANCE")])

        unprocessed = conn.execute(
            f"SELECT event_type, COUNT(*) AS n FROM webhook_events"
            f" WHERE processed_at IS NULL AND received_at >= {since}"
            f" GROUP BY event_type ORDER BY n DESC"
        ).fetchall()
        print("\n    Webhooks received but not processed (signature ok, handler errored):")
        _table([{"event": u["event_type"], "count": u["n"]} for u in unprocessed],
               [("event", "EVENT"), ("count", "COUNT")])

        # ---------------------------------------------------------------
        print("\n  CREDIT SUPPLY")
        supply = conn.execute(
            "SELECT reason, COUNT(*) AS n, SUM(delta) AS total FROM credit_ledger"
            " GROUP BY reason ORDER BY ABS(SUM(delta)) DESC"
        ).fetchall()
        _table([{"reason": s["reason"], "entries": s["n"],
                 "net": f"{s['total']:+d}"} for s in supply],
               [("reason", "REASON"), ("entries", "ENTRIES"), ("net", "NET CREDITS")])

        outstanding = conn.execute(
            "SELECT COALESCE(SUM(balance),0) AS n FROM credit_accounts WHERE balance > 0"
        ).fetchone()["n"]
        print(f"\n    outstanding     {outstanding} credits held by users")
        print(f"    liability       ~{_rupees(outstanding * 11000)} of Gemini spend if all are used")

    print(f"\n{'=' * 68}\n")


if __name__ == "__main__":
    main()
