import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

const GENRES = [
  'Fantasy', 'Sci-Fi', 'Romance', 'Horror', 'Mystery',
  'Slice of Life', 'Historical', 'Post-Apocalyptic', 'Supernatural', 'Comedy',
];

const ART_STYLES = [
  { value: 'anime', label: 'Anime' },
  { value: 'cartoon', label: 'Cartoon' },
  { value: 'realistic', label: 'Realistic' },
  { value: 'fiction', label: 'Fiction / Illustrated' },
];

const TONES = [
  'Dark', 'Lighthearted', 'Romantic', 'Dramatic', 'Comedic', 'Mysterious', 'Bittersweet',
];

export function renderSetupWizard(container) {
  container.innerHTML = `
    <div class="setup-wizard">
      <button class="btn btn-ghost back-btn" id="btn-back">&larr; Back</button>

      <header class="page-header">
        <div class="ornament">Craft</div>
        <h1 class="display-title">Author a new tale</h1>
        <p class="page-subtitle">Every detail steers the story.</p>
      </header>

      <form id="setup-form">
        <div class="section-rule">Premise</div>

        <div class="form-group">
          <label for="genre">Genre</label>
          <select id="genre" name="genre" required>
            <option value="">Choose a genre…</option>
            ${GENRES.map((g) => `<option value="${g}">${g}</option>`).join('')}
          </select>
        </div>

        <div class="form-group">
          <label>Art style</label>
          <div class="radio-group">
            ${ART_STYLES.map(
              (s) => `
              <label class="radio-card">
                <input type="radio" name="artStyle" value="${s.value}" required />
                <span class="radio-label">${s.label}</span>
              </label>
            `
            ).join('')}
          </div>
        </div>

        <div class="form-group">
          <label for="setting">Setting · world</label>
          <textarea id="setting" name="setting" required maxlength="500"
            placeholder="A floating city above the clouds in a steampunk era…"></textarea>
          <span class="char-count" data-for="setting">0 / 500</span>
        </div>

        <div class="section-rule">Protagonist</div>

        <div class="form-group">
          <label for="protagonistName">Name</label>
          <input type="text" id="protagonistName" name="protagonistName" required
            placeholder="What are they called?" />
        </div>

        <div class="form-group">
          <label for="protagonistPersonality">Personality</label>
          <textarea id="protagonistPersonality" name="protagonistPersonality" required maxlength="300"
            placeholder="Shy but determined; secretly brilliant…"></textarea>
          <span class="char-count" data-for="protagonistPersonality">0 / 300</span>
        </div>

        <div class="section-rule">Tone &amp; intent</div>

        <div class="form-group">
          <label for="tone">Tone</label>
          <select id="tone" name="tone" required>
            <option value="">Choose a tone…</option>
            ${TONES.map((t) => `<option value="${t}">${t}</option>`).join('')}
          </select>
        </div>

        <div class="form-group">
          <label for="premise">Story premise <span style="color: var(--ink-dim); font-weight: 400; letter-spacing: 0.02em; text-transform: none;">— optional</span></label>
          <textarea id="premise" name="premise" maxlength="1000"
            placeholder="A scenario you want to see unfold…"></textarea>
          <span class="char-count" data-for="premise">0 / 1000</span>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-lg" id="btn-generate">
            <span class="btn-icon">&#10022;</span> Weave the story
          </button>
        </div>

        <div id="form-error" class="error-message" style="display:none;"></div>
      </form>
    </div>
  `;

  container.querySelector('#btn-back').addEventListener('click', () => navigate('/'));

  container.querySelectorAll('textarea[maxlength]').forEach((ta) => {
    const counter = container.querySelector(`.char-count[data-for="${ta.name}"]`);
    if (counter) {
      ta.addEventListener('input', () => {
        counter.textContent = `${ta.value.length} / ${ta.maxLength}`;
      });
    }
  });

  container.querySelector('#setup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = container.querySelector('#btn-generate');
    const errDiv = container.querySelector('#form-error');
    errDiv.style.display = 'none';

    btn.disabled = true;
    btn.textContent = 'Creating session…';

    try {
      const formData = new FormData(e.target);
      const data = Object.fromEntries(formData.entries());

      const session = await api.post('/sessions', data);
      await api.post(`/sessions/${session.id}/generate`);

      navigate(`/loading/${session.id}`);
    } catch (err) {
      errDiv.textContent = err.message;
      errDiv.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">&#10022;</span> Weave the story';
    }
  });
}
