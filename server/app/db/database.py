"""Postgres-backed DB access.

The query layer keeps its tiny sqlite-style surface — `with db() as conn:` then
`conn.execute(sql, params).fetchone()/.fetchall()` with '?' placeholders — via a
thin adapter over a POOLED SQLAlchemy connection. This replaces the old single
global sqlite3 connection guarded by one process-wide lock, so requests and
pipeline workers no longer serialize. Schema is owned by Alembic (see alembic/).
"""
import re
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text

from app.config import config
from app.db.base import engine
from app.logger import logger

_QMARK = re.compile(r"\?")


class _Result:
    """Wraps a SQLAlchemy result so callers keep sqlite-style .fetchone()/
    .fetchall() returning plain dicts (detached, safe to use after the block)."""

    def __init__(self, result):
        self._result = result

    def fetchone(self) -> dict | None:
        if not self._result.returns_rows:
            return None
        row = self._result.mappings().fetchone()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict]:
        if not self._result.returns_rows:
            return []
        return [dict(r) for r in self._result.mappings().fetchall()]


class _Conn:
    """Adapts a SQLAlchemy Connection to the query layer's execute() surface,
    translating sqlite '?' positional placeholders to named binds."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: tuple | list = ()) -> _Result:
        params = tuple(params or ())
        i = 0

        def _named(_m: re.Match) -> str:
            nonlocal i
            name = f":p{i}"
            i += 1
            return name

        converted = _QMARK.sub(_named, sql)
        binds = {f"p{n}": v for n, v in enumerate(params)}
        return _Result(self._conn.execute(text(converted), binds))


@contextmanager
def db() -> Iterator[_Conn]:
    """A pooled per-call connection wrapped in a transaction (commit on success,
    rollback on error)."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield _Conn(conn)
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Schema is managed by Alembic now — just verify connectivity at startup."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database ready (Postgres): %s", _sanitize(config.DATABASE_URL))


def _sanitize(url: str) -> str:
    """Strip credentials from a DB URL for logging."""
    return re.sub(r"://[^@/]+@", "://***@", url)


def row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]
