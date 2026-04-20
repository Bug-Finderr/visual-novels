"""Per-line audio generation via the Irodori TTS server.

For each openingScript dialogue/narration that has a `jp` field, we synthesize a
WAV with the speaker's voiceCaption and save under
    data/generated/<sid>/audio/<hash>.wav

A `manifest.json` is also written mapping the rendered script string
(`speaker:expression text` for dialogue, or just the text for narration) to its
audio file. The frontend loads the manifest once and looks up the audio file
for each statement it about to display.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable

from app.config import config
from app.db.queries import characters as character_queries
from app.logger import logger
from app.services import tts_client


def audio_dir(session_id: str) -> Path:
    return config.GENERATED_DIR / session_id / "audio"


def audio_path(session_id: str, key: str) -> Path:
    return audio_dir(session_id) / f"{key}.wav"


def manifest_path(session_id: str) -> Path:
    return audio_dir(session_id) / "manifest.json"


def script_string_for(stmt: dict) -> str | None:
    """Mirror script_builder._convert_single for dialogue/narration."""
    t = stmt.get("type")
    if t == "narration":
        return stmt.get("text", "")
    if t == "dialogue":
        expr = stmt.get("expression") or "neutral"
        return f"{stmt['speaker']}:{expr} {stmt.get('text', '')}"
    return None


def _audio_key_for(script_string: str) -> str:
    return hashlib.sha1(script_string.encode("utf-8")).hexdigest()[:16]


def _voice_captions(session_id: str) -> dict[str, str | None]:
    chars = character_queries.get_by_session(session_id)
    return {c["id"]: c.get("voice_caption") for c in chars}


def _iter_lines(opening_script: list[dict]) -> Iterable[tuple[str, str | None, str]]:
    """Yield (script_string, speaker_id_or_None, jp_text) per line with both fields."""
    for stmt in opening_script:
        jp = (stmt.get("jp") or "").strip()
        if not jp:
            continue
        s = script_string_for(stmt)
        if not s:
            continue
        speaker = stmt.get("speaker") if stmt.get("type") == "dialogue" else None
        yield s, speaker, jp


def _load_manifest(session_id: str) -> dict[str, str]:
    p = manifest_path(session_id)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_manifest(session_id: str, manifest: dict[str, str]) -> None:
    manifest_path(session_id).write_text(json.dumps(manifest, ensure_ascii=False))


def generate_for_opening_script(
    session_id: str,
    opening_script: list[dict],
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    return _render_lines(session_id, list(_iter_lines(opening_script)), progress_cb)


def generate_for_statements(session_id: str, statements: list[dict]) -> dict[str, str]:
    """Runtime path: synthesize audio for the dialogue/narration in a single AI
    response and return ONLY the new {script_string: filename} entries that the
    frontend can merge into its in-memory manifest.
    """
    if not tts_client.is_enabled():
        return {}
    lines = list(_iter_lines(statements))
    if not lines:
        return {}
    _render_lines(session_id, lines)
    delta: dict[str, str] = {}
    for script_string, _, _ in lines:
        key = _audio_key_for(script_string)
        if audio_path(session_id, key).exists():
            delta[script_string] = f"{key}.wav"
    return delta


def _render_lines(
    session_id: str,
    lines: list[tuple[str, str | None, str]],
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    if not lines or not tts_client.is_enabled():
        return 0
    captions = _voice_captions(session_id)
    audio_dir(session_id).mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(session_id)

    written = 0
    for i, (script_string, speaker_id, jp_text) in enumerate(lines, start=1):
        caption = captions.get(speaker_id) if speaker_id else None
        key = _audio_key_for(script_string)
        out = audio_path(session_id, key)
        if not out.exists():
            try:
                wav = tts_client.synthesize(jp_text, caption=caption)
                out.write_bytes(wav)
            except Exception as err:
                logger.warning("TTS failed for line %d (%s): %s", i, jp_text[:30], err)
                if progress_cb:
                    progress_cb(i, len(lines), jp_text[:30])
                continue
        manifest[script_string] = f"{key}.wav"
        written += 1
        _save_manifest(session_id, manifest)
        if progress_cb:
            progress_cb(i, len(lines), jp_text[:30])
    return written
