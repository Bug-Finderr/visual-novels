import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

export function renderLoading(container, params) {
  const sessionId = params[0];
  if (!sessionId) {
    navigate('/');
    return;
  }

  container.innerHTML = `
    <div class="loading-view">
      <h2>Generating Your Story</h2>
      <p class="loading-subtitle">This may take a few minutes as we create your world, characters, and artwork.</p>

      <div class="progress-container">
        <div class="progress-bar">
          <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
        </div>
        <div class="progress-text" id="progress-text">Connecting...</div>
        <div class="progress-percent" id="progress-percent">0%</div>
      </div>

      <div class="progress-steps" id="progress-steps"></div>

      <div id="loading-actions" style="display:none;">
        <button class="btn btn-primary btn-lg" id="btn-start-game">Start Your Story</button>
      </div>

      <div id="loading-error" class="error-message" style="display:none;"></div>
    </div>
  `;

  const fillEl = container.querySelector('#progress-fill');
  const textEl = container.querySelector('#progress-text');
  const percentEl = container.querySelector('#progress-percent');
  const actionsEl = container.querySelector('#loading-actions');
  const errorEl = container.querySelector('#loading-error');

  const stepsLog = [];
  const stepsEl = container.querySelector('#progress-steps');

  function addStep(text) {
    if (stepsLog.length === 0 || stepsLog[stepsLog.length - 1] !== text) {
      stepsLog.push(text);
      stepsEl.innerHTML = stepsLog
        .map((s, i) => `<div class="step ${i === stepsLog.length - 1 ? 'step-active' : 'step-done'}">${s}</div>`)
        .join('');
      stepsEl.scrollTop = stepsEl.scrollHeight;
    }
  }

  // Connect to SSE for progress
  const source = api.sse(
    `/sessions/${sessionId}/generate/status`,
    (data) => {
      fillEl.style.width = `${data.progress}%`;
      percentEl.textContent = `${data.progress}%`;
      textEl.textContent = data.details;
      addStep(data.details);

      if (data.step === 'done') {
        actionsEl.style.display = 'block';
        source.close();
      }

      if (data.step === 'error') {
        errorEl.textContent = data.details;
        errorEl.style.display = 'block';
        source.close();
      }
    },
    () => {
      // SSE error — check session status
      api.get(`/sessions/${sessionId}`).then((session) => {
        if (session.status === 'ready') {
          fillEl.style.width = '100%';
          percentEl.textContent = '100%';
          textEl.textContent = 'Generation complete!';
          actionsEl.style.display = 'block';
        } else if (session.status === 'error') {
          errorEl.textContent = 'Generation failed. Try again.';
          errorEl.style.display = 'block';
        }
      });
    }
  );

  container.querySelector('#btn-start-game').addEventListener('click', () => {
    navigate(`/game/${sessionId}`);
  });
}
