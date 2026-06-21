/**
 * Tiny Web Audio synth for UI sound cues — no external assets, lazily inits
 * the AudioContext on first user interaction (browser autoplay policy).
 */
let _ctx = null;
let _enabled = true;

function ensureCtx() {
  if (_ctx) return _ctx;
  try {
    _ctx = new (window.AudioContext || window.webkitAudioContext)();
  } catch {
    _enabled = false;
  }
  return _ctx;
}

function tone({ freq = 440, duration = 0.08, type = 'sine', gain = 0.08, attack = 0.005, release = 0.04, when = 0 }) {
  if (!_enabled) return;
  const ctx = ensureCtx();
  if (!ctx) return;
  const t0 = ctx.currentTime + when;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + attack);
  g.gain.linearRampToValueAtTime(0, t0 + duration + release);
  osc.connect(g).connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + duration + release + 0.05);
}

export const audioCue = {
  setEnabled(v) { _enabled = !!v; },
  isEnabled() { return _enabled; },
  /** Soft click for advancing dialogue. */
  click() {
    tone({ freq: 320, type: 'triangle', duration: 0.03, gain: 0.05, release: 0.03 });
  },
  /** Two-tone chime for choice selection. */
  select() {
    tone({ freq: 660, type: 'sine', duration: 0.06, gain: 0.06 });
    tone({ freq: 880, type: 'sine', duration: 0.06, gain: 0.06, when: 0.07 });
  },
  /** Soft tick for choice button hover. */
  hover() {
    tone({ freq: 540, type: 'sine', duration: 0.02, gain: 0.025, release: 0.03 });
  },
  /** Low whoosh for scene change. */
  sceneIn() {
    tone({ freq: 220, type: 'sine', duration: 0.18, gain: 0.06, attack: 0.04, release: 0.15 });
  },
};
