import { createContext, useContext, useEffect, useState, useCallback } from 'react';

/* Modular theme system. A "pack" is a named token set (see styles/theme.css);
 * mode is light | dark | system. Both persist to localStorage now and will
 * migrate to server-side user prefs once accounts land. */

const STORAGE_KEY = 'storyplex.theme';

export const THEME_PACKS = [
  { id: 'manga-ink', name: 'Manga Ink', blurb: 'B&W shonen panels · vermillion pop',
    swatches: ['#141414', '#f7f3e9', '#e63329', '#8a8578'] },
  { id: 'neon', name: 'Neon City Pop', blurb: '80s synthwave · magenta + cyan glow',
    swatches: ['#0c0a24', '#ff3cac', '#21e6e0', '#7a5cff'] },
  { id: 'otome', name: 'Sakura Otome', blurb: 'Romantic dating-sim · pink + gilt',
    swatches: ['#fff6f8', '#e85d8a', '#9b8ce0', '#d8b25a'] },
  { id: 'kawaii', name: 'Kawaii Pop', blurb: 'Candy sticker-book cuteness',
    swatches: ['#ff6fb5', '#5cc8ff', '#ffd84d', '#7be0c6'] },
];

const PACK_IDS = THEME_PACKS.map((p) => p.id);
const MODES = ['light', 'dark', 'system'];

function readPref() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}
function systemDark() {
  return typeof window !== 'undefined' && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}
function resolveMode(mode) {
  return mode === 'dark' || (mode === 'system' && systemDark()) ? 'dark' : 'light';
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [pack, setPackState] = useState(() => {
    const p = readPref().pack;
    return PACK_IDS.includes(p) ? p : 'manga-ink';
  });
  const [mode, setModeState] = useState(() => {
    const m = readPref().mode;
    return MODES.includes(m) ? m : 'system';
  });
  const [resolved, setResolved] = useState(() => resolveMode(mode));

  const apply = useCallback((p, m) => {
    const r = resolveMode(m);
    const el = document.documentElement;
    el.setAttribute('data-theme', p);
    el.setAttribute('data-mode', r);
    setResolved(r);
  }, []);

  // Reflect state → <html> attributes + persist.
  useEffect(() => {
    apply(pack, mode);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ pack, mode }));
    } catch { /* storage unavailable — theme still applies for the session */ }
  }, [pack, mode, apply]);

  // Track OS changes while on "system".
  useEffect(() => {
    if (mode !== 'system') return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => apply(pack, 'system');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [mode, pack, apply]);

  const value = {
    pack,
    mode,
    resolved,
    packs: THEME_PACKS,
    setPack: setPackState,
    setMode: setModeState,
    toggleMode: () => setModeState(resolved === 'dark' ? 'light' : 'dark'),
  };
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
}
