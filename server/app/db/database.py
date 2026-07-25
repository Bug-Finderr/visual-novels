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

-- Pre-generated full-beat expansions so runtime page-advances hit the cache
-- instead of an LLM call. Three variants per beat keyed by the alignmentTag
-- of the choice the player took in the *previous* beat — so each choice
-- produces a genuinely different next-beat. Empty string '' is the default
-- variant (used for /advance fallback + cache-miss recovery).
CREATE TABLE IF NOT EXISTS beat_expansions (
  session_id          TEXT NOT NULL,
  beat_index          INTEGER NOT NULL,
  source_choice_tag   TEXT NOT NULL DEFAULT '',
  statements          TEXT NOT NULL,
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, beat_index, source_choice_tag),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Pre-generated dialogue for each candidate ending. Keyed by ending_id so the
-- runtime can look up whichever ending the alignment score lands on, with no
-- live LLM call needed at the final beat.
CREATE TABLE IF NOT EXISTS ending_dialogue (
  session_id   TEXT NOT NULL,
  ending_id    TEXT NOT NULL,
  statements   TEXT NOT NULL,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, ending_id),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saves (
  id                  TEXT PRIMARY KEY,
  session_id          TEXT NOT NULL,
  slot                INTEGER,
  name                TEXT,
  current_label       TEXT NOT NULL,
  statement_index     INTEGER DEFAULT 0,
  current_scene_id    TEXT,
  current_beat_index  INTEGER DEFAULT 0,
  alignment_state     TEXT,
  chosen_ending_id    TEXT,
  visible_characters  TEXT,
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_saves_session ON saves(session_id, created_at DESC);

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
    char_cols = {row[1] for row in conn.execute("PRAGMA table_info(characters)").fetchall()}
    if "voice_caption" not in char_cols:
        conn.execute("ALTER TABLE characters ADD COLUMN voice_caption TEXT")
    if "voice_id" not in char_cols:
        conn.execute("ALTER TABLE characters ADD COLUMN voice_id TEXT")
    if "gender" not in char_cols:
        # Explicit gender — drives the TTS voice profile directly so we don't
        # have to keyword-scan voice_caption. Values: 'female', 'male', or
        # 'neutral' (non-binary / animal / unknown).
        conn.execute("ALTER TABLE characters ADD COLUMN gender TEXT")

    sess_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    # Spine model: pre-generated 10-beat story arc + 5 candidate endings.
    # alignment_state tracks {ending_id: weight} updated as the player chooses;
    # current_beat_index advances each time the AI marks a beat complete.
    if "story_spine" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN story_spine TEXT")
    if "endings" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN endings TEXT")
    if "alignment_state" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN alignment_state TEXT DEFAULT '{}'")
    if "current_beat_index" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN current_beat_index INTEGER DEFAULT 0")
    if "chosen_ending_id" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN chosen_ending_id TEXT")
    # Chapter continuation — a child session links back to the parent it
    # continues from, and chapter_number is the 1-based position in the
    # sequence. Standalone sessions have parent_session_id NULL + chapter 1.
    if "parent_session_id" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN parent_session_id TEXT")
    if "chapter_number" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN chapter_number INTEGER DEFAULT 1")

    # Which generation engine actually produced this session's story
    # ('monolith' | 'graph'). Recorded at generation time so runtime free-input
    # routing stays consistent even if the STORYGEN_ENGINE flag is later flipped.
    if "storygen_engine" not in sess_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN storygen_engine TEXT DEFAULT 'monolith'")

    # Branching beat cache — if an older session has the single-variant
    # schema (no source_choice_tag column), drop the cache table so the
    # CREATE TABLE IF NOT EXISTS above rebuilds it with the new PK shape.
    # The cached beats are regenerable by the pipeline so this is safe.
    be_cols = {row[1] for row in conn.execute("PRAGMA table_info(beat_expansions)").fetchall()}
    if be_cols and "source_choice_tag" not in be_cols:
        logger.info("Migrating beat_expansions to per-choice variants (dropping single-variant cache)")
        conn.execute("DROP TABLE beat_expansions")
        # Recreate immediately so the rest of the connection lifecycle sees it.
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS beat_expansions (
              session_id          TEXT NOT NULL,
              beat_index          INTEGER NOT NULL,
              source_choice_tag   TEXT NOT NULL DEFAULT '',
              statements          TEXT NOT NULL,
              created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (session_id, beat_index, source_choice_tag),
              FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
        """)


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
