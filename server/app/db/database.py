import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from app.config import config
from app.logger import logger
from app.utils.file_utils import ensure_dir

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id                          TEXT PRIMARY KEY,
  title                       TEXT NOT NULL,
  status                      TEXT NOT NULL DEFAULT 'created',
  setup_genre                 TEXT NOT NULL,
  setup_art_style             TEXT NOT NULL,
  setup_setting               TEXT NOT NULL,
  setup_protagonist_name      TEXT NOT NULL,
  setup_protagonist_personality TEXT NOT NULL,
  setup_tone                  TEXT NOT NULL,
  setup_premise               TEXT,
  world_lore                  TEXT,
  plot_arc                    TEXT,
  current_scene_id            TEXT,
  current_label               TEXT DEFAULT 'Start',
  created_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_played_at              DATETIME
);

CREATE TABLE IF NOT EXISTS characters (
  id                TEXT NOT NULL,
  session_id        TEXT NOT NULL,
  name              TEXT NOT NULL,
  color             TEXT NOT NULL DEFAULT '#FFFFFF',
  role              TEXT,
  personality       TEXT,
  appearance        TEXT,
  backstory         TEXT,
  relationship      TEXT,
  speech_style      TEXT,
  quirks            TEXT,
  sprites_generated INTEGER DEFAULT 0,
  is_dynamic        INTEGER DEFAULT 0,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id, session_id),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenes (
  id                TEXT NOT NULL,
  session_id        TEXT NOT NULL,
  name              TEXT NOT NULL,
  description       TEXT,
  narrative_context TEXT,
  image_generated   INTEGER DEFAULT 0,
  is_dynamic        INTEGER DEFAULT 0,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id, session_id),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS script_labels (
  session_id  TEXT NOT NULL,
  label_name  TEXT NOT NULL,
  statements  TEXT NOT NULL,
  sort_order  INTEGER DEFAULT 0,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, label_name),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dialogue_history (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL,
  role          TEXT NOT NULL,
  content       TEXT NOT NULL,
  label_context TEXT,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dialogue_history_session
  ON dialogue_history(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_characters_session
  ON characters(session_id);
CREATE INDEX IF NOT EXISTS idx_scenes_session
  ON scenes(session_id);
CREATE INDEX IF NOT EXISTS idx_script_labels_session
  ON script_labels(session_id);
"""


def init_database() -> None:
    global _conn
    ensure_dir(config.DB_PATH.parent)
    _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA foreign_keys = ON")
    _conn.executescript(_SCHEMA)
    _migrate(_conn)
    _conn.commit()
    logger.info("Database initialized at %s", config.DB_PATH)


def _migrate(conn: sqlite3.Connection) -> None:
    """Defensive ALTER TABLE for columns added after the initial schema."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(characters)").fetchall()}
    if "voice_caption" not in cols:
        conn.execute("ALTER TABLE characters ADD COLUMN voice_caption TEXT")


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    if _conn is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    with _lock:
        try:
            yield _conn
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
