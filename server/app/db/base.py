"""SQLAlchemy engine + session (Postgres).

This is the Phase-1 persistence foundation. It is introduced ALONGSIDE the
legacy sqlite layer (app/db/database.py) so the running app is untouched while
the schema + models are established; the query layer is cut over separately.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import config

# pool_pre_ping avoids handing out a dead connection after Postgres restarts.
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, class_=Session, future=True
)

Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a per-request session, committed on success and
    rolled back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
