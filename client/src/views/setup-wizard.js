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
      <h2>Create Your Story</h2>
      <p class="setup-desc">Fill in the details below and AI will generate a unique visual novel for you.</p>

      <form id="setup-form">
        <div class="form-group">
          <label for="genre">Genre *</label>
          <select id="genre" name="genre" required>
            <option value="">Select a genre...</option>
            ${GENRES.map((g) => `<option value="${g}">${g}</option>`).join('')}
          </select>
        </div>

        <div class="form-group">
          <label>Art Style *</label>
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
          <label for="setting">Setting / World *</label>
          <textarea id="setting" name="setting" required maxlength="500"
            placeholder="Describe the world (e.g., &quot;A floating city above the clouds in a steampunk era&quot;)"></textarea>
          <span class="char-count" data-for="setting">0/500</span>
        </div>

        <div class="form-group">
          <label for="protagonistName">Protagonist Name *</label>
          <input type="text" id="protagonistName" name="protagonistName" required
            placeholder="Enter protagonist name" />
        </div>

        <div class="form-group">
          <label for="protagonistPersonality">Protagonist Personality *</label>
          <textarea id="protagonistPersonality" name="protagonistPersonality" required maxlength="300"
            placeholder="Describe their personality (e.g., &quot;Shy but determined, secretly brilliant&quot;)"></textarea>
          <span class="char-count" data-for="protagonistPersonality">0/300</span>
        </div>

        <div class="form-group">
          <label for="tone">Tone *</label>
          <select id="tone" name="tone" required>
            <option value="">Select a tone...</option>
            ${TONES.map((t) => `<option value="${t}">${t}</option>`).join('')}
          </select>
        </div>

        <div class="form-group">
          <label for="premise">Story Premise (Optional)</label>
          <textarea id="premise" name="premise" maxlength="1000"
            placeholder="Describe a story premise or scenario you want..."></textarea>
          <span class="char-count" data-for="premise">0/1000</span>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-lg" id="btn-generate">
            Generate My Story
          </button>
        </div>

        <div id="form-error" class="error-message" style="display:none;"></div>
      </form>
    </div>
  `;

  // Back button
  container.querySelector('#btn-back').addEventListener('click', () => navigate('/'));

  // Character count for textareas
  container.querySelectorAll('textarea[maxlength]').forEach((ta) => {
    const counter = container.querySelector(`.char-count[data-for="${ta.name}"]`);
    if (counter) {
      ta.addEventListener('input', () => {
        counter.textContent = `${ta.value.length}/${ta.maxLength}`;
      });
    }
  });

  // Form submission
  container.querySelector('#setup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = container.querySelector('#btn-generate');
    const errDiv = container.querySelector('#form-error');
    errDiv.style.display = 'none';

    btn.disabled = true;
    btn.textContent = 'Creating session...';

    try {
      const formData = new FormData(e.target);
      const data = Object.fromEntries(formData.entries());

      // Create session
      const session = await api.post('/sessions', data);

      // Kick off generation
      await api.post(`/sessions/${session.id}/generate`);

      // Navigate to loading screen
      navigate(`/loading/${session.id}`);
    } catch (err) {
      errDiv.textContent = err.message;
      errDiv.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Generate My Story';
    }
  });
}
