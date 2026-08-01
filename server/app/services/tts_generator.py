"""Per-line audio generation via the Silk / Mulberry TTS API (rumik.ai).

For each script dialogue/narration line we synthesize an English WAV (the `text`
field — what the player reads) and save it under
    data/generated/<sid>/audio/<hash>.wav

A `manifest.json` maps the rendered script string (`speaker:expression text` for
dialogue, or the text for narration) to its audio file. The frontend loads the
manifest once and looks up the file for each statement it's about to display.

Voice consistency: Silk has no reference-WAV cloning, so each character gets a
deterministic voice PROFILE (preset speaker + pitch shift + optional English
description) reused for every line. Per-line emotion is layered on via the
expression tag steering Mulberry's delivery.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from app.config import config
from app.db.queries import characters as character_queries
from app.logger import logger
from app.services import silk_client

# Mulberry rate limiting has been lifted, so per-line failure is now an
# unusual transient (network blip / one-off server error). Short retry only.
_BACKOFF_SECONDS = 3.0

# Parallel TTS synthesis. Each call is an independent WebSocket session.
_TTS_PARALLELISM = 8


def is_enabled() -> bool:
    return silk_client.is_enabled()


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


# --- voice profiles -------------------------------------------------------

# Mulberry named studio speakers (rumik.ai): 8 female, 4 male. Each character
# is assigned one deterministically by gender (same id -> same voice; distinct
# cast members -> distinct voices), and the name is passed to the Silk API.
FEMALE_SPEAKERS = ["emma", "mia", "sophia", "ava", "ira", "siya", "aisha", "zoya"]
MALE_SPEAKERS = ["lucas", "noah", "theo", "adam"]
_ALL_SPEAKERS = set(FEMALE_SPEAKERS + MALE_SPEAKERS)

# Trait grid: (gender, age[young|adult], pitch[low|high]) -> the matching voice.
#   Emma  F/young/low   Mia  F/young/high   Sophia F/adult/low   Ava  F/adult/high
#   Lucas M/young/low   Noah M/young/high   Adam   M/adult/low   Theo M/adult/high
_TRAIT_SPEAKER = {
    ("female", "young", "low"): "emma",  ("female", "young", "high"): "mia",
    ("female", "adult", "low"): "sophia", ("female", "adult", "high"): "ava",
    ("male", "young", "low"): "lucas",   ("male", "young", "high"): "noah",
    ("male", "adult", "low"): "adam",    ("male", "adult", "high"): "theo",
}
# Extra female voices, used to keep same-gender cast members distinct.
_EXTRA_FEMALE = ["ira", "siya", "zoya", "aisha"]

_HIGH_PITCH_WORDS = (
    "energetic", "lively", "bright", "excitable", "animated", "upbeat", "cheerful",
    "bubbly", "perky", "airy", "breezy", "light", "playful", "chirpy", "spirited",
    "peppy", "excited", "enthusiastic", "giddy", "vivacious", "high-pitched", "squeaky",
)
_LOW_PITCH_WORDS = (
    "calm", "grounded", "firm", "steady", "measured", "deep", "low", "serious", "stoic",
    "grave", "solemn", "gruff", "reserved", "stern", "informative", "quiet", "monotone",
    "gravelly", "husky", "weary", "somber", "subdued", "low-pitched", "soft-spoken",
)


# Explicit F0/timbre cues take precedence over energy/delivery adjectives —
# a "deep" character is low-pitched even if also described as, say, energetic.
_DEEP_WORDS = (
    "deep", "low pitched", "low-pitched", "bass", "baritone", "booming",
    "rumbling", "gravelly", "sonorous", "basso", "low, resonant", "deep and resonant",
)
_SHRILL_WORDS = ("high pitched", "high-pitched", "squeaky", "shrill", "piping", "reedy")


def _pitch_band(caption: str | None) -> str:
    c = (caption or "").lower()
    deep = any(w in c for w in _DEEP_WORDS)
    shrill = any(w in c for w in _SHRILL_WORDS)
    if deep and not shrill:
        return "low"
    if shrill and not deep:
        return "high"
    # Fall back to energy / delivery adjectives.
    if any(w in c for w in _HIGH_PITCH_WORDS):
        return "high"
    if any(w in c for w in _LOW_PITCH_WORDS):
        return "low"
    return "low"  # grounded default


def _age2(age: str) -> str:
    return "young" if age in ("young", "teen", "child") else "adult"


def _trait_speaker(gender: str, caption: str | None, age: str) -> str:
    """Single speaker matching the character's gender + age + pitch traits."""
    g = gender if gender in ("male", "female") else "female"  # neutral -> female pool
    return _TRAIT_SPEAKER[(g, _age2(age), _pitch_band(caption))]


def _assign_one(gender: str, caption: str | None, age: str, used: set) -> str:
    """Trait-matched speaker; if already used in this cast, pick a distinct
    alternate (extra female voices / other same-gender voices) before reuse."""
    primary = _trait_speaker(gender, caption, age)
    if primary not in used:
        return primary
    g = gender if gender in ("male", "female") else "female"
    pool = (_EXTRA_FEMALE + FEMALE_SPEAKERS) if g == "female" else MALE_SPEAKERS
    for alt in pool:
        if alt not in used:
            return alt
    return primary  # pool exhausted -> unavoidable reuse


# Narrator: an adult, measured male voice (Adam is described as narrator-like).
NARRATOR_PROFILE = {
    "speaker": "adam",
    "f0_up_key": -2,
    "description": "Calm middle-aged male narrator, low warm voice. American accent.",
}

# Per-line delta layered ON TOP of the character's stable default description.
# The default description (voice_caption) carries the character's identity
# (gender + age + timbre + speaking style); these hints only nudge the
# delivery — tone + pacing — for the current line. Phrased as a continuation
# of "Speak ..." so it reads naturally appended to the base description.
_EMOTION_DELIVERY = {
    "happy":       "cheerfully and a bit quickly, with a smile in the voice",
    "sad":         "softly and slowly, with a downcast tone",
    "angry":       "sharply and with bite, faster paced",
    "surprised":   "with a sudden, startled inflection",
    "neutral":     None,
    "embarrassed": "haltingly and quietly, with shy hesitation",
    "thinking":    "slowly, with thoughtful pauses",
    "scared":      "shakily and a little breathless, faster paced",
    "determined":  "firmly and steadily, with conviction",
    "smug":        "with a teasing drawl",
}

# Word-boundary gender keyword detection over the voice_caption.
_FEMALE_RX = re.compile(
    r"\b(woman|women|girl|girls|female|females|lady|ladies|"
    r"she|her|herself|feminine|"
    r"mother|mom|mum|daughter|sister|grandmother|grandma|"
    r"queen|princess|priestess|miss|mrs|madam)\b",
    re.IGNORECASE,
)
_MALE_RX = re.compile(
    r"\b(man|men|boy|boys|male|males|gentleman|gentlemen|guy|guys|"
    r"he|him|his|himself|masculine|"
    r"father|dad|son|brother|grandfather|grandpa|"
    r"king|prince|sir|mr|lord)\b",
    re.IGNORECASE,
)


def _stable_int(s: str) -> int:
    return int(hashlib.sha1(s.encode("utf-8")).hexdigest()[:8], 16)


def _is_mostly_ascii(s: str) -> bool:
    if not s:
        return False
    ascii_count = sum(1 for ch in s if ord(ch) < 128)
    return ascii_count / len(s) >= 0.8


def _detect_gender(caption: str | None) -> str:
    """Return 'female' / 'male' / 'unknown' from keyword hits in the caption."""
    if not caption:
        return "unknown"
    f = len(_FEMALE_RX.findall(caption))
    m = len(_MALE_RX.findall(caption))
    if f > m:
        return "female"
    if m > f:
        return "male"
    return "unknown"


def _detect_age_band(caption: str | None) -> str:
    """Bucket the character into a coarse age band from keyword cues."""
    if not caption:
        return "adult"
    c = caption.lower()
    # A stated numeric age (e.g. "apparent age 17", "16-year-old") wins over
    # keyword cues — anime casts skew teen and often give the number directly.
    m = re.search(r"(?:age[d]?|apparent age)\s*(\d{1,2})", c) or re.search(r"(\d{1,2})[\s-]*(?:year|yr|yo)\b", c)
    if m:
        n = int(m.group(1))
        if n < 13:
            return "child"
        if n < 20:
            return "teen"
        if n < 30:
            return "young"
        if n < 55:
            return "adult"
        return "elderly"
    if any(k in c for k in (
        "elderly", "ancient", "venerable", "wizened", "aged",
        "old man", "old woman", "older man", "older woman", "older lady",
        "older gentleman", "grandmother", "grandfather", "grandma", "grandpa",
    )):
        return "elderly"
    if "middle-aged" in c or "middle aged" in c or "in his forties" in c or "in her forties" in c:
        return "middle"
    if any(k in c for k in ("child", "kid", "little boy", "little girl", "young child")):
        return "child"
    if any(k in c for k in ("teen", "teenage", "teenager", "adolescent")):
        return "teen"
    if any(k in c for k in ("young woman", "young man", "young adult", "twenties", "20s", "in his twenties", "in her twenties")):
        return "young"
    return "adult"


_AGE_BASE = {
    "elderly": -2,
    "middle":  -1,
    "adult":    0,
    "young":   +1,
    "teen":    +2,
    "child":   +3,
}


_AGE_LABEL = {
    "elderly": "elderly",
    "middle":  "middle-aged",
    "adult":   "adult",
    "young":   "young",
    "teen":    "teenage",
    "child":   "child",
}


def _article(word: str) -> str:
    return "An" if word and word[0].lower() in "aeiou" else "A"


def _short_male_description(age: str) -> str:
    label = _AGE_LABEL.get(age, "adult")
    if age == "elderly":
        return f"An {label} man with a deep, slow voice."
    if age == "child":
        return f"A young {label} boy with a bright, light voice."
    if age == "teen":
        return f"A {label} boy with a clear mid-range voice."
    return f"{_article(label)} {label} man with a warm, resonant voice."


def _short_female_description(age: str) -> str:
    label = _AGE_LABEL.get(age, "adult")
    if age == "elderly":
        return f"An {label} woman with a soft, measured voice."
    if age == "child":
        return f"A young {label} girl with a bright, light voice."
    if age == "teen":
        return f"A {label} girl with a clear, expressive voice."
    return f"{_article(label)} {label} woman with a clear, expressive voice."


# Accent words that mean the description already commits to an accent — if any
# are present we leave it alone; otherwise we default to an American accent.
_ACCENT_WORDS = (
    "accent", "american", "british", "english", "australian", "irish", "scottish",
    "welsh", "cockney", "posh", "received pronunciation", "southern drawl",
    "new york", "brooklyn", "boston", "texan", "midwestern",
    "french", "german", "italian", "spanish", "russian", "japanese", "indian",
)


def _ensure_accent(description: str) -> str:
    """Default every voice to an American accent unless the description already
    specifies one (the story/voice_caption wins if it names a different accent)."""
    d = (description or "").strip()
    if not d:
        return "American accent."
    if any(w in d.lower() for w in _ACCENT_WORDS):
        return d
    return f"{d}{'' if d.endswith('.') else '.'} American accent."


def _default_description(caption: str | None, gender: str, age: str) -> str:
    """The character's stable, per-session default voice description.

    Prefers the AI-written `voice_caption` (set once at character creation by
    the world-building prompt) because it captures personality + speaking
    style. Falls back to a templated one-sentence description only for
    legacy sessions whose caption is missing or non-English.
    """
    cap = (caption or "").strip()
    if cap and _is_mostly_ascii(cap):
        # Truncate runaway captions so the per-line description doesn't
        # balloon — Mulberry steers fine on a sentence; multi-paragraph
        # captions just dilute the signal.
        return _ensure_accent(cap[:240])
    return _ensure_accent(
        _short_female_description(age) if gender == "female"
        else _short_male_description(age)
    )


def _character_profile(
    character_id: str,
    caption: str | None,
    gender: str | None = None,
    speaker: str | None = None,
) -> dict:
    """Voice profile, deterministic per character_id, gender + age aware.

    The `description` here is the character's STABLE DEFAULT — set once,
    reused on every line. Per-line emotion/pacing is layered on top by
    `_compose_description` when the line is synthesized; we never change
    the character's underlying voice prompt mid-session.

    - A named speaker is chosen by gender (male -> 4 male voices; female /
      neutral -> 8 female voices), deterministic per character_id so the same
      character always sounds the same and distinct cast members differ.
    - Pitch (f0_up_key) adds age variety + a small per-character jitter on top.
    - The description defaults to an American accent (see `_ensure_accent`).
    """
    g = (gender or "").lower().strip()
    if g not in {"female", "male", "neutral"}:
        g = _detect_gender(caption)

    age = _detect_age_band(caption)
    base = _AGE_BASE[age]
    h = _stable_int(character_id)
    jitter = ((h >> 4) % 3) - 1   # -1..+1
    pitch = max(-12, min(12, base + jitter))
    chosen = speaker if speaker in _ALL_SPEAKERS else _trait_speaker(g, caption, age)
    return {
        "speaker": chosen,
        "f0_up_key": pitch,
        "description": _default_description(caption, g, age),
    }


def _compose_description(base: str | None, expression: str | None) -> str | None:
    """Per-line description = character default + emotion / pacing delta.

    `base` is the character's stable voice_caption (set once at creation).
    `expression` selects the delivery delta (tone + pacing) for the current
    line — that is the ONLY thing that varies between two lines of the same
    character. Neutral lines omit the delta entirely.
    """
    delivery = _EMOTION_DELIVERY.get(expression or "neutral")
    if not base and not delivery:
        return None
    if not delivery:
        return base
    if not base:
        return f"Speak {delivery}."
    # Tidy join — strip a trailing period from base so the appended sentence
    # reads cleanly: "<voice_caption>. Speak <delta>."
    base_clean = base.rstrip(". ").strip()
    return f"{base_clean}. Speak {delivery}."


def ensure_all_character_voices(
    session_id: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    """Assign each character a SINGLE named speaker from its traits (gender +
    age + pitch), kept distinct within the cast where the 12-voice pool allows,
    and persist the speaker name on the character (voice_id). Runtime + pre-gen
    both read it back so the character always sounds the same."""
    if not is_enabled():
        return 0
    chars = character_queries.get_by_session(session_id)
    used: set = set()
    done = 0
    for i, c in enumerate(chars, start=1):
        gender = (c.get("gender") or "").lower().strip()
        if gender not in ("male", "female", "neutral"):
            gender = _detect_gender(c.get("voice_caption"))
        age = _detect_age_band(c.get("voice_caption"))
        speaker = _assign_one(gender, c.get("voice_caption"), age, used)
        used.add(speaker)
        try:
            character_queries.set_voice_id(session_id, c["id"], speaker)
            done += 1
        except Exception as err:
            logger.warning("speaker assign failed for %s: %s", c["id"], err)
        if progress_cb:
            progress_cb(i, len(chars), c["name"])
    return done


# --- synthesis ------------------------------------------------------------

def _voice_meta(session_id: str) -> dict[str, dict]:
    """Map character_id -> {'caption', 'gender'} for runtime profile lookups."""
    chars = character_queries.get_by_session(session_id)
    return {
        c["id"]: {
            "caption": c.get("voice_caption"),
            "gender": c.get("gender"),
            "speaker": c.get("voice_id"),
        }
        for c in chars
    }


_SKIPPED_TEXTS = {
    "__choice_target_placeholder__",
    "waiting for ai to continue the story...",
}


def _iter_lines(script: list[dict]) -> Iterable[tuple[str, str | None, str, str | None]]:
    """Yield (script_string, speaker_id_or_None, english_text, expression) per line.

    Filters out script_builder's choice-target placeholders so we never burn
    Mulberry calls voicing the never-played `__choice_target_placeholder__`
    label body (or its legacy text equivalent in old sessions).
    """
    for stmt in script:
        text = (stmt.get("text") or "").strip()
        if not text:
            continue
        if text.lower() in _SKIPPED_TEXTS:
            continue
        s = script_string_for(stmt)
        if not s:
            continue
        is_dialogue = stmt.get("type") == "dialogue"
        speaker = stmt.get("speaker") if is_dialogue else None
        expression = stmt.get("expression") if is_dialogue else None
        yield s, speaker, text, expression


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


def generate_for_all_session_lines(
    session_id: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    """Pre-render audio for EVERY pre-generated line in the session.

    Reads the opening (Start label statements), every cached beat expansion,
    and every cached ending dialogue, then runs them through `_render_lines`
    which dedupes by sha1 of the script string. Idempotent — already-cached
    WAVs are skipped.
    """
    from app.db.queries import beat_expansions as beat_expansions_queries
    from app.db.queries import ending_dialogue as ending_dialogue_queries
    from app.db.database import db
    from app.backfill_audio import _parse_script_string

    all_statements: list[dict] = []
    seen_keys: set[str] = set()

    def _add(stmt: dict) -> None:
        text = (stmt.get("text") or "").strip()
        if not text:
            return
        key = f"{stmt.get('type','')}:{stmt.get('speaker','')}:{stmt.get('expression','')}:{text}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        all_statements.append(stmt)

    # 1) Opening script — stored as flat strings in the Start label; reverse-parse
    #    back to dicts so _iter_lines understands them.
    with db() as conn:
        row = conn.execute(
            "SELECT statements FROM script_labels WHERE session_id = ? AND label_name = 'Start'",
            (session_id,),
        ).fetchone()
        beat_rows = conn.execute(
            "SELECT statements FROM beat_expansions WHERE session_id = ? ORDER BY beat_index",
            (session_id,),
        ).fetchall()
        ending_rows = conn.execute(
            "SELECT statements FROM ending_dialogue WHERE session_id = ?",
            (session_id,),
        ).fetchall()

    if row:
        try:
            opening_flat = json.loads(row["statements"])
            for s in opening_flat:
                parsed = _parse_script_string(s)
                if parsed:
                    _add(parsed)
        except Exception:
            pass

    # 2) All cached beat expansions
    for br in beat_rows:
        try:
            for stmt in json.loads(br["statements"]):
                _add(stmt)
        except Exception:
            continue

    # 3) All cached endings
    for er in ending_rows:
        try:
            for stmt in json.loads(er["statements"]):
                _add(stmt)
        except Exception:
            continue

    return _render_lines(session_id, list(_iter_lines(all_statements)), progress_cb)


def generate_for_statements(session_id: str, statements: list[dict]) -> dict[str, str]:
    """Runtime path: synthesize audio for one AI response and return ONLY the new
    {script_string: filename} entries for the frontend to merge into its manifest.
    """
    if not is_enabled():
        return {}
    lines = list(_iter_lines(statements))
    if not lines:
        return {}
    _render_lines(session_id, lines)
    delta: dict[str, str] = {}
    for script_string, _, _, _ in lines:
        key = _audio_key_for(script_string)
        if audio_path(session_id, key).exists():
            delta[script_string] = f"{key}.wav"
    return delta


def _render_lines(
    session_id: str,
    lines: list[tuple[str, str | None, str, str | None]],
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    """Parallel synthesis — each line runs an independent WS session.

    Mulberry's rate-limit was removed, so we can run multiple synth calls
    concurrently without backing off. WAV files are unique by sha1 hash so
    there's no write conflict; the manifest dict is guarded by a lock and
    written to disk once at the end (writing per-line under contention was
    only safe before because the loop was serial).
    """
    if not lines or not is_enabled():
        return 0
    meta = _voice_meta(session_id)
    audio_dir(session_id).mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(session_id)
    manifest_lock = threading.Lock()
    progress_lock = threading.Lock()
    progress_state = {"n": 0}
    total = len(lines)

    def _render_one(idx_line: tuple[int, tuple[str, str | None, str, str | None]]) -> bool:
        i, (script_string, speaker_id, text, expression) = idx_line
        if speaker_id:
            m = meta.get(speaker_id) or {}
            profile = _character_profile(speaker_id, m.get("caption"), gender=m.get("gender"), speaker=m.get("speaker"))
        else:
            profile = NARRATOR_PROFILE

        key = _audio_key_for(script_string)
        out = audio_path(session_id, key)
        wrote = False
        if not out.exists():
            wav = _synthesize_with_retry(text, profile, expression, line_no=i)
            if wav is not None:
                out.write_bytes(wav)
                wrote = True
        else:
            wrote = True  # already on disk counts as success

        if wrote:
            with manifest_lock:
                manifest[script_string] = f"{key}.wav"

        if progress_cb:
            with progress_lock:
                progress_state["n"] += 1
                progress_cb(progress_state["n"], total, text[:30])
        return wrote

    written = 0
    with ThreadPoolExecutor(max_workers=_TTS_PARALLELISM) as pool:
        futures = [pool.submit(_render_one, idx_line)
                   for idx_line in enumerate(lines, start=1)]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    written += 1
            except Exception as exc:
                logger.warning("tts render task crashed: %s", exc)

    # Single final manifest write — minimizes disk I/O and avoids races.
    _save_manifest(session_id, manifest)
    return written


def _synthesize_with_retry(
    text: str,
    profile: dict,
    expression: str | None,
    *,
    line_no: int,
) -> bytes | None:
    """One synth attempt + one retry after a SHORT backoff. With Mulberry's
    rate limit removed, failures are now transient (network blip / one-off
    server hiccup) — a 3 s pause is plenty before retry.
    """
    for attempt in (1, 2):
        try:
            return silk_client.synthesize(
                text,
                description=_compose_description(profile.get("description"), expression),
                speaker=profile.get("speaker"),
                f0_up_key=profile.get("f0_up_key", 0),
            )
        except Exception as err:
            if attempt == 1:
                logger.warning(
                    "Silk TTS failed for line %d (%s) — retrying in %.0fs: %s",
                    line_no, text[:30], _BACKOFF_SECONDS, err,
                )
                time.sleep(_BACKOFF_SECONDS)
            else:
                logger.warning(
                    "Silk TTS failed for line %d (%s) after retry: %s",
                    line_no, text[:30], err,
                )
    return None
