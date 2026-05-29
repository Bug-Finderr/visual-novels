import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

export async function renderSessions(container) {
  container.innerHTML = `
    <div class="sessions-view">
      <button class="btn btn-ghost back-btn" id="btn-back">&larr; Back</button>

      <header class="page-header">
        <div class="ornament">Library</div>
        <h1 class="display-title">Your tales</h1>
        <p class="page-subtitle">Each playthrough is one of a kind.</p>
      </header>

      <div id="sessions-list" class="sessions-grid">
        <div class="empty-state"><p>Loading…</p></div>
      </div>
    </div>
  `;

  container.querySelector('#btn-back').addEventListener('click', () => navigate('/'));

  try {
    const sessions = await api.get('/sessions');
    const listEl = container.querySelector('#sessions-list');

    if (sessions.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <p>The shelves are empty. Begin a new tale.</p>
          <button class="btn btn-primary btn-lg" id="btn-create">
            <span class="btn-icon">&#10022;</span> Author a tale
          </button>
        </div>
      `;
      listEl.querySelector('#btn-create').addEventListener('click', () => navigate('/setup'));
      return;
    }

    listEl.innerHTML = sessions
      .map(
        (s) => `
      <div class="session-card" data-id="${s.id}">
        <div class="session-card-info">
          <h3 class="session-card-title">${s.title}</h3>
          <div class="session-card-meta">
            <span class="badge badge-${s.status}">${s.status}</span>
            ${(s.chapter_number && s.chapter_number > 1) ? `<span class="session-card-genre">Chapter ${s.chapter_number}</span>` : ''}
            <span class="session-card-genre">${s.setup_genre}</span>
            <span class="session-card-tone">${s.setup_tone}</span>
          </div>
          <p class="session-card-date">${new Date(s.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</p>
        </div>
        <div class="session-card-actions">
          ${
            s.status === 'ready' || s.status === 'playing'
              ? '<button class="btn btn-primary btn-play">&#9656; Read</button>'
              : s.status === 'generating'
              ? '<button class="btn btn-secondary btn-progress">Progress</button>'
              : ''
          }
          <button class="btn btn-danger btn-delete">Delete</button>
        </div>
      </div>
    `
      )
      .join('');

    listEl.querySelectorAll('.session-card').forEach((card) => {
      const id = card.dataset.id;

      const playBtn = card.querySelector('.btn-play');
      if (playBtn) {
        playBtn.addEventListener('click', () => navigate(`/game/${id}`));
      }

      const progressBtn = card.querySelector('.btn-progress');
      if (progressBtn) {
        progressBtn.addEventListener('click', () => navigate(`/loading/${id}`));
      }

      card.querySelector('.btn-delete').addEventListener('click', async (e) => {
        e.stopPropagation();
        if (confirm('Delete this tale? This cannot be undone.')) {
          await api.delete(`/sessions/${id}`);
          renderSessions(container);
        }
      });
    });
  } catch (err) {
    container.querySelector('#sessions-list').innerHTML = `
      <div class="error-message">Failed to load sessions: ${err.message}</div>
    `;
  }
}
