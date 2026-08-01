import { Link } from 'react-router-dom';
import { useTheme } from '../theme/ThemeContext.jsx';
import { useAuth } from '../auth/AuthContext.jsx';
import Avatar from '../components/Avatar.jsx';

const MODES = ['light', 'dark', 'system'];

/**
 * Settings — the seed of the future profile settings panel. Theme lives here
 * now (persisted to localStorage); account/playback are placeholders that
 * light up as auth + features land.
 */
export default function Settings() {
  const { pack, setPack, mode, setMode, packs } = useTheme();
  const { user, googleEnabled, login, logout } = useAuth();

  return (
    <div className="page page--narrow">
      <Link to="/" className="back-link">← Back</Link>
      <div className="page-head">
        <span className="eyebrow">Settings</span>
        <h1 className="display">Preferences</h1>
        <p>Make StoryPlex yours. These live on this device for now — they'll move to your
          profile once accounts arrive.</p>
      </div>

      <section className="settings-section">
        <h2>Theme</h2>
        <p className="sub">Pick a look. It reskins the whole app instantly — even the reader.</p>
        <div className="theme-gallery">
          {packs.map((p) => (
            <button
              key={p.id}
              className={`theme-swatch ${p.id === pack ? 'selected' : ''}`}
              onClick={() => setPack(p.id)}
              aria-pressed={p.id === pack}
            >
              <div className="theme-swatch__preview" style={{ background: p.swatches[0] }}>
                {p.swatches.slice(1).map((c, i) => (
                  <span key={i} className="sw" style={{ background: c }} />
                ))}
              </div>
              <div className="theme-swatch__label">
                <span>{p.name}</span>
                {p.id === pack && <span className="tick">✓</span>}
              </div>
            </button>
          ))}
        </div>

        <div className="setting-row" style={{ marginTop: '1.5rem' }}>
          <div style={{ flex: 1 }}>
            <div className="setting-label">Appearance</div>
            <div className="setting-desc">Light, dark, or follow your system.</div>
          </div>
          <div className="segmented">
            {MODES.map((m) => (
              <button key={m} className={mode === m ? 'active' : ''} onClick={() => setMode(m)}>
                {m[0].toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h2>Account</h2>
        {user ? (
          <div className="panel">
            <div className="row" style={{ gap: '1rem' }}>
              <div className="user-avatar user-avatar--lg" aria-hidden="true">
                <Avatar url={user.avatarUrl} name={user.displayName || user.username} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="setting-label">{user.displayName || user.username}</div>
                <div className="setting-desc">{user.email} · @{user.username}</div>
              </div>
              <button className="btn btn-danger" onClick={logout}>Sign out</button>
            </div>
          </div>
        ) : (
          <>
            <p className="sub">Sign in to publish tales, follow creators, and sync across devices.</p>
            <div className="panel">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <div className="setting-label">Google sign-in</div>
                  <div className="setting-desc">
                    {googleEnabled
                      ? 'Sign in with your Google account.'
                      : 'Not configured on this server yet.'}
                  </div>
                </div>
                <button className="btn btn-primary" onClick={login} disabled={!googleEnabled}>
                  Sign in with Google
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <section className="settings-section">
        <h2>Playback</h2>
        <div className="setting-row">
          <div style={{ flex: 1 }}>
            <div className="setting-label">Character voices</div>
            <div className="setting-desc">Streamed TTS with lip-sync during dialogue.</div>
          </div>
          <span className="locked-note">● on</span>
        </div>
        <div className="setting-row">
          <div style={{ flex: 1 }}>
            <div className="setting-label">Typewriter speed</div>
            <div className="setting-desc">Per-line reveal pacing.</div>
          </div>
          <span className="locked-note">standard</span>
        </div>
      </section>
    </div>
  );
}
