import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../theme/ThemeContext.jsx';

/** Compact nav switcher: a light/dark toggle + a pack popover. The full
 *  gallery lives in Settings (the seed of the profile settings panel). */
export default function ThemeMenu() {
  const { pack, packs, setPack, resolved, toggleMode } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="theme-menu" ref={ref}>
      <button
        className="icon-btn"
        title={resolved === 'dark' ? 'Switch to light' : 'Switch to dark'}
        aria-label="Toggle light or dark mode"
        onClick={toggleMode}
      >
        {resolved === 'dark' ? '☾' : '☀'}
      </button>
      <button
        className="icon-btn"
        title="Choose theme"
        aria-label="Choose theme"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        ✦
      </button>
      {open && (
        <div className="theme-pop card" role="menu">
          <div className="theme-pop__title">Theme</div>
          {packs.map((p) => (
            <button
              key={p.id}
              className={`theme-pop__item ${p.id === pack ? 'active' : ''}`}
              role="menuitemradio"
              aria-checked={p.id === pack}
              onClick={() => setPack(p.id)}
            >
              <span className="theme-pop__dots">
                {p.swatches.slice(0, 3).map((c, i) => (
                  <i key={i} style={{ background: c }} />
                ))}
              </span>
              {p.name}
              {p.id === pack && <span className="tick">✓</span>}
            </button>
          ))}
          <Link to="/settings" className="theme-pop__more" onClick={() => setOpen(false)}>
            All settings →
          </Link>
        </div>
      )}
    </div>
  );
}
