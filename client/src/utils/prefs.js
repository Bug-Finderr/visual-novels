const KEY = 'storyplex:prefs:v1';

const DEFAULTS = {
  typewriterSpeed: 'normal', // 'slow' | 'normal' | 'fast' | 'instant'
  autoAdvance: false,
  autoAdvanceDelayMs: 1400,
};

const SPEED_MS = { slow: 40, normal: 20, fast: 8, instant: 0 };

export function loadPrefs() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {}
}

export function speedMs(speedKey) {
  return SPEED_MS[speedKey] ?? SPEED_MS.normal;
}
