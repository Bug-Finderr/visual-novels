/**
 * AnimatedSprite — drives a single on-screen character with idle breathing,
 * randomized blink loop, mouth-flap during dialogue, and smooth expression
 * crossfade. Falls back to static sprite if animation frames aren't available
 * (404 on `<expr>_blink.png`).
 *
 * DOM structure produced:
 *   <div class="character-sprite position-X">
 *     <div class="anim-stack">
 *       <img class="anim-frame anim-base    is-visible" src=".../neutral.png">
 *       <img class="anim-frame anim-blink"             src=".../neutral_blink.png">
 *       <img class="anim-frame anim-mouth-half"        src=".../neutral_mouth_half.png">
 *       <img class="anim-frame anim-mouth-open"        src=".../neutral_mouth_open.png">
 *     </div>
 *   </div>
 */

const FRAME_KEYS = ['base', 'blink', 'mouth_half', 'mouth_open'];
const MOUTH_CYCLE = ['half', 'open', 'half', 'closed', 'closed'];
const MOUTH_FRAME_MS = 110;
const BLINK_MIN_MS = 2800;
const BLINK_MAX_MS = 6500;
const BLINK_HOLD_MS = 110;

function frameUrl(sessionId, characterId, expression, frame) {
  const suffix = frame === 'base' ? '' : `_${frame}`;
  return `/game-assets/${sessionId}/characters/${characterId}/${expression}${suffix}.png`;
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
    this._frames = {}; // {base: <img>, blink: <img>, mouth_half: <img>, mouth_open: <img>}
    this._activeFrame = 'base';

    this._blinkTimer = null;
    this._mouthTimer = null;
    this._mouthIndex = 0;

    // expression -> { ready: bool, hasAnim: bool }
    this._exprState = new Map();
  }

  mount(parent) {
    this.root = document.createElement('div');
    this.root.className = `character-sprite position-${this.position} anim-enabled fade-in`;
    this.root.dataset.charId = this.characterId;

    this.stack = document.createElement('div');
    this.stack.className = 'anim-stack';
    this.root.appendChild(this.stack);

    for (const key of FRAME_KEYS) {
      const img = document.createElement('img');
      img.className = `anim-frame anim-${key.replace('_', '-')}`;
      img.alt = this.name;
      img.draggable = false;
      this._frames[key] = img;
      this.stack.appendChild(img);
    }

    parent.appendChild(this.root);
    this._loadExpression(this.expression).then(() => this._startBlinkLoop());
  }

  async setExpression(expression) {
    if (expression === this.expression) return;
    this.expression = expression;
    await this._loadExpression(expression);
    this._swapTo('base');
    // brief cross-flash effect
    this.root.classList.add('expr-change');
    setTimeout(() => this.root.classList.remove('expr-change'), 250);
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

  setPosition(position) {
    if (position === this.position) return;
    this.root.classList.remove(`position-${this.position}`);
    this.position = position;
    this.root.classList.add(`position-${position}`);
  }

  destroy() {
    this._stopBlinkLoop();
    this._stopMouthLoop();
    if (this.root) {
      this.root.classList.add('fade-out');
      setTimeout(() => this.root?.remove(), 400);
    }
  }

  // --- internals ---

  async _loadExpression(expression) {
    const cached = this._exprState.get(expression);
    if (cached?.ready) {
      this._applyFrameSources(expression, cached.hasAnim);
      return;
    }

    const baseUrl = frameUrl(this.sessionId, this.characterId, expression, 'base');
    // probe blink frame to detect whether animation set exists for this expression
    const blinkUrl = frameUrl(this.sessionId, this.characterId, expression, 'blink');
    const [baseOk, blinkOk] = await Promise.all([preload(baseUrl), preload(blinkUrl)]);

    const hasAnim = baseOk && blinkOk;
    this._exprState.set(expression, { ready: true, hasAnim });

    if (hasAnim) {
      // also preload mouth frames so the cycle doesn't flicker
      await Promise.all([
        preload(frameUrl(this.sessionId, this.characterId, expression, 'mouth_half')),
        preload(frameUrl(this.sessionId, this.characterId, expression, 'mouth_open')),
      ]);
    }

    this._applyFrameSources(expression, hasAnim);
  }

  _applyFrameSources(expression, hasAnim) {
    this.root.classList.toggle('anim-static', !hasAnim);
    this._frames.base.src = frameUrl(this.sessionId, this.characterId, expression, 'base');
    if (hasAnim) {
      for (const key of FRAME_KEYS) {
        if (key === 'base') continue;
        this._frames[key].src = frameUrl(this.sessionId, this.characterId, expression, key);
      }
    } else {
      // Avoid 404 noise for missing extra frames in static fallback
      for (const key of FRAME_KEYS) {
        if (key === 'base') continue;
        this._frames[key].removeAttribute('src');
      }
    }
    this._swapTo('base');
  }

  _swapTo(frameKey) {
    if (frameKey === this._activeFrame) return;
    this._frames[this._activeFrame]?.classList.remove('is-visible');
    this._frames[frameKey]?.classList.add('is-visible');
    this._activeFrame = frameKey;
  }

  // --- blink ---
  _startBlinkLoop() {
    this._stopBlinkLoop();
    const schedule = () => {
      const wait = BLINK_MIN_MS + Math.random() * (BLINK_MAX_MS - BLINK_MIN_MS);
      this._blinkTimer = setTimeout(() => {
        if (!this._isAnimAvailable()) { schedule(); return; }
        if (!this.isTalking) {
          this._swapTo('blink');
          setTimeout(() => {
            // resume base unless talking-state took over in the meantime
            if (!this.isTalking) this._swapTo('base');
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

  // --- mouth flap ---
  _startMouthLoop() {
    if (!this._isAnimAvailable()) return;
    this._stopMouthLoop();
    this._mouthIndex = 0;
    const tick = () => {
      const phase = MOUTH_CYCLE[this._mouthIndex % MOUTH_CYCLE.length];
      if (phase === 'closed') this._swapTo('base');
      else if (phase === 'half') this._swapTo('mouth_half');
      else this._swapTo('mouth_open');
      this._mouthIndex++;
      this._mouthTimer = setTimeout(tick, MOUTH_FRAME_MS);
    };
    tick();
  }
  _stopMouthLoop() {
    if (this._mouthTimer) { clearTimeout(this._mouthTimer); this._mouthTimer = null; }
    if (this._activeFrame !== 'base') this._swapTo('base');
  }

  _isAnimAvailable() {
    return this._exprState.get(this.expression)?.hasAnim === true;
  }
}
