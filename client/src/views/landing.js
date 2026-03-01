import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

export async function renderLanding(container) {
  container.innerHTML = `
    <div class="landing">
      <div class="landing-hero">
        <h1 class="landing-title">Storyplex</h1>
        <p class="landing-subtitle">AI-Powered Visual Novel Experience</p>
        <p class="landing-desc">Create unique visual novels with AI-generated stories, characters, and artwork. Every playthrough is one of a kind.</p>
        <div class="landing-actions">
          <button class="btn btn-primary btn-lg" id="btn-new-game">New Story</button>
          <button class="btn btn-secondary btn-lg" id="btn-load-game">Continue Story</button>
        </div>
      </div>
      <div class="landing-sessions" id="recent-sessions" style="display:none;">
        <h3>Recent Stories</h3>
        <div id="session-list"></div>
      </div>
    </div>
  `;

  container.querySelector('#btn-new-game').addEventListener('click', () => {
    navigate('/setup');
  });

  container.querySelector('#btn-load-game').addEventListener('click', () => {
    navigate('/sessions');
  });

  // Show recent sessions
  try {
    const sessions = await api.get('/sessions');
    if (sessions.length > 0) {
      const recentDiv = container.querySelector('#recent-sessions');
      recentDiv.style.display = 'block';
      const listDiv = container.querySelector('#session-list');
      listDiv.innerHTML = sessions
        .slice(0, 3)
        .map(
          (s) => `
        <div class="session-card-mini" data-id="${s.id}">
          <span class="session-title">${s.title}</span>
          <span class="session-status badge-${s.status}">${s.status}</span>
        </div>
      `
        )
        .join('');

      listDiv.querySelectorAll('.session-card-mini').forEach((card) => {
        card.addEventListener('click', () => {
          const id = card.dataset.id;
          const session = sessions.find((s) => s.id === id);
          if (session.status === 'ready' || session.status === 'playing') {
            navigate(`/game/${id}`);
          } else if (session.status === 'generating') {
            navigate(`/loading/${id}`);
          }
        });
      });
    }
  } catch (e) {
    // Server might not be running yet — that's fine
  }
}
