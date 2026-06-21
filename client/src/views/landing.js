import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

export async function renderLanding(container) {
  container.innerHTML = `
    <div class="landing">
      <div class="landing-hero">
        <div class="ornament">Storyplex</div>
        <h1 class="landing-title">Storyplex</h1>
        <p class="landing-tagline">Worlds woven by AI, line by line.</p>
        <p class="landing-desc">Conjure a unique visual novel from a single premise — story, characters, scenes, and voices, all generated. No two playthroughs alike.</p>
        <div class="landing-actions">
          <button class="btn btn-primary btn-lg" id="btn-new-game">
            <span class="btn-icon">&#9656;</span> Begin a tale
          </button>
          <button class="btn btn-secondary btn-lg" id="btn-load-game">Continue</button>
        </div>
      </div>

      <div class="landing-sessions" id="recent-sessions" style="display:none;">
        <div class="section-rule">Recent tales</div>
        <div id="session-list"></div>
        <a class="more-link" id="link-all-sessions">See all &rarr;</a>
      </div>
    </div>
  `;

  container.querySelector('#btn-new-game').addEventListener('click', () => {
    navigate('/setup');
  });

  container.querySelector('#btn-load-game').addEventListener('click', () => {
    navigate('/sessions');
  });

  container.querySelector('#link-all-sessions').addEventListener('click', (e) => {
    e.preventDefault();
    navigate('/sessions');
  });

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
          <span class="badge badge-${s.status}">${s.status}</span>
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
