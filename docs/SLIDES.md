---
marp: true
theme: gaia
class: invert
paginate: true
size: 16:9
---

<style>
section { background: #07060a; color: #f3e7cf; font-family: 'Inter', sans-serif; }
section h1, section h2 { font-family: 'Cormorant Garamond', serif; font-weight: 300; color: #ebc473; letter-spacing: 0.04em; }
section.lead h1 { font-size: 4rem; }
section blockquote { color: #c4b08a; font-style: italic; border-left-color: #d4a857; }
section a { color: #ebc473; }
code, pre { background: #14110b; border-radius: 6px; color: #f3e7cf; }
hr { border-color: rgba(212,168,87,0.25); }
table th { color: #ebc473; }
section.lead p { color: #c4b08a; font-style: italic; }
</style>

<!-- _class: lead -->

# Storyplex — v2

### Pre-generated stories, instant playback

A snapshot of the architecture refactor

---

# The problem

- The old runtime kept hitting Gemini Flash on every page advance
- 2–4 statements per LLM call → 4–6 calls per beat → 5–8 s of wait per beat
- Player kept seeing "Characters are responding…" between every page

> "User don't feel the wait and lag."

---

# The shift

|                  | Before | After |
| ---              | ---    | ---   |
| Story spine + endings | pre-gen ✓ | pre-gen ✓ |
| Per-beat dialogue | live LLM per turn | **pre-gen ✓ + cached** |
| Ending dialogue | live LLM at beat 9 | **pre-gen ✓ + cached** |
| Voice audio | streamed per line | **pre-gen ✓ + cached** |
| Per-page advance | 1–1.5 s LLM | **<100 ms DB lookup** |

Free-input is the only thing that still calls Gemini at runtime.

---

# Story shape

- **10 beats** in a fixed spine
- **3 pre-baked choices per beat** — each with `alignmentTag` + `magnitude`
- **5 candidate endings** keyed by tag
- Choices don't change beat content; they nudge `alignment_state`
- The ending with the highest score fires at beat 9

> Linear in content. Branching in destination.

---

# Spine flow

```
opening ──► beat 0 ──┬─► beat 1 ──┬─► beat 2 ──► ... ──► beat 9 ──► ending
                     │            │
                  choice        choice
              (3 options,    (3 options,
               each tagged)    each tagged)

         alignment_state at beat 9 picks 1 of 5 cached endings.
```

---

# Pipeline (parallel everywhere)

| Phase | What |  ⏱  |
| --- | --- | --- |
| A | World + spine + endings (Pro 2.5) | 45 s |
| B | Character neutrals (parallel) | 12 s |
| C | 9 emotions × N chars + N scenes (one pool) | ~100 s |
| D | Overlays \|\| 8 beat dialogues (Flash) | ~50 s |
| E | Script + voices + 5 ending dialogues | ~15 s |
| F | **TTS pre-render of every line** (8 workers) | ~1.5–2 min |

**Total**: ~3.5–5 min. After that — zero waits during play.

---

# Caches we write

| Table | What |
| --- | --- |
| `sessions` | spine, endings catalogue, alignment, chosen ending, chapter |
| `characters` | personality, voice_caption, **gender** |
| `beat_expansions` | ALL 10 beats' statements (pre-rendered) |
| `ending_dialogue` | ALL 5 endings' statements (pre-rendered) |
| `script_labels` | flat statements per label |
| `saves` | Ren'Py-style checkpoints |

Plus on-disk: sprites, backgrounds, overlays, `<sha1>.wav` audio.

---

# Runtime — per page click

```
client ──► /choice {alignmentTag, magnitude}
            │
            ▼
   process_player_action
            │
            ├── apply alignment to alignment_state[ending_id]
            ├── target_beat = beat_index + 1
            ├── LOOKUP beat_expansions  ◄─── cache hit
            ├── _ensure_scene_change(canonical sceneId)
            ├── _ensure_cast(hide non-cast chars)
            └── append beat's pre-baked choices
            ▼
   200 OK in <100 ms
```

---

# TTS — WebSocket all the way

1. Client opens WS to `/api/sessions/{sid}/tts/stream`
2. Server checks the on-disk WAV cache
3. **Cache hit**: streams PCM payload back in 100 ms chunks
4. **Cache miss**: opens upstream Mulberry WS, **forwards each PCM frame
   as it arrives**, writes WAV at the end
5. Client decodes int16 LE @ 24 kHz, schedules each `BufferSource` so
   playback starts on the first chunk

`AnalyserNode` drives amplitude-based lip-sync on the speaking sprite.

---

# Voice profiles (stable per character)

**Per-character default** — set ONCE from `voice_caption`:

> "A teenage girl with a clear, mid-range voice that is often sharp and
> clipped, but can soften with vulnerability."

**Per-line delta** — only the delivery hint changes:

| expression | appended |
| --- | --- |
| happy | "Speak cheerfully and a bit quickly, with a smile in the voice." |
| sad | "Speak softly and slowly, with a downcast tone." |
| angry | "Speak sharply and with bite, faster paced." |

Character identity is preserved across every line.

---

# Voice routing

- `gender = "female"` → speaker_1 preset + age-based pitch
- `gender = "male" / "neutral"` → description-driven, no preset, deeper pitch
- narrator → description-driven, `f0_up_key = -3`

`gender` is now an **explicit field** on every character (set by the
world prompt). Legacy sessions fall back to keyword detection over
`voice_caption`.

---

# Stage guards

The cached LLM output is sometimes sloppy. Two server-side guards:

**`_ensure_scene_change`**
- If statements don't lead with a `scene_change` to the spine's canonical
  `sceneId`, prepend/replace
- Fixes "background went black after a choice" caused by hallucinated scene ids

**`_ensure_cast`**
- Prepend `hide_character` for every char NOT in `beat.castIds`
- Inserted after the `scene_change`
- Stops prior-beat sprites from lingering when the LLM forgets to hide them

---

# Save / Load / Restart

Triggered by **Esc** or the `☰ Menu` button.

| | |
| --- | --- |
| **Save** | Snapshot `{label, statementIndex, sceneId, beat, alignment, ending, visibleChars}` to `saves` table |
| **Load** | Rebuild the scene, mount each char, jump label + index |
| **Restart** | Reset alignment + beat, drop runtime labels — **keep** beat & ending caches so replay is instant |

---

# Continue to next chapter

After an ending fires, the ending card shows **"Continue to next chapter"**.

```
Chapter 1  ────► chosen_ending_id = "noble_sacrifice"
                                  │
                                  ▼
Chapter 2  (new session)
    parent_session_id ─►  Chapter 1
    chapter_number      = 2
    world + cast        = inherited
    spine + endings     = NEW (continues from Ch1's ending)
```

The continuation prompt forces re-use of character ids and picks up
after the parent's chosen ending's outcome.

---

# UI revamp — cinematic VN

- Candlelit amber palette (gold accent on near-black)
- Cormorant Garamond display serif + Inter body
- Film grain + soft vignette overlay
- Glass-card aesthetic with gold rule dividers
- Per-view: landing, setup wizard, sessions, loading, pause menu

The dialogue box has a soft gold gradient top edge, the choice buttons
get a gold left bar on hover, and the start gate uses a gradient serif
title.

---

# Deployment — split hosting

| Layer | Host | Why |
| --- | --- | --- |
| Frontend (SPA) | **Netlify** | static, free, perfect for Vite output |
| Backend (FastAPI + WS) | **Render / Fly / Railway** | persistent disk, WS support, long-running |

Netlify Functions can't host the backend: no persistent WS, no persistent
disk, hard execution caps. So we split.

---

# What needs to change to deploy

- `client/src/services/api.js` → `VITE_API_BASE` env var
- `client/src/services/game-bridge.js` → `VITE_WS_BASE` env var
- `client/public/_redirects` → SPA fallback `/*  /index.html  200`
- `server/app/config.py` → `DATA_DIR` env var (persistent disk mount)
- `server/app/main.py` → tighten CORS to the Netlify origin
- Render service config: persistent disk → `/var/data`
- Env vars: `GEMINI_API_KEY`, `SILK_API_KEY`, `DATA_DIR`, `FRONTEND_ORIGIN`

---

# Cost back-of-envelope

| Item | Cost |
| --- | --- |
| Netlify (frontend) | $0 |
| Render Starter (backend) | $7/mo |
| Render persistent disk (1 GB) | $0.25/mo |
| Gemini API (per fresh session) | ~$0.30 |
| Mulberry TTS | per their plan |

Dev/single-user usage: well under $10/mo for hosting.

---

# What we explicitly punted on

- **Multi-user auth** — sessions currently owned by "whoever has the link"
- **Postgres migration** — SQLite is fine until traffic warrants it
- **Object store for assets** — local disk works for the first deploy
- **Mid-beat scene-change validation** — only the FIRST scene_change in a
  beat is currently guarded against hallucinated scene ids

---

<!-- _class: lead -->

# Next

- Deploy frontend to Netlify
- Deploy backend to Render with persistent disk
- Wire env vars + production CORS
- Smoke-test fresh-session → play → save → continue

Then iterate.
