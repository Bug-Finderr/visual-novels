import { assetUrl } from '../lib/assets.js';

/**
 * AnimatedSprite — a layered 2.5D character rig (Live2D-like, GPU-free).
 *
 * A single emotion base sprite (full body, from Gemini) is composited with up
 * to three character-level TRANSPARENT overlays — closed eyes, half-open mouth,
 * open mouth — to produce blink and lip-sync over ANY emotion. On top of that,
 * a requestAnimationFrame loop drives continuous idle motion (breathing + head
 * sway + a per-emotion head tilt), so the character feels alive even when idle.
 *
 * Mouth motion is driven procedurally by default, but `setMouthOpen(level)`
 * lets the game bridge drive real audio-amplitude lip-sync while a voice plays.
 *
 * Graceful fallback: if the overlays didn't generate (or aren't transparent),
 * the rig runs motion-only — blink/lip-sync simply disable, base still shows.
 *
 * DOM structure:
 *   <div class="character-sprite position-X anim-enabled">
 *     <div class="anim-stack">
 *       <img class="anim-frame anim-base is-visible" src=".../neutral.png">
 *       <img class="anim-frame ov-eyes"        src=".../overlay_eyes_closed.png">
 *       <img class="anim-frame ov-mouth-half"  src=".../overlay_mouth_half.png">
 *       <img class="anim-frame ov-mouth-open"  src=".../overlay_mouth_open.png">
 *     </div>
 *   </div>
 */

const BLINK_MIN_MS = 2600;
const BLINK_MAX_MS = 6200;
const BLINK_HOLD_MS = 115;

// Procedural mouth envelope (used when no external audio level is supplied).
const MOUTH_TICK_MS = 95;

// Per-emotion resting head tilt (degrees) — small, layered onto idle sway.
const EMOTION_TILT = {
  neutral: 0, happy: 2, sad: -2, angry: -1, surprised: 0,
  embarrassed: -3, thinking: 3, scared: -1, determined: 1, smug: 4,
};

function assetVersionQuery() {
  const v = window.STORYPLEX_ASSET_VERSION || '';
  return v ? `?v=${encodeURIComponent(v)}` : '';
}

function baseUrl(sessionId, characterId, expression) {
  return assetUrl(`${sessionId}/characters/${characterId}/${expression}.png`) + assetVersionQuery();
}

function overlayUrl(sessionId, characterId, overlay) {
  return assetUrl(`${sessionId}/characters/${characterId}/overlay_${overlay}.png`) + assetVersionQuery();
}

function preload(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

export class AnimatedSprite {
  constructor({ sessionId, characterId, name, color, position }) {
    this.sessionId = sessionId;
    this.characterId = characterId;
    this.name = name;
    this.color = color || '#fff';
    this.position = position || 'center';

    this.expression = 'neutral';
    this.isSpeaker = false;
    this.isTalking = false;

    this.root = null;
    this.stack = null;
    this._base = null;
    this._ov = {};            // { eyes, mouth_half, mouth_open } -> <img>
    this._hasEyes = false;
    this._hasMouth = false;

    this._loadedExpr = new Set();
    this._blinkTimer = null;
    this._mouthTimer = null;
    this._isBlinking = false;

    // Mouth level (0..1). External audio drive overrides procedural when fresh.
    this._mouthLevel = 0;
    this._extMouthAt = 0;

    // Idle-motion clock.
    this._raf = null;
    this._t0 = performance.now();
    this._alive = true;
    // Per-instance phase offset so multiple characters don't breathe in sync.
    this._phase = Math.random() * Math.PI * 2;
  }

  mount(parent) {
    this.root = document.createElement('div');
    this.root.className = `character-sprite position-${this.position} anim-enabled fade-in`;
    this.root.dataset.charId = this.characterId;
    this.root.dataset.position = this.position;

    this.stack = document.createElement('div');
    this.stack.className = 'anim-stack';
    this.root.appendChild(this.stack);

    this._base = document.createElement('img');
    this._base.className = 'anim-frame anim-base is-visible';
    this._base.alt = this.name;
    this._base.draggable = false;
    this.stack.appendChild(this._base);

    for (const [key, cls] of [['eyes', 'ov-eyes'], ['mouth_half', 'ov-mouth-half'], ['mouth_open', 'ov-mouth-open']]) {
      const img = document.createElement('img');
      img.className = `anim-frame ${cls}`;
      img.draggable = false;
      this._ov[key] = img;
      this.stack.appendChild(img);
    }

    parent.appendChild(this.root);

    this._loadExpression(this.expression);
    this._loadOverlays().then(() => this._startBlinkLoop());
    this._startIdleLoop();
  }

  // --- public API (unchanged contract used by game-bridge) ---

  async setExpression(expression) {
    if (expression === this.expression) return;
    this.expression = expression;
    await this._loadExpression(expression);
    this.root.classList.add('expr-change');
    setTimeout(() => this.root?.classList.remove('expr-change'), 250);
  }

  setSpeaker(isSpeaker) {
    if (isSpeaker === this.isSpeaker) return;
    this.isSpeaker = isSpeaker;
    this.root.classList.toggle('is-speaker', isSpeaker);
    this.root.classList.toggle('is-quiet', !isSpeaker);
  }

  setTalking(isTalking) {
    if (isTalking === this.isTalking) return;
    this.isTalking = isTalking;
    if (isTalking) this._startMouthLoop();
    else this._stopMouthLoop();
  }

  /** External audio-amplitude lip-sync. level in 0..1. */
  setMouthOpen(level) {
    this._extMouthAt = performance.now();
    this._mouthLevel = Math.max(0, Math.min(1, level));
    this._applyMouth(this._mouthLevel);
  }

  setPosition(position) {
    if (position === this.position) return;
    this.root.classList.remove(`position-${this.position}`);
    this.position = position;
    this.root.classList.add(`position-${position}`);
    this.root.dataset.position = position;
  }

  setSlotX(pct) {
    this.root?.style.setProperty('--slot-x', pct);
  }

  destroy() {
    this._alive = false;
    this._stopBlinkLoop();
    this._stopMouthLoop();
    if (this._raf) cancelAnimationFrame(this._raf);
    if (this.root) {
      this.root.classList.add('fade-out');
      setTimeout(() => this.root?.remove(), 400);
    }
  }

  // --- loading ---

  async _loadExpression(expression) {
    const url = baseUrl(this.sessionId, this.characterId, expression);
    if (!this._loadedExpr.has(expression)) {
      await preload(url);
      this._loadedExpr.add(expression);
    }
    // Only apply if still the intended expression (guards stale async swaps).
    if (this.expression === expression && this._base) {
      this._base.src = url;
    }
  }

  async _loadOverlays() {
    const [eyesOk, halfOk, openOk] = await Promise.all([
      preload(overlayUrl(this.sessionId, this.characterId, 'eyes_closed')),
      preload(overlayUrl(this.sessionId, this.characterId, 'mouth_half')),
      preload(overlayUrl(this.sessionId, this.characterId, 'mouth_open')),
    ]);
    this._hasEyes = eyesOk;
    this._hasMouth = halfOk && openOk;

    if (eyesOk) this._ov.eyes.src = overlayUrl(this.sessionId, this.characterId, 'eyes_closed');
    if (halfOk) this._ov.mouth_half.src = overlayUrl(this.sessionId, this.characterId, 'mouth_half');
    if (openOk) this._ov.mouth_open.src = overlayUrl(this.sessionId, this.characterId, 'mouth_open');

    this.root?.classList.toggle('rig-static', !this._hasEyes && !this._hasMouth);
  }

  // --- idle motion (breathing + sway + per-emotion tilt) ---

  _startIdleLoop() {
    const loop = () => {
      if (!this._alive || !this.stack) return;
      const t = (performance.now() - this._t0) / 1000 + this._phase;
      const amp = this.isSpeaker ? 1.15 : 1.0;

      // Breathing: gentle vertical scale + lift.
      const breath = Math.sin(t * (2 * Math.PI / 4.2));
      const scaleY = 1 + 0.012 * amp * (breath * 0.5 + 0.5);
      const lift = -0.5 * amp * (breath * 0.5 + 0.5);   // percent of height

      // Head sway: slow horizontal drift + micro rotation, different period.
      const sway = Math.sin(t * (2 * Math.PI / 6.7) + 1.3);
      const tx = 0.9 * amp * sway;                      // percent
      const tilt = (EMOTION_TILT[this.expression] || 0) * 0.5 + 0.5 * amp * sway;

      this.stack.style.transform =
        `translateX(${tx}%) translateY(${lift}%) scaleY(${scaleY.toFixed(4)}) rotate(${tilt.toFixed(2)}deg)`;

      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  // --- blink ---

  _startBlinkLoop() {
    this._stopBlinkLoop();
    const schedule = () => {
      const wait = BLINK_MIN_MS + Math.random() * (BLINK_MAX_MS - BLINK_MIN_MS);
      this._blinkTimer = setTimeout(() => {
        if (this._hasEyes && !this._isBlinking) {
          this._isBlinking = true;
          this._ov.eyes.classList.add('is-visible');
          setTimeout(() => {
            this._ov.eyes?.classList.remove('is-visible');
            this._isBlinking = false;
          }, BLINK_HOLD_MS);
        }
        schedule();
      }, wait);
    };
    schedule();
  }

  _stopBlinkLoop() {
    if (this._blinkTimer) { clearTimeout(this._blinkTimer); this._blinkTimer = null; }
  }

  // --- mouth / lip-sync ---

  _startMouthLoop() {
    if (!this._hasMouth) return;
    this._stopMouthLoop();
    const tick = () => {
      // If audio is actively driving the mouth, let it own the frame.
      const extFresh = performance.now() - this._extMouthAt < 180;
      if (!extFresh) {
        // Procedural envelope: speech-like alternation with some randomness.
        const r = Math.random();
        const level = r < 0.25 ? 0 : r < 0.65 ? 0.45 : 0.9;
        this._applyMouth(level);
      }
      this._mouthTimer = setTimeout(tick, MOUTH_TICK_MS);
    };
    tick();
  }

  _stopMouthLoop() {
    if (this._mouthTimer) { clearTimeout(this._mouthTimer); this._mouthTimer = null; }
    this._applyMouth(0);
  }

  _applyMouth(level) {
    if (!this._hasMouth) return;
    const half = this._ov.mouth_half;
    const open = this._ov.mouth_open;
    if (level >= 0.55) {
      open.classList.add('is-visible');
      half.classList.remove('is-visible');
    } else if (level >= 0.15) {
      half.classList.add('is-visible');
      open.classList.remove('is-visible');
    } else {
      half.classList.remove('is-visible');
      open.classList.remove('is-visible');
    }
  }
}
