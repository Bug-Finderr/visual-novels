import { api } from './api.js';
import { loadPrefs, speedMs } from '../utils/prefs.js';

/**
 * Custom visual-novel renderer. Plays Monogatari-style scripts produced by the server.
 * Supports resume (persists current_label + statement_index), sprite position tracking,
 * and optional "fast-forward" replay when restoring a saved position.
 */
class GameBridge {
  constructor() {
    this.sessionId = null;
    this.container = null;
    this.characters = {};
    this.scenes = {};
    this.script = {};
    this.session = null;

    // Playback state
    this.currentLabel = 'Start';
    this.statementIndex = 0;
    this.isWaiting = false;
    this.isReplaying = false;

    // Position tracking: position -> charId
    this.positionOccupancy = {};

    // Typewriter state
    this._typewriterGen = 0;
    this._isTyping = false;
    this._pendingText = '';

    // DOM
    this.bgEl = null;
    this.charsEl = null;
    this.dialogueBox = null;
    this.speakerEl = null;
    this.textEl = null;
    this.advanceEl = null;
    this.interactionPanel = null;
    this.choicesPanel = null;
    this.freeInputPanel = null;
    this.freeInputText = null;
    this.loadingOverlay = null;

    // Cleanup handles
    this._keydownHandler = null;
    this._boundHandlers = [];

    // Position save debounce
    this._saveTimer = null;

    // Auto-advance timer
    this._autoAdvanceTimer = null;
    this.prefs = loadPrefs();
  }

  updatePrefs(newPrefs) {
    this.prefs = { ...this.prefs, ...newPrefs };
    if (!this.prefs.autoAdvance && this._autoAdvanceTimer) {
      clearTimeout(this._autoAdvanceTimer);
      this._autoAdvanceTimer = null;
    }
  }

  init({ sessionId, container, characters, scenes, script, session }) {
    this.sessionId = sessionId;
    this.container = container;
    this.session = session;
    this.script = script;

    this.characters = {};
    for (const c of characters) this.characters[c.id] = c;

    this.scenes = {};
    for (const s of scenes) this.scenes[s.id] = s;

    this.bgEl = container.querySelector('#scene-bg');
    this.charsEl = container.querySelector('#characters-layer');
    this.dialogueBox = container.querySelector('#dialogue-box');
    this.speakerEl = container.querySelector('#speaker-name');
    this.textEl = container.querySelector('#dialogue-text');
    this.advanceEl = container.querySelector('#dialogue-advance');
    this.interactionPanel = container.querySelector('#interaction-panel');
    this.choicesPanel = container.querySelector('#choices-panel');
    this.freeInputPanel = container.querySelector('#free-input-panel');
    this.freeInputText = container.querySelector('#free-input-text');
    this.loadingOverlay = container.querySelector('#loading-overlay');

    const advance = () => this.advance();
    this.dialogueBox.addEventListener('click', advance);
    this._boundHandlers.push(() => this.dialogueBox.removeEventListener('click', advance));

    this._keydownHandler = (e) => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
      if (e.key === ' ' || e.key === 'Enter') {
        if (!this.isWaiting) this.advance();
      }
    };
    document.addEventListener('keydown', this._keydownHandler);

    const sendInput = () => this._sendFreeInput();
    const sendBtn = container.querySelector('#free-input-send');
    sendBtn.addEventListener('click', sendInput);
    this._boundHandlers.push(() => sendBtn.removeEventListener('click', sendInput));

    const inputKey = (e) => { if (e.key === 'Enter') { e.preventDefault(); this._sendFreeInput(); } };
    this.freeInputText.addEventListener('keydown', inputKey);
    this._boundHandlers.push(() => this.freeInputText.removeEventListener('keydown', inputKey));
  }

  destroy() {
    if (this._keydownHandler) {
      document.removeEventListener('keydown', this._keydownHandler);
      this._keydownHandler = null;
    }
    for (const off of this._boundHandlers) {
      try { off(); } catch {}
    }
    this._boundHandlers = [];
    this._typewriterGen++;
    this._isTyping = false;
    if (this._saveTimer) { clearTimeout(this._saveTimer); this._saveTimer = null; }
    if (this._autoAdvanceTimer) { clearTimeout(this._autoAdvanceTimer); this._autoAdvanceTimer = null; }
    this.sessionId = null;
  }

  start() {
    const savedLabel = (this.session && this.session.current_label) || 'Start';
    const savedIndex = (this.session && this.session.statement_index) || 0;

    if (savedLabel !== 'Start' || savedIndex > 0) {
      this._replayTo(savedLabel, savedIndex);
    } else {
      this.currentLabel = 'Start';
      this.statementIndex = 0;
      this.executeNext();
    }
  }

  _replayTo(label, index) {
    // Restore persistent scene background — session.current_scene_id is authoritative
    // because the active scene may have been set in a prior label.
    if (this.session && this.session.current_scene_id) {
      this._showScene(`show scene ${this.session.current_scene_id}`, { animate: false });
    }

    this.currentLabel = label;
    const statements = this.script[label] || [];
    const upTo = Math.min(index, statements.length);

    this.isReplaying = true;

    // First pass: apply explicit show/hide statements up to the save point.
    const dialogueRe = /^(\w+):(\w+)\s+(.+)$/;
    const lastDialogueByChar = new Map();
    for (let i = 0; i < upTo; i++) {
      const stmt = statements[i];
      if (typeof stmt !== 'string') continue;
      if (stmt.startsWith('show scene ')) this._showScene(stmt, { animate: false });
      else if (stmt.startsWith('show character ')) this._showCharacter(stmt, { animate: false });
      else if (stmt.startsWith('hide character ')) this._hideCharacter(stmt, { animate: false });
      else {
        const m = stmt.match(dialogueRe);
        if (m) lastDialogueByChar.set(m[1], m[2]);
      }
    }

    // Second pass: any speaker who appeared in dialogue but has no on-stage sprite
    // (because the show_character was in a prior label) gets auto-shown at center.
    for (const [charId, expression] of lastDialogueByChar.entries()) {
      if (!this.characters[charId]) continue;
      if (this.charsEl.querySelector(`[data-char-id="${charId}"]`)) continue;
      this._showCharacter(`show character ${charId} ${expression} at center`, { animate: false });
    }

    this.isReplaying = false;
    this.statementIndex = upTo;
    this.executeNext();
  }

  advance() {
    if (this.isWaiting) return;

    if (this._isTyping) {
      this._typewriterGen++;
      this._isTyping = false;
      this.textEl.textContent = this._pendingText;
      this.advanceEl.style.display = 'block';
      return;
    }

    this.statementIndex++;
    this._savePosition();
    this.executeNext();
  }

  executeNext() {
    const label = this.script[this.currentLabel];
    if (!label || this.statementIndex >= label.length) return;

    const stmt = label[this.statementIndex];

    if (typeof stmt === 'string') {
      this._executeStringStatement(stmt);
    } else if (typeof stmt === 'object' && stmt !== null) {
      if (stmt.Choice) {
        this._showChoices(stmt.Choice);
      } else {
        this.advance();
      }
    }
  }

  _executeStringStatement(stmt) {
    if (stmt.startsWith('show scene ')) {
      this._showScene(stmt);
      this.advance();
    } else if (stmt.startsWith('show character ')) {
      this._showCharacter(stmt);
      this.advance();
    } else if (stmt.startsWith('hide character ')) {
      this._hideCharacter(stmt);
      this.advance();
    } else if (stmt.startsWith('jump ')) {
      const labelName = stmt.replace('jump ', '').trim();
      this.currentLabel = labelName;
      this.statementIndex = 0;
      this._savePosition();
      this.executeNext();
    } else {
      this._showDialogue(stmt);
    }
  }

  _showScene(stmt, { animate = true } = {}) {
    const parts = stmt.split(' ');
    const sceneId = parts[2];
    const url = `/game-assets/${this.sessionId}/backgrounds/${sceneId}.png`;
    this.bgEl.style.backgroundImage = `url('${url}')`;
    if (animate) {
      this.bgEl.classList.add('fade-in');
      setTimeout(() => this.bgEl.classList.remove('fade-in'), 500);
    }
  }

  _showCharacter(stmt, { animate = true } = {}) {
    const match = stmt.match(/show character (\w+)\s+(\w+)\s+at\s+(\w+)/);
    if (!match) return;

    const [, charId, expression, position] = match;
    const character = this.characters[charId];
    if (!character) return;

    const url = `/game-assets/${this.sessionId}/characters/${charId}/${expression}.png`;

    // Remove any existing sprite for this charId (switching position)
    const existing = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (existing) {
      const prevPos = existing.dataset.position;
      if (prevPos && this.positionOccupancy[prevPos] === charId) {
        delete this.positionOccupancy[prevPos];
      }
      existing.remove();
    }

    // If another character already holds this position, evict them
    const incumbent = this.positionOccupancy[position];
    if (incumbent && incumbent !== charId) {
      const incumbentEl = this.charsEl.querySelector(`[data-char-id="${incumbent}"]`);
      if (incumbentEl) incumbentEl.remove();
      delete this.positionOccupancy[incumbent];
    }

    const el = document.createElement('div');
    el.className = `character-sprite position-${position}${animate ? ' fade-in' : ''}`;
    el.dataset.charId = charId;
    el.dataset.position = position;

    const img = document.createElement('img');
    img.src = url;
    img.alt = character.name; // character.name already validated server-side; set as property, not html
    el.appendChild(img);

    this.charsEl.appendChild(el);
    this.positionOccupancy[position] = charId;
  }

  _hideCharacter(stmt, { animate = true } = {}) {
    const match = stmt.match(/hide character (\w+)/);
    if (!match) return;
    const charId = match[1];
    const el = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (!el) return;
    const pos = el.dataset.position;
    if (pos && this.positionOccupancy[pos] === charId) delete this.positionOccupancy[pos];
    if (animate) {
      el.classList.add('fade-out');
      setTimeout(() => el.remove(), 400);
    } else {
      el.remove();
    }
  }

  _showDialogue(stmt) {
    const dialogueMatch = stmt.match(/^(\w+):(\w+)\s+(.+)$/);

    this.dialogueBox.style.display = 'block';
    this.interactionPanel.style.display = 'none';

    if (dialogueMatch) {
      const [, charId, expression, text] = dialogueMatch;
      const character = this.characters[charId];

      this.speakerEl.textContent = character ? character.name : charId;
      this.speakerEl.style.color = this._safeColor(character ? character.color : null);
      this.speakerEl.style.display = 'block';

      // If this speaker isn't on-stage (e.g., AI forgot to emit show_character, or
      // we resumed mid-label where the prior show_character was in a previous label),
      // auto-show them at center so the player sees who is talking.
      if (character && !this.charsEl.querySelector(`[data-char-id="${charId}"]`)) {
        this._showCharacter(
          `show character ${charId} ${expression} at center`,
          { animate: !this.isReplaying }
        );
      } else {
        this._updateCharacterExpression(charId, expression);
      }
      this._recordPlayed({
        kind: 'dialogue',
        speakerId: charId,
        speaker: character ? character.name : charId,
        text,
      });
      this._typeText(text);
    } else {
      this.speakerEl.style.display = 'none';
      this._recordPlayed({ kind: 'narration', text: stmt });
      this._typeText(stmt);
    }
  }

  _safeColor(color) {
    if (typeof color === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(color)) return color;
    return '#ffffff';
  }

  _updateCharacterExpression(charId, expression) {
    const el = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (el) {
      const img = el.querySelector('img');
      img.src = `/game-assets/${this.sessionId}/characters/${charId}/${expression}.png`;
    }
  }

  _typeText(text) {
    this._typewriterGen++;
    const gen = this._typewriterGen;

    if (this._autoAdvanceTimer) { clearTimeout(this._autoAdvanceTimer); this._autoAdvanceTimer = null; }
    this.textEl.textContent = '';
    this.advanceEl.style.display = 'none';
    this.isWaiting = false;
    this._isTyping = true;
    this._pendingText = text;

    const speed = speedMs(this.prefs.typewriterSpeed);
    if (speed === 0) {
      this.textEl.textContent = text;
      this._isTyping = false;
      this.advanceEl.style.display = 'block';
      this._scheduleAutoAdvance();
      return;
    }

    let i = 0;
    const type = () => {
      if (gen !== this._typewriterGen) return;
      if (i < text.length) {
        this.textEl.textContent += text[i];
        i++;
        setTimeout(type, speed);
      } else {
        this._isTyping = false;
        this.advanceEl.style.display = 'block';
        this._scheduleAutoAdvance();
      }
    };
    type();
  }

  _scheduleAutoAdvance() {
    if (!this.prefs.autoAdvance || this.isWaiting) return;
    if (this._autoAdvanceTimer) clearTimeout(this._autoAdvanceTimer);
    this._autoAdvanceTimer = setTimeout(() => {
      this._autoAdvanceTimer = null;
      if (!this.isWaiting && !this._isTyping) this.advance();
    }, Math.max(400, this.prefs.autoAdvanceDelayMs || 1400));
  }

  _showChoices(choiceObj) {
    if (this._autoAdvanceTimer) { clearTimeout(this._autoAdvanceTimer); this._autoAdvanceTimer = null; }
    this.isWaiting = true;
    this.dialogueBox.style.display = 'none';
    this.interactionPanel.style.display = 'flex';
    this.choicesPanel.style.display = 'flex';
    this.freeInputPanel.style.display = 'flex';

    this.choicesPanel.innerHTML = '';

    for (const [key, choice] of Object.entries(choiceObj)) {
      const btn = document.createElement('button');
      btn.className = 'choice-btn';
      btn.textContent = choice.Text;
      btn.addEventListener('click', () => this._handleChoice(key, choice), { once: true });
      this.choicesPanel.appendChild(btn);
    }
  }

  async _handleChoice(key, choice) {
    this.isWaiting = true;
    this.interactionPanel.style.display = 'none';
    this.loadingOverlay.style.display = 'flex';

    this._recordPlayed({ kind: 'player_choice', text: choice.Text });

    try {
      const result = await api.post(`/sessions/${this.sessionId}/choice`, {
        text: choice.Text,
        consequence: choice._consequence || '',
      });
      this._injectAndPlay(result);
    } catch (err) {
      console.error('Choice handling error:', err);
      this.loadingOverlay.style.display = 'none';
      this.isWaiting = false;
      this._showDialogueText(`Something went wrong: ${err.message}`);
    }
  }

  async _sendFreeInput() {
    if (this.isWaiting) return;
    const text = this.freeInputText.value.trim();
    if (!text) return;

    this.isWaiting = true;
    this.interactionPanel.style.display = 'none';
    this.loadingOverlay.style.display = 'flex';
    this.freeInputText.value = '';

    this._recordPlayed({ kind: 'player_input', text });

    try {
      const result = await api.post(`/sessions/${this.sessionId}/free-input`, { text });
      this._injectAndPlay(result);
    } catch (err) {
      console.error('Free input error:', err);
      this.loadingOverlay.style.display = 'none';
      this.isWaiting = false;
      this._showDialogueText(`Something went wrong: ${err.message}`);
    }
  }

  _showDialogueText(text) {
    this.dialogueBox.style.display = 'block';
    this.speakerEl.style.display = 'none';
    this._typeText(text);
  }

  _injectAndPlay(result) {
    this.loadingOverlay.style.display = 'none';
    this.isWaiting = false;

    if (result.newCharacter) {
      this.characters[result.newCharacter.id] = {
        ...result.newCharacter,
        quirks: [],
      };
    }
    if (result.newScene) {
      this.scenes[result.newScene.id] = result.newScene;
    }

    this.script[result.newLabel] = result.statements;
    if (result.extraLabels) Object.assign(this.script, result.extraLabels);

    this.currentLabel = result.newLabel;
    this.statementIndex = 0;
    this._savePosition();
    this.executeNext();
  }

  _savePosition() {
    if (this.isReplaying || !this.sessionId) return;
    if (this._saveTimer) clearTimeout(this._saveTimer);
    const label = this.currentLabel;
    const index = this.statementIndex;
    const sid = this.sessionId;
    this._saveTimer = setTimeout(() => {
      api.post(`/sessions/${sid}/position`, { label, index }).catch((err) => {
        console.warn('Failed to save position:', err.message);
      });
    }, 600);
  }

  _recordPlayed(entry) {
    if (this.isReplaying || !this.sessionId) return;
    const sid = this.sessionId;
    api.post(`/sessions/${sid}/played`, {
      ...entry,
      labelName: this.currentLabel,
    }).catch(() => {});
  }
}

export const gameBridge = new GameBridge();
