"""One-time copy of the legacy sqlite data into Postgres.

Idempotent (ON CONFLICT DO NOTHING). Run once, after the Alembic schema exists:

    cd server && python3 scripts/migrate_sqlite_to_pg.py

Sessions are copied first; child rows are only inserted when their parent
session exists (legacy sqlite has some orphaned rows from before FK enforcement).
Each row inserts inside a savepoint so one bad row never aborts the batch.
dialogue_history ids are reassigned by the Postgres sequence.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.config import config  # noqa: E402
from app.db.base import engine  # noqa: E402

TABLES = [
    "sessions",
    "characters",
    "scenes",
    "script_labels",
    "dialogue_history",
    "beat_expansions",
    "ending_dialogue",
    "saves",
]


def main() -> None:
    if not config.DB_PATH.exists():
        print(f"No sqlite db at {config.DB_PATH} — nothing to migrate.")
        return

    sq = sqlite3.connect(str(config.DB_PATH))
    sq.row_factory = sqlite3.Row
    grand_total = 0
    valid_sids: set[str] = set()

    for table in TABLES:
        try:
            rows = sq.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"{table}: (missing in sqlite, skipped)")
            continue
        if not rows:
            print(f"{table}: 0")
            if table == "sessions":
                valid_sids = _load_session_ids()
            continue

        cols = list(rows[0].keys())
        if table == "dialogue_history":
            cols = [c for c in cols if c != "id"]  # let the Postgres SERIAL assign ids

        # Drop orphaned children whose parent session no longer exists.
        if table != "sessions":
            rows = [r for r in rows if r["session_id"] in valid_sids]

        col_list = ", ".join(cols)
        binds = ", ".join(f":{c}" for c in cols)
        stmt = text(
            f"INSERT INTO {table} ({col_list}) VALUES ({binds}) ON CONFLICT DO NOTHING"
        )

        n = skipped = 0
        with engine.begin() as pg:
            for r in rows:
                try:
                    with pg.begin_nested():
                        pg.execute(stmt, {c: r[c] for c in cols})
                    n += 1
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    if skipped <= 3:
                        print(f"  ! skip {table} row: {str(exc)[:90]}")

        if table == "sessions":
            valid_sids = _load_session_ids()

        grand_total += n
        print(f"{table}: {n}" + (f"  (skipped {skipped} orphan/bad)" if skipped else ""))

    sq.close()
    print(f"\nMigrated {grand_total} rows into Postgres.")


def _load_session_ids() -> set[str]:
    with engine.connect() as pg:
        return {row[0] for row in pg.execute(text("SELECT id FROM sessions"))}


if __name__ == "__main__":
    main()
