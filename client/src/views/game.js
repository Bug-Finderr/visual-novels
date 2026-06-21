import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';
import { gameBridge } from '../services/game-bridge.js';

export async function renderGame(container, params) {
  const sessionId = params[0];
  if (!sessionId) {
    navigate('/');
    return;
  }

  container.innerHTML = `
    <div class="game-view">
      <div class="game-header">
        <button class="btn btn-ghost" id="btn-back-to-menu">&larr; Library</button>
        <span class="game-title" id="game-title">Loading…</span>
        <button class="btn btn-ghost" id="btn-pause" title="Pause (Esc)">&#9776; Menu</button>
      </div>
      <div class="game-container" id="game-container">
        <div class="game-canvas" id="game-canvas">
          <div class="scene-background" id="scene-bg"></div>
          <div class="characters-layer" id="characters-layer"></div>
          <div class="dialogue-box" id="dialogue-box" style="display:none;">
            <div class="speaker-name" id="speaker-name"></div>
            <div class="dialogue-text" id="dialogue-text"></div>
            <div class="dialogue-advance" id="dialogue-advance">&#9660;</div>
          </div>
          <div class="interaction-panel" id="interaction-panel" style="display:none;">
            <div class="choices-panel" id="choices-panel"></div>
            <div class="free-input-panel" id="free-input-panel">
              <input type="text" id="free-input-text" placeholder="What do you want to say or do?" maxlength="300" />
              <button class="btn btn-primary" id="free-input-send">Send</button>
            </div>
          </div>
          <div class="loading-overlay" id="loading-overlay" style="display:none;">
            <div class="thinking-indicator">
              <span></span><span></span><span></span>
            </div>
            <p>The next page is being written…</p>
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-back-to-menu').addEventListener('click', () => {
    navigate('/');
  });
  container.querySelector('#btn-pause').addEventListener('click', () => {
    gameBridge.togglePauseMenu();
  });

  try {
    // Load session data
    const [session, characters, scenes, script] = await Promise.all([
      api.get(`/sessions/${sessionId}`),
      api.get(`/sessions/${sessionId}/characters`),
      api.get(`/sessions/${sessionId}/scenes`),
      api.get(`/sessions/${sessionId}/script`),
    ]);

    container.querySelector('#game-title').textContent = session.title;

    // Asset cache buster — keyed on session updated_at. When the backend
    // regenerates frames in place (retrofit / new dynamic char), the URL
    // string changes and the immutable HTTP cache is bypassed naturally.
    window.STORYPLEX_ASSET_VERSION = (session.updated_at || '').replace(/\D/g, '');

    // Initialize the game bridge (our custom VN engine instead of raw Monogatari)
    gameBridge.init({
      sessionId,
      container: container.querySelector('#game-canvas'),
      characters,
      scenes,
      script,
      session,
    });

    gameBridge.start();
  } catch (err) {
    container.querySelector('#game-container').innerHTML = `
      <div class="error-message">
        <p>Failed to load game: ${err.message}</p>
        <button class="btn btn-primary" onclick="location.reload()">Retry</button>
      </div>
    `;
  }
}
