"""Backfill TTS audio for an existing session whose initial TTS pass failed.

Walks every saved script label, reverse-parses the flat script strings back
into statement dicts, and feeds them to tts_generator (which streams via the
Mulberry WS, writes the WAV to disk, and updates manifest.json). Lines whose
WAV is already on disk are skipped — safe to re-run.

Usage:
    python -m app.backfill_audio <session_id>
    python -m app.backfill_audio --all                # every 'ready' session
                                                       # whose manifest is missing
                                                       # or empty
"""
from __future__ import annotations

import json
import re
import sys

from app.db.database import db, init_database
from app.logger import logger
from app.services import tts_generator


_DIALOGUE_RE = re.compile(r"^(\w+):(\w+)\s+(.+)$")
_CMD_PREFIXES = ("show ", "hide ", "jump ")
_SKIPPED_TEXTS = {
    "__choice_target_placeholder__",
    "waiting for ai to continue the story...",
}


def _parse_script_string(s) -> dict | None:
    """Reverse of script_builder._convert_single — flat string back to dict.
    Returns None for VN commands (show/hide/jump), choice objects (dicts),
    and the choice-target placeholder sentinel (which is never voiced).
    """
    if not isinstance(s, str):
        return None
    if s.startswith(_CMD_PREFIXES):
        return None
    if s.strip().lower() in _SKIPPED_TEXTS:
        return None
    m = _DIALOGUE_RE.match(s)
    if m:
        return {"type": "dialogue", "speaker": m.group(1),
                "expression": m.group(2), "text": m.group(3)}
    return {"type": "narration", "text": s}


def _statements_for_session(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT statements FROM script_labels WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            arr = json.loads(row["statements"])
        except Exception:
            continue
        for s in arr:
            stmt = _parse_script_string(s)
            if stmt and (stmt.get("text") or "").strip():
                out.append(stmt)
    return out


def _incomplete_sessions() -> list[str]:
    """Sessions in 'ready' state where the audio manifest is missing or empty."""
    with db() as conn:
        rows = conn.execute("SELECT id FROM sessions WHERE status = 'ready'").fetchall()
    targets: list[str] = []
    for row in rows:
        sid = row["id"]
        manifest = tts_generator.manifest_path(sid)
        if not manifest.is_file() or manifest.stat().st_size < 10:
            targets.append(sid)
    return targets


def backfill(session_id: str) -> int:
    statements = _statements_for_session(session_id)
    if not statements:
        logger.info("session %s: no TTS-applicable lines", session_id)
        return 0

    logger.info("session %s: %d lines to consider (cached ones skipped)",
                session_id, len(statements))

    # Pre-assign voice profiles for any character missing one (the original
    # run failed before the ensure_all step could persist them in some cases).
    tts_generator.ensure_all_character_voices(session_id)

    def cb(i: int, total: int, preview: str) -> None:
        logger.info("[%d/%d] %s", i, total, preview)

    return tts_generator.generate_for_opening_script(
        session_id, statements, progress_cb=cb,
    )


def main() -> None:
    init_database()
    if not tts_generator.is_enabled():
        logger.error("SILK_API_KEY not configured — cannot backfill")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("usage: python -m app.backfill_audio <session_id> | --all")
        sys.exit(1)

    if args[0] == "--all":
        targets = _incomplete_sessions()
        logger.info("found %d sessions needing audio backfill", len(targets))
    else:
        targets = args

    total_written = 0
    for sid in targets:
        try:
            n = backfill(sid)
            total_written += n
            logger.info("session %s: wrote %d new audio files", sid, n)
        except Exception as exc:
            logger.exception("session %s failed: %s", sid, exc)

    logger.info("DONE — wrote %d files across %d session(s)", total_written, len(targets))


if __name__ == "__main__":
    main()
