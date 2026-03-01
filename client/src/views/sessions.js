import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

export async function renderSessions(container) {
  container.innerHTML = `
    <div class="sessions-view">
      <button class="btn btn-ghost back-btn" id="btn-back">&larr; Back</button>
      <h2>Your Stories</h2>
      <div id="sessions-list" class="sessions-list">
        <p class="loading-text">Loading...</p>
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
          <p>No stories yet. Create your first one!</p>
          <button class="btn btn-primary" id="btn-create">Create Story</button>
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
            <span class="session-card-genre">${s.setup_genre}</span>
            <span class="session-card-tone">${s.setup_tone}</span>
          </div>
          <p class="session-card-date">Created: ${new Date(s.created_at).toLocaleDateString()}</p>
        </div>
        <div class="session-card-actions">
          ${
            s.status === 'ready' || s.status === 'playing'
              ? '<button class="btn btn-primary btn-play">Play</button>'
              : s.status === 'generating'
              ? '<button class="btn btn-secondary btn-progress">View Progress</button>'
              : ''
          }
          <button class="btn btn-danger btn-delete">Delete</button>
        </div>
      </div>
    `
      )
      .join('');

    // Bind event listeners
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
        if (confirm('Delete this story? This cannot be undone.')) {
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
