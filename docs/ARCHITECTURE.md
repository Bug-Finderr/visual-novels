# Storyplex — Architecture (v2)

A snapshot of how the system actually works after the recent refactor. Sections
follow the lifecycle of a single playthrough: generate → cache → play → save →
continue.

---

## TL;DR

- **Story is fully pre-generated** before the player ever clicks Start.
- **Runtime is a deterministic playback** of cached content — no LLM call,
  no Mulberry call, no waiting (except free-input).
- **WebSocket-streamed TTS** with a per-character stable voice description.
- **Ren'Py-style save / load / restart** with explicit checkpointing.
- **"Continue to next chapter"** spawns a child session whose world + cast
  are inherited from the parent's chosen ending.

---

## System map

```
Browser  ─── HTTPS ───────────►  FastAPI (uvicorn)
   │       /api/sessions/...
   │       /api/sessions/{id}/choice
   │       /api/sessions/{id}/advance
   │       /api/sessions/{id}/free-input
   │       /api/sessions/{id}/saves[/...]
   │       /api/sessions/{id}/restart
   │       /api/sessions/{id}/continue
   │       /api/assets/{id}/...
   └─── WSS ──►  /api/sessions/{id}/tts/stream
                       │
                       ▼
                  Mulberry TTS WS
                  (rumik.ai)

FastAPI ────►  Gemini 2.5-Pro  (world + spine + endings catalogue)
        ────►  Gemini 2.5-Flash (beat dialogues, ending dialogues, free-input)
        ────►  Gemini 2.5-Flash-Image (sprites + scene backgrounds)
        ────►  SQLite (sessions, beats, characters, scenes, dialogue, saves)
        ────►  local FS (data/generated/<sid>/{sprites,backgrounds,audio,overlays})
```

---

## Story shape

- **10 beats** in a fixed spine — every player walks the same beats in order.
- **3 pre-baked choices per beat**, each carrying `alignmentTag` + `magnitude`.
- **5 candidate endings** — the one that fires at beat 9 is whichever
  alignment tag accumulated the most weight from the player's picks.
- The story is **linear in content, branching in destination**.

```
opening ──► beat 0 ──┬─► beat 1 ──┬─► beat 2 ──► ... ──► beat 9 ──► ending
                     │            │
                  choice         choice
                  (nudges alignment, all 3 choices route to same beat)

alignment_state at beat 9 picks 1 of 5 cached endings.
```

---

## Generation pipeline

Triggered by `POST /api/sessions/{id}/generate`. Runs in `asyncio.to_thread`
so the request returns immediately while the SSE progress stream watches.

| Phase | What runs | Wall-clock |
| --- | --- | --- |
| **A** | World build (Pro 2.5) — world + cast + 10-beat spine + 3 choices/beat + 5 endings + opening script | ~45 s |
| **B** | Character neutral sprites in parallel (1 per char, identity anchor) | ~12 s |
| **C** | 9 emotions × N chars **+** N scene backgrounds in one shared 6-worker pool | ~100 s |
| **D** | Overlays (per char, internal 4-worker pool) **\|\|** 8 beat dialogues pre-rendered with Flash 2.5 in parallel | ~50 s |
| **E** | Script binding + voice profiles + 5 endings pre-rendered | ~15 s |
| **F** | TTS pre-render of every line (opening + 10 beats + 5 endings) in 8-way pool | ~1.5–2 min |

**Total**: ~3.5–5 min from `created` to `ready`. After that, runtime is
deterministic playback.

---

## Caches written during generation

| Table | Keyed by | Holds |
| --- | --- | --- |
| `sessions` | `id` | world_lore, plot_arc, story_spine, endings catalogue, alignment_state, current_beat_index, chosen_ending_id, parent_session_id, chapter_number |
| `characters` | `(session_id, id)` | name, color, role, personality, appearance, speech_style, quirks, voice_caption, **gender**, voice_id |
| `scenes` | `(session_id, id)` | name, description, image_generated |
| `script_labels` | `(session_id, label_name)` | flat statements as JSON — for the `Start` label and runtime-generated dynamic labels |
| **`beat_expansions`** | `(session_id, beat_index)` | full per-beat statement list (10 entries per session) |
| **`ending_dialogue`** | `(session_id, ending_id)` | full epilogue statement list (5 entries per session) |
| `dialogue_history` | autoincrement | per-turn user + model messages — used by free-input only |
| `saves` | `id` | Ren'Py-style checkpoint snapshots |

Plus on-disk per session:
```
data/generated/<sid>/
    sprites/<char_id>/<expression>.png      ← 10 per char
    overlays/<char_id>/<overlay>.png        ← 3 per char (best-effort)
    backgrounds/<scene_id>.png              ← 1 per scene
    audio/<sha1>.wav                        ← 1 per unique script string
    audio/manifest.json                     ← script_string → wav filename
```

---

## Runtime — the player loop

The client is a custom lightweight VN engine (`game-bridge.js`) — Monogatari
markup compatible but no Monogatari runtime.

### Every advance / choice click

1. **Client** posts `/choice` (with `alignmentTag` + `magnitude`) or `/advance`.
2. **Server** (`dialogue_engine.process_player_action`):
   1. Apply alignment to `alignment_state[ending_id]` (choice only).
   2. Compute `target_beat_index`.
   3. Look up `beat_expansions[session, target]` → instant cache hit.
   4. `_ensure_scene_change` — prepend `scene_change` to the spine's canonical
      `sceneId` if the cached statements don't already lead with the right one.
   5. `_ensure_cast` — prepend `hide_character` for every character NOT in the
      beat's `castIds` so prior-beat sprites don't linger.
   6. Append the beat's pre-baked choices.
3. **Server** wraps in `build_runtime_label` → flat strings + Choice block.
4. **Client** plays through statements; choice click → loop again.

Latency: typically <100 ms server-side. The bottleneck is the typewriter
animation playing the statements.

### TTS playback

For each dialogue / narration line:

1. **Client** opens a WS to `/api/sessions/{sid}/tts/stream` with
   `{scriptString, text, characterId, expression}`.
2. **Server** resolves the character's voice profile (stable
   `voice_caption` + emotion delivery hint), checks the on-disk WAV.
3. **Cache hit** (the normal case after pipeline pre-render): server reads
   the WAV and streams its PCM payload back in 100 ms chunks.
4. **Cache miss**: server mints a Mulberry WS session, forwards each PCM
   frame to the browser AS IT ARRIVES, and writes the WAV to disk for
   subsequent replays.
5. **Client** decodes int16 LE @ 24 kHz mono per chunk, schedules each
   `BufferSource` at `playAt = max(now, nextStart)` so playback starts on
   the first chunk (no "wait for full audio" gap).
6. An `AnalyserNode` in the chain drives amplitude-based lip-sync on the
   speaking sprite.

### Final beat (ending)

- Server picks the ending whose `id` is the max of `alignment_state`.
- Look up `ending_dialogue[session, chosen_ending]` → instant.
- Returns `endingFired: true` + the ending's statements.
- Client plays through, then shows the **ending card** with two options:
  - **Continue to next chapter** → spawn child session
  - **Return to library**

### Free-input

The only path that still calls Gemini live. Generates a short response
(~2–4 statements, 700 tokens, `thinking_budget=0`) in ~1 s. Beat index does
NOT advance.

---

## Voice profiles

Two layers — character identity is stable, per-line delivery varies.

### Default per-character description (stable)

Set once at character creation by Gemini in `voice_caption`. Examples:

- `"A teenage girl with a clear, mid-range voice that is often sharp and
  clipped, but can soften with vulnerability."`
- `"An older man with a calm, low-pitched voice and a slow, gentle cadence."`

This is the description Mulberry sees on **every** line of that character.

### Per-line delivery delta (varies)

Driven by the dialogue's `expression` tag. Mapped to a phrase that
continues "Speak …":

| expression | delta |
| --- | --- |
| neutral | _none — base description only_ |
| happy | "Speak cheerfully and a bit quickly, with a smile in the voice." |
| sad | "Speak softly and slowly, with a downcast tone." |
| angry | "Speak sharply and with bite, faster paced." |
| scared | "Speak shakily and a little breathless, faster paced." |
| (… etc, 10 expressions) |  |

### Speaker preset + pitch

- **gender = female** → `speaker_1` preset + age-based pitch + ±1 jitter
- **gender = male / neutral** → no preset (description-driven) + downward
  pitch shift (–5 from age baseline for male, –2 for neutral)
- **narrator** → description-only, `f0_up_key=-3`

`gender` is now an explicit character field set by the world prompt
(`'female' | 'male' | 'neutral'`); legacy sessions fall back to keyword
detection over `voice_caption`.

---

## Save / Load / Restart (Ren'Py-style)

Triggered by **Esc** key or the `☰ Menu` button in the game header.

| Action | What it does |
| --- | --- |
| **Save** | Snapshots `{currentLabel, statementIndex, currentSceneId, currentBeatIndex, alignmentState, chosenEndingId, visibleCharacters[{id,expression,position}]}` to the `saves` table. Named slots optional. |
| **Load** | Restores the snapshot — rebuilds the scene, mounts each visible character, jumps the label + statementIndex, calls `executeNext()`. |
| **Restart** | Resets `current_beat_index → 0`, clears `alignment_state` + `chosen_ending_id`, drops all runtime-generated labels, deletes `dialogue_history`. **Keeps `beat_expansions` + `ending_dialogue`** so the replay is instant. |

---

## Chapter continuation

Each chapter is its own session linked to its parent.

```
ChAPTER 1  ────► chosen_ending_id = "noble_sacrifice"
                                 │
                                 │ "Continue to next chapter"
                                 ▼
ChAPTER 2  (new session)
   parent_session_id ─►  Chapter 1
   chapter_number      = 2
   world + cast        = inherited (re-emitted by Gemini with same ids)
   spine + endings     = NEW (continue from Ch1's ending state)
```

The generation pipeline reads `parent_session_id`, fetches the parent's
world + chosen ending, and calls `build_continuation_prompt` instead of
the fresh world prompt. The Pro 2.5 response is constrained to re-use
parent character ids and pick up after the previous ending's outcome.

---

## Story-mutation guards

Two server-side passes guarantee a clean stage even when the LLM's
cached output is sloppy.

### `_ensure_scene_change(statements, canonical_scene_id)`

If the first statement isn't a `scene_change` to a real `sceneId`,
prepend / overwrite with the spine's canonical one. Prevents the
"background went black after a choice" bug where the LLM hallucinated a
sceneId that didn't have a generated background image on disk.

### `_ensure_cast(statements, beat_cast_ids, all_character_ids)`

Prepend `hide_character` for every character NOT in this beat's
`castIds`. Inserted after any leading `scene_change`. Prevents previous-
beat sprites from lingering when the LLM forgets to hide them. Safe to
over-hide because `_hideCharacter` is a no-op on the client when the
sprite isn't mounted.

---

## Cleanup — what got deleted in this refactor

- `puppeteer_client.py` — old THA3 GPU-puppeteer path (replaced by the
  layered rig)
- `tts_client.py` — old Irodori Japanese TTS (replaced by Mulberry WS)
- `dialogue_system.py` — old reactive dialogue prompt (replaced by
  `beat_expansion.py` with full-beat + per-turn variants)
- the `jp` field — Japanese script lines (English only now)

---

## File-by-file index of the active code

```
server/app/
    main.py                              ─── FastAPI lifespan + router includes
    config.py                            ─── env vars (GEMINI/SILK keys, paths)
    logger.py
    db/
        database.py                      ─── schema + ALTER TABLE migrations
        queries/
            sessions.py                  ─── core session CRUD + spine/alignment
            characters.py                ─── chars with voice_caption + gender
            scenes.py
            script_labels.py
            dialogue_history.py
            beat_expansions.py           ─── beat dialogue cache (NEW)
            ending_dialogue.py           ─── ending dialogue cache (NEW)
            saves.py                     ─── Ren'Py-style saves (NEW)
    services/
        session_service.py               ─── create + create_continuation
        script_builder.py                ─── statement → flat string conversion + beat 0 choice append
        asset_manager.py                 ─── path helpers
        background_remover.py            ─── rembg
        silk_client.py                   ─── Mulberry WS — async stream + WAV facade
        tts_generator.py                 ─── voice profiles, parallel WAV synth, full-session pre-render
        animation_generator.py           ─── thin wrapper around image_generator overlays
        ai/
            gemini_client.py
            story_generator.py           ─── world/continuation Pro 2.5 call
            image_generator.py           ─── parallel sprite + scene + overlay gen
            dialogue_engine.py           ─── process_player_action + beat/ending pre-expand
            prompts/
                world_building.py        ─── world prompt + build_continuation_prompt
                beat_expansion.py        ─── per-turn + full-beat + ending prompts
                sprite_generation.py
                choice_generation.py
    routes/
        sessions.py                      ─── CRUD + /continue
        generation.py                    ─── /generate + SSE progress
        gameplay.py                      ─── /choice, /advance, /free-input, /script
        saves.py                         ─── /saves (list/get/create/delete) + /restart
        tts_stream.py                    ─── WS /tts/stream (NEW)
        assets.py
    backfill_audio.py                    ─── one-shot CLI: regen audio for an existing session
    complete_generation.py               ─── one-shot CLI: resume a crashed pipeline

client/src/
    main.js                              ─── routes + SPA boot
    utils/router.js
    services/
        api.js                           ─── tiny fetch wrapper + SSE
        animated-sprite.js               ─── 2.5D layered rig (breathing, sway, lip-sync)
        game-bridge.js                   ─── VN engine: WS audio + cache flow + save/load + pause menu
        audio-cue.js                     ─── click/hover/scene-in sfx
    views/
        landing.js                       ─── cinematic hero
        setup-wizard.js                  ─── form
        loading.js                       ─── SSE progress + literary epigraph
        sessions.js                      ─── library (with chapter badges)
        game.js                          ─── shell + pause menu hook
    styles/main.css                      ─── candlelit-amber design system
```
