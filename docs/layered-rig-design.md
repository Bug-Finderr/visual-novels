# Layered-Sprite 2.5D Character Rig — Design

**Status:** Implemented (v1) · **Date:** 2026-05-26 · **Supersedes:** THA3 puppeteer animation path

## Implementation note (as-built v1)

The shipped v1 takes a pragmatic, cost-controlled cut of the full design below.
Rather than decomposing each character into body/head/hair layers (flaky + costly
to extract reliably from Gemini), v1 keeps the **10 expressive emotion bases** and
adds **3 transparent facial overlays generated once per character** from the
neutral sprite — `eyes_closed`, `mouth_half`, `mouth_open` — composited by the
browser over *any* emotion base. On top, a `requestAnimationFrame` rig drives
continuous **breathing + head sway + per-emotion tilt**, overlay-based **blink**,
and **lip-sync** (audio-amplitude via WebAudio analyser, procedural fallback).
THA3 / the GPU puppeteer is fully removed. Overlays are alpha-sanity-checked
server-side and the rig degrades to motion-only if they're missing.

The full body/head/hair part decomposition + pixi.js mesh warp (below) remains
**Phase 2 / future** for true parallax head-turn and hair physics.

---


## 1. Motivation

We want **better, more lifelike character animation** than the current THA3 approach,
while keeping the generation pipeline **fully automated** (Gemini → assets → playable
game, no human in the loop).

We evaluated adopting [AIRI](https://airi.moeru.ai) and its Live2D rendering. Conclusion:

- AIRI renders **rigged** characters — Live2D (`.moc3` + `.model3.json`) or VRM (`.vrm`).
- The Live2D runtime model (`.moc3`) can **only** be authored in **Live2D Cubism Editor**,
  a closed proprietary GUI app. There is **no API/SDK/CLI** to emit `.moc3` from an image,
  and **no reliable auto-rigger** from a flat PNG.
- Therefore an automated flat-PNG → Live2D pipeline is **impossible**. This is almost
  certainly why the project originally chose THA3 (the only tech that animates a flat AI
  portrait with no rigging step).

**Decision:** Build a Live2D-*like* result we *can* automate — generate the character as
**separable layers** and drive a **browser-side 2.5D rig** that warps/swaps those layers.
This removes the runtime GPU (THA3) dependency entirely; animation becomes client-side,
continuous, and free.

We borrow **concepts** from AIRI/Live2D, and the **pixi.js** renderer family
(`pixi-live2d-display`, AIRI's Live2D path, is a pixi plugin) — but not AIRI's Vue +
Live2D-loader code, which would fight our vanilla-JS stack.

## 2. Asset contract

Per character, every layer is a transparent PNG on a **shared, pixel-aligned canvas**
(identical dimensions) so the layers stack perfectly.

| Layer file | Contents | Animated by |
|---|---|---|
| `body.png` | torso, arms, legs, neck (no facial features) | breathing scale, slight sway |
| `head.png` | face base — skin, nose, ears (no eyes/brows/mouth) | head bob + tilt (parent of parts below) |
| `hair_back.png` | hair behind the head | parallax sway |
| `hair_front.png` | bangs / front hair | parallax sway |
| `eyes_open.png` | both eyes open | swapped with closed for blink |
| `eyes_closed.png` | both eyes shut | blink frame |
| `brows.png` | eyebrows | translate up/down per emotion |
| `mouth_closed.png` | viseme: closed | lip-sync |
| `mouth_half.png` | viseme: mid-open | lip-sync |
| `mouth_open.png` | viseme: open "aa" | lip-sync |

### `rig.json` (per character)

```jsonc
{
  "canvas": { "w": 768, "h": 1024 },
  "layers": [            // z-order, back to front
    "hair_back", "body", "head", "brows", "eyes_open", "mouth_closed", "hair_front"
  ],
  "pivots": {            // normalized 0..1 anchor points
    "head":  { "x": 0.50, "y": 0.22 },
    "brows": { "x": 0.50, "y": 0.30 },
    "body":  { "x": 0.50, "y": 0.95 }
  },
  "emotions": {          // emotion = a POSE of the rig, not a separate render
    "neutral":    { "brow_dy": 0.00, "eye_squint": 0.0, "mouth": "closed", "blush": 0.0, "head_tilt": 0 },
    "happy":      { "brow_dy": -0.01, "eye_squint": 0.2, "mouth": "half",   "blush": 0.0, "head_tilt": 2 },
    "embarrassed":{ "brow_dy": 0.01,  "eye_squint": 0.1, "mouth": "closed", "blush": 0.8, "head_tilt": -3 }
    // ... remaining emotions
  }
}
```

Emotions become **rig poses** (brow/eye/mouth/blush/tilt parameters) rather than 10
separate full-body renders.

### Layer registration (the riskiest step)

Reliable approach:
1. Generate the full **neutral** sprite first (as today) — this is the ground-truth
   coordinate frame.
2. For each layer, issue a **reference-guided edit** to Gemini 2.5 Flash Image:
   *"Output ONLY the eyes from the reference image, everything else fully transparent,
   identical size and position."*
3. Post-process each layer: `remove_sprite_bg`, alpha-bbox sanity check against expected
   region; reject + retry on large drift.

If extraction quality is low for a character, fall back to a **single-flat-sprite rig**
(no blink/lip-sync) so generation never hard-fails.

## 3. Backend changes

| File | Change |
|---|---|
| `services/ai/prompts/sprite_generation.py` | Add `build_layer_extraction_prompt(character, layer, neutral_ref)`; add `EMOTION_RIG_PRESETS`. |
| `services/ai/image_generator.py` | Add `generate_character_layers(...)`: neutral → per-layer extraction → write `rig.json`. Keep `generate_character_sprites` behind a flag during migration. |
| `services/animation_generator.py` | Retired for the layered path (THA3 no longer needed); gated behind the legacy flag. |
| `routes/generation.py` (`_run_pipeline`, ~L48–89) | Branch on `RIG_MODE`: layered path emits layers + `rig.json` and **skips the THA3 block**; adjust progress weighting. |
| `services/asset_manager.py` + `routes/assets.py` | `save_character_layer(...)`; serve `rig.json` and `/characters/{id}/layers/*.png`. |
| `db/queries/characters.py`, `db/database.py` | Add `rig_ready` flag (mirrors `sprites_generated`); optional `rig_manifest` column. |
| `routes/gameplay.py` | Runtime new-character generation calls the layered generator too. |

## 4. Frontend changes

**Renderer — phased:**

- **Phase 1 — DOM/CSS rig (low risk).** `animated-sprite.js` already stacks `<img>` layers.
  Extend it: mount all rig layers; drive head bob + tilt + breathing via CSS `transform`;
  hair sway via skew; blink via eyes open/closed swap; lip-sync via mouth-viseme swap;
  emotion via `rig.json` preset (brow translate, blush opacity). Removes THA3 dependency,
  noticeably more life.
- **Phase 2 — pixi.js mesh warp (Live2D-grade).** Replace the DOM renderer with a pixi
  `MeshPlane` per layer for smooth squash/stretch breathing, parallax head turn, and
  jaw-warp lip-sync.

| File | Change |
|---|---|
| `services/character-rig.js` *(new)* | Loads `rig.json`, owns layer stack + `requestAnimationFrame` loop. Exposes the **same API** `setExpression`/`setSpeaker`/`setTalking`/`setPosition` so `game-bridge.js` (L293–403) needs **no changes**. |
| `services/animated-sprite.js` | Becomes the Phase-1 rig implementation, or is replaced by `character-rig.js`. |
| `services/live-puppeteer.js` | **Delete** once rig path is default. |
| `setTalking` | Drive visemes from the TTS audio via WebAudio amplitude (real lip-sync) instead of a fixed mouth cycle. |

**On AIRI:** borrow concepts, not code. pixi.js (its renderer) is the reusable piece;
`@proj-airi/stage-ui` is Vue + Live2D-loader-coupled and would fight our stack.

## 5. Removed
THA3 puppeteer: server `puppeteer_client` + `animation_generator`; client
`live-puppeteer.js`; the `STORYPLEX_LIVE` WS path; the H100 GPU dependency for animation.
(TTS stays on its own service.)

## 6. Risks / open questions

- **Layer registration accuracy** — make-or-break. Gemini extraction may drift or
  hallucinate. Mitigate: extract on neutral only; alpha-bbox alignment; single-flat-sprite
  fallback rig.
- **Art-style coverage** — clean for `anime`/`cartoon`; `realistic` seams may show; may
  need style-conditional rig params.
- **Hair/occlusion** — front hair over brows/eyes needs correct z-order in `rig.json`.
- **Cost** — ~6–8 image calls/char (neutral + layers) vs 10 today: roughly neutral.

## 7. Suggested sequencing

1. **Prototype frontend rig** against hand-made test layers — prove the animation *feels*
   good before backend work.
2. **Prototype layer extraction** on one real character — validate registration (riskiest).
3. **Full pipeline integration** behind `RIG_MODE`, with legacy THA3 path still available
   until the rig path is proven, then remove.
</content>
</invoke>
