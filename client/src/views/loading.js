import { navigate } from '../utils/router.js';
import { api } from '../services/api.js';

const EPIGRAPHS = [
  'In the beginning was the word…',
  'A story is the shortest distance between two souls.',
  'Every world is born from a single thought.',
  'Patience — the ink is still drying.',
];

export function renderLoading(container, params) {
  const sessionId = params[0];
  if (!sessionId) {
    navigate('/');
    return;
  }

  const epigraph = EPIGRAPHS[Math.floor(Math.random() * EPIGRAPHS.length)];

  container.innerHTML = `
    <div class="loading-view">
      <div class="loading-card">
        <div class="ornament">Weaving</div>
        <h1 class="display-title">Weaving your world</h1>
        <p class="loading-subtitle">&ldquo;${epigraph}&rdquo;</p>

        <div class="progress-container">
          <div class="progress-bar">
            <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
          </div>
          <div class="progress-meta">
            <span class="progress-text" id="progress-text">Connecting…</span>
            <span class="progress-percent" id="progress-percent">0</span>
          </div>
        </div>

        <div class="progress-steps" id="progress-steps"></div>

        <div id="loading-actions" style="display:none;">
          <button class="btn btn-primary btn-lg" id="btn-start-game">
            <span class="btn-icon">&#9656;</span> Begin the tale
          </button>
        </div>

        <div id="loading-error" class="error-message" style="display:none;"></div>
      </div>
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

  const source = api.sse(
    `/sessions/${sessionId}/generate/status`,
    (data) => {
      fillEl.style.width = `${data.progress}%`;
      percentEl.textContent = `${data.progress}`;
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
      api.get(`/sessions/${sessionId}`).then((session) => {
        if (session.status === 'ready') {
          fillEl.style.width = '100%';
          percentEl.textContent = '100';
          textEl.textContent = 'Generation complete.';
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
