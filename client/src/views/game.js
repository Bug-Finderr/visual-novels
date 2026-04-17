import { navigate, onRouteCleanup } from '../utils/router.js';
import { api } from '../services/api.js';
import { gameBridge } from '../services/game-bridge.js';
import { escapeHtml } from '../utils/escape.js';
import { loadPrefs, savePrefs } from '../utils/prefs.js';

export async function renderGame(container, params) {
  const sessionId = params[0];
  if (!sessionId) {
    navigate('/');
    return;
  }

  container.innerHTML = `
    <div class="game-view">
      <div class="game-header">
        <button class="btn btn-ghost" id="btn-back-to-menu">&larr; Menu</button>
        <button class="btn btn-ghost" id="btn-stories">Stories</button>
        <button class="btn btn-ghost" id="btn-history">History</button>
        <button class="btn btn-ghost" id="btn-restart" title="Restart this story from the beginning">Restart</button>
        <button class="btn btn-ghost" id="btn-settings" title="Playback settings (?)">Settings</button>
        <span class="game-title" id="game-title">Loading...</span>
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
            <p>Characters are responding...</p>
          </div>
        </div>
      </div>
      <div class="modal" id="history-modal" style="display:none;" aria-hidden="true">
        <div class="modal-backdrop"></div>
        <div class="modal-panel">
          <div class="modal-header">
            <h3>Story History</h3>
            <button class="btn btn-ghost" id="btn-history-close">Close</button>
          </div>
          <div class="modal-body" id="history-body">
            <p class="loading-text">Loading history...</p>
          </div>
        </div>
      </div>
      <div class="modal" id="settings-modal" style="display:none;" aria-hidden="true">
        <div class="modal-backdrop"></div>
        <div class="modal-panel">
          <div class="modal-header">
            <h3>Settings</h3>
            <button class="btn btn-ghost" id="btn-settings-close">Close</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="pref-speed">Text speed</label>
              <select id="pref-speed">
                <option value="slow">Slow</option>
                <option value="normal">Normal</option>
                <option value="fast">Fast</option>
                <option value="instant">Instant</option>
              </select>
            </div>
            <div class="form-group">
              <label class="radio-card" style="cursor:pointer;">
                <input type="checkbox" id="pref-auto-advance" />
                <span>Auto-advance dialogue</span>
              </label>
            </div>
            <div class="form-group">
              <label for="pref-delay">Auto-advance delay (ms)</label>
              <input type="number" id="pref-delay" min="400" max="10000" step="100" />
            </div>
            <div class="settings-hint">
              <strong>Keys:</strong> Space / Enter = advance · Esc = settings · ? = this hint
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-back-to-menu').addEventListener('click', () => navigate('/'));
  container.querySelector('#btn-stories').addEventListener('click', () => navigate('/sessions'));

  const historyModal = container.querySelector('#history-modal');
  const historyBody = container.querySelector('#history-body');
  container.querySelector('#btn-history').addEventListener('click', async () => {
    historyModal.style.display = 'flex';
    historyBody.innerHTML = '<p class="loading-text">Loading history...</p>';
    try {
      const rows = await api.get(`/sessions/${sessionId}/history`);
      if (!rows.length) {
        historyBody.innerHTML = '<p class="empty-text">No dialogue recorded yet — play a bit first.</p>';
        return;
      }
      historyBody.innerHTML = rows.map((r) => renderHistoryRow(r)).join('');
      historyBody.scrollTop = historyBody.scrollHeight;
    } catch (err) {
      historyBody.innerHTML = `<p class="error-message">${escapeHtml(err.message)}</p>`;
    }
  });
  container.querySelector('#btn-history-close').addEventListener('click', () => {
    historyModal.style.display = 'none';
  });
  historyModal.querySelector('.modal-backdrop').addEventListener('click', () => {
    historyModal.style.display = 'none';
  });

  // Settings modal
  const settingsModal = container.querySelector('#settings-modal');
  const prefSpeed = container.querySelector('#pref-speed');
  const prefAuto = container.querySelector('#pref-auto-advance');
  const prefDelay = container.querySelector('#pref-delay');
  const syncUi = () => {
    const p = loadPrefs();
    prefSpeed.value = p.typewriterSpeed;
    prefAuto.checked = !!p.autoAdvance;
    prefDelay.value = p.autoAdvanceDelayMs;
  };
  const writePrefs = () => {
    const p = {
      typewriterSpeed: prefSpeed.value,
      autoAdvance: prefAuto.checked,
      autoAdvanceDelayMs: Math.max(400, Math.min(10000, parseInt(prefDelay.value, 10) || 1400)),
    };
    savePrefs(p);
    gameBridge.updatePrefs(p);
  };
  container.querySelector('#btn-settings').addEventListener('click', () => {
    syncUi();
    settingsModal.style.display = 'flex';
  });
  container.querySelector('#btn-settings-close').addEventListener('click', () => {
    settingsModal.style.display = 'none';
  });
  settingsModal.querySelector('.modal-backdrop').addEventListener('click', () => {
    settingsModal.style.display = 'none';
  });
  prefSpeed.addEventListener('change', writePrefs);
  prefAuto.addEventListener('change', writePrefs);
  prefDelay.addEventListener('change', writePrefs);

  const keyHandler = (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 'Escape') {
      if (settingsModal.style.display === 'flex') settingsModal.style.display = 'none';
      else if (historyModal.style.display === 'flex') historyModal.style.display = 'none';
      else { syncUi(); settingsModal.style.display = 'flex'; }
    } else if (e.key === '?') {
      syncUi();
      settingsModal.style.display = 'flex';
    }
  };
  document.addEventListener('keydown', keyHandler);
  onRouteCleanup(() => document.removeEventListener('keydown', keyHandler));

  container.querySelector('#btn-restart').addEventListener('click', async () => {
    if (!confirm('Restart this story from the beginning? Your current position will be reset.')) return;
    try {
      await api.post(`/sessions/${sessionId}/position`, { label: 'Start', index: 0 });
      location.reload();
    } catch (err) {
      alert('Failed to restart: ' + err.message);
    }
  });

  try {
    const [session, characters, scenes, script] = await Promise.all([
      api.get(`/sessions/${sessionId}`),
      api.get(`/sessions/${sessionId}/characters`),
      api.get(`/sessions/${sessionId}/scenes`),
      api.get(`/sessions/${sessionId}/script`),
    ]);

    container.querySelector('#game-title').textContent = session.title;

    gameBridge.init({
      sessionId,
      container: container.querySelector('#game-canvas'),
      characters,
      scenes,
      script,
      session,
    });

    onRouteCleanup(() => gameBridge.destroy());

    gameBridge.start();
  } catch (err) {
    const msg = escapeHtml(err.message || 'Unknown error');
    container.querySelector('#game-container').innerHTML = `
      <div class="error-message">
        <p>Failed to load game: ${msg}</p>
        <button class="btn btn-primary" id="btn-retry">Retry</button>
      </div>
    `;
    container.querySelector('#btn-retry').addEventListener('click', () => location.reload());
  }
}

function renderHistoryRow(r) {
  const kind = r.kind;
  if (kind === 'dialogue') {
    return `<div class="history-row history-dialogue">
      <span class="history-speaker">${escapeHtml(r.speaker || r.speaker_id || 'Someone')}</span>
      <span class="history-text">${escapeHtml(r.text)}</span>
    </div>`;
  }
  if (kind === 'narration') {
    return `<div class="history-row history-narration"><em>${escapeHtml(r.text)}</em></div>`;
  }
  if (kind === 'player_choice') {
    return `<div class="history-row history-choice">&rarr; You chose: ${escapeHtml(r.text)}</div>`;
  }
  if (kind === 'player_input') {
    return `<div class="history-row history-input">&rarr; You said: ${escapeHtml(r.text)}</div>`;
  }
  return `<div class="history-row">${escapeHtml(r.text)}</div>`;
}
