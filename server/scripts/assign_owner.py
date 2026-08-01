"""ADMIN one-time: assign all currently-unowned stories to a user (by email).

    cd server && python3 scripts/assign_owner.py you@example.com

This is a migration/admin action for legacy data created before accounts
existed. It is intentionally NOT exposed in the app — users cannot claim
content that isn't theirs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.db.base import engine  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python3 scripts/assign_owner.py <email>")
        return
    email = sys.argv[1].strip()
    with engine.begin() as conn:
        user = conn.execute(
            text("SELECT id, username FROM users WHERE email = :email"), {"email": email}
        ).fetchone()
        if not user:
            print(f"No user with email {email!r}. Sign in with that account first.")
            return
        uid, uname = user[0], user[1]
        result = conn.execute(
            text("UPDATE sessions SET owner_id = :uid WHERE owner_id IS NULL"), {"uid": uid}
        )
        print(f"Assigned {result.rowcount} unowned stories to {uname} <{email}>.")


if __name__ == "__main__":
    main()
