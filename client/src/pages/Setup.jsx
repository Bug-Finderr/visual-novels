import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { useCredits, useRefreshCredits } from '../lib/credits.js';

const GENRES = [
  'Fantasy', 'Sci-Fi', 'Romance', 'Horror', 'Mystery',
  'Slice of Life', 'Historical', 'Post-Apocalyptic', 'Supernatural', 'Comedy',
];
const ART_STYLES = [
  { value: 'anime', label: 'Anime' },
  { value: 'cartoon', label: 'Cartoon' },
  { value: 'realistic', label: 'Realistic' },
  { value: 'fiction', label: 'Illustrated' },
];
const TONES = ['Dark', 'Lighthearted', 'Romantic', 'Dramatic', 'Comedic', 'Mysterious', 'Bittersweet'];

const EMPTY = {
  genre: '', artStyle: '', setting: '', protagonistName: '',
  protagonistPersonality: '', tone: '', premise: '',
};

export default function Setup() {
  const navigate = useNavigate();
  const { user, googleEnabled, login, loading } = useAuth();
  const { data: credits } = useCredits(!!user);
  const refreshCredits = useRefreshCredits();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState('');
  const [outOfCredits, setOutOfCredits] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const billingOn = credits?.billingEnabled;
  const balance = credits?.balance;
  const cost = credits?.creditsPerStory ?? 1;
  const broke = billingOn && balance !== undefined && balance < cost;

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setOutOfCredits(false);
    setSubmitting(true);
    try {
      const session = await api.post('/sessions', form);
      await api.post(`/sessions/${session.id}/generate`);
      refreshCredits();
      navigate(`/loading/${session.id}`);
    } catch (err) {
      // 402 is the out-of-credits signal from the generation gate. Send them
      // somewhere useful rather than showing a raw error string.
      if (/credit/i.test(err.message || '')) {
        setOutOfCredits(true);
        refreshCredits();
      } else {
        setError(err.message || 'Something went wrong.');
      }
      setSubmitting(false);
    }
  }

  if (!loading && !user) {
    return (
      <div className="page page--narrow">
        <Link to="/" className="back-link">← Back</Link>
        <div className="page-head">
          <span className="eyebrow">Create</span>
          <h1 className="display">Author a new tale</h1>
          <p>Sign in to author and keep your own tales.</p>
        </div>
        <div className="panel" style={{ textAlign: 'center', padding: '2.5rem' }}>
          <button className="btn btn-primary btn-lg" onClick={login} disabled={!googleEnabled}>
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page page--narrow">
      <Link to="/" className="back-link">← Back</Link>
      <div className="page-head">
        <span className="eyebrow">Create</span>
        <h1 className="display">Author a new tale</h1>
        <p>Every detail steers the story, the cast, and the art.</p>
      </div>

      {broke && (
        <div className="banner">
          <span className="badge badge-error">no credits</span>
          You're out of story credits.
          <span className="spacer" />
          <Link to="/billing" className="btn btn-sm btn-primary">Top up</Link>
        </div>
      )}

      <form onSubmit={onSubmit}>
        <div className="section-title">Premise <span className="rule" /></div>

        <div className="field">
          <label htmlFor="genre">Genre</label>
          <div className="select-wrap">
            <select id="genre" className="select" required value={form.genre} onChange={upd('genre')}>
              <option value="">Choose a genre…</option>
              {GENRES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
        </div>

        <div className="field">
          <label>Art style</label>
          <div className="radio-grid">
            {ART_STYLES.map((s) => (
              <label className="radio-card" key={s.value}>
                <input
                  type="radio"
                  name="artStyle"
                  value={s.value}
                  required
                  checked={form.artStyle === s.value}
                  onChange={upd('artStyle')}
                />
                {s.label}
              </label>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="setting">Setting · world</label>
          <textarea
            id="setting" className="textarea" required maxLength={500}
            placeholder="A floating city above the clouds in a steampunk era…"
            value={form.setting} onChange={upd('setting')}
          />
          <span className="char-count">{form.setting.length} / 500</span>
        </div>

        <div className="section-title">Protagonist <span className="rule" /></div>

        <div className="field">
          <label htmlFor="pname">Name</label>
          <input
            id="pname" className="input" type="text" required
            placeholder="What are they called?"
            value={form.protagonistName} onChange={upd('protagonistName')}
          />
        </div>

        <div className="field">
          <label htmlFor="ppers">Personality</label>
          <textarea
            id="ppers" className="textarea" required maxLength={300}
            placeholder="Shy but determined; secretly brilliant…"
            value={form.protagonistPersonality} onChange={upd('protagonistPersonality')}
          />
          <span className="char-count">{form.protagonistPersonality.length} / 300</span>
        </div>

        <div className="section-title">Tone &amp; intent <span className="rule" /></div>

        <div className="field">
          <label htmlFor="tone">Tone</label>
          <div className="select-wrap">
            <select id="tone" className="select" required value={form.tone} onChange={upd('tone')}>
              <option value="">Choose a tone…</option>
              {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="field">
          <label htmlFor="premise">Story premise <span className="optional">— optional</span></label>
          <textarea
            id="premise" className="textarea" maxLength={1000}
            placeholder="A scenario you want to see unfold…"
            value={form.premise} onChange={upd('premise')}
          />
          <span className="char-count">{form.premise.length} / 1000</span>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={submitting || broke}>
            <span className="btn-icon">✦</span> {submitting ? 'Creating…' : 'Weave the story'}
          </button>
          {billingOn && (
            <span className="muted" style={{ fontSize: '0.85rem' }}>
              Costs {cost} {cost === 1 ? 'credit' : 'credits'}
              {balance !== undefined && ` · you have ${balance}`}
            </span>
          )}
        </div>

        {outOfCredits && (
          <div className="banner">
            <span className="badge badge-error">no credits</span>
            You're out of story credits — nothing was charged.
            <span className="spacer" />
            <Link to="/billing" className="btn btn-sm btn-primary">Top up</Link>
          </div>
        )}
        {error && <div className="form-error">{error}</div>}
      </form>
    </div>
  );
}
