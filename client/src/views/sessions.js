import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';
import { escapeHtml } from '../utils/escape.js';

export async function renderSessions(container) {
  container.innerHTML = `
    <div class="sessions-view">
      <button class="btn btn-ghost back-btn" id="btn-back">&larr; Back</button>
      <div class="sessions-header">
        <h2>Your Stories</h2>
        <button class="btn btn-primary" id="btn-new">+ New Story</button>
      </div>
      <div id="sessions-list" class="sessions-list">
        <p class="loading-text">Loading...</p>
      </div>
    </div>
  `;

  container.querySelector('#btn-back').addEventListener('click', () => navigate('/'));
  container.querySelector('#btn-new').addEventListener('click', () => navigate('/setup'));

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
      .map((s) => {
        const actions = [];
        if (s.status === 'ready' || s.status === 'playing') {
          actions.push('<button class="btn btn-primary btn-play">Play</button>');
        } else if (s.status === 'generating') {
          actions.push('<button class="btn btn-secondary btn-progress">View Progress</button>');
        } else if (s.status === 'error') {
          actions.push('<button class="btn btn-secondary btn-retry">Retry</button>');
        }
        actions.push('<button class="btn btn-danger btn-delete">Delete</button>');

        const date = s.last_played_at
          ? `Last played: ${new Date(s.last_played_at).toLocaleString()}`
          : `Created: ${new Date(s.created_at).toLocaleDateString()}`;

        return `
          <div class="session-card" data-id="${escapeHtml(s.id)}">
            <div class="session-card-info">
              <h3 class="session-card-title">${escapeHtml(s.title)}</h3>
              <div class="session-card-meta">
                <span class="badge badge-${escapeHtml(s.status)}">${escapeHtml(s.status)}</span>
                <span class="session-card-genre">${escapeHtml(s.setup_genre || '')}</span>
                <span class="session-card-tone">${escapeHtml(s.setup_tone || '')}</span>
              </div>
              <p class="session-card-date">${escapeHtml(date)}</p>
            </div>
            <div class="session-card-actions">${actions.join('')}</div>
          </div>
        `;
      })
      .join('');

    listEl.querySelectorAll('.session-card').forEach((card) => {
      const id = card.dataset.id;

      const playBtn = card.querySelector('.btn-play');
      if (playBtn) playBtn.addEventListener('click', () => navigate(`/game/${id}`));

      const progressBtn = card.querySelector('.btn-progress');
      if (progressBtn) progressBtn.addEventListener('click', () => navigate(`/loading/${id}`));

      const retryBtn = card.querySelector('.btn-retry');
      if (retryBtn) {
        retryBtn.addEventListener('click', async () => {
          try {
            await api.post(`/sessions/${id}/generate`);
            navigate(`/loading/${id}`);
          } catch (err) {
            alert('Failed to retry: ' + err.message);
          }
        });
      }

      card.querySelector('.btn-delete').addEventListener('click', async (e) => {
        e.stopPropagation();
        if (confirm('Delete this story? This cannot be undone.')) {
          try {
            await api.delete(`/sessions/${id}`);
            renderSessions(container);
          } catch (err) {
            alert('Delete failed: ' + err.message);
          }
        }
      });
    });
  } catch (err) {
    container.querySelector('#sessions-list').innerHTML =
      `<div class="error-message">Failed to load sessions: ${escapeHtml(err.message)}</div>`;
  }
}
