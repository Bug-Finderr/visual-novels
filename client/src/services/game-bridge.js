import { api } from './api.js';
import { AnimatedSprite } from './animated-sprite.js';
import { audioCue } from './audio-cue.js';

/** Map of script-string → audio file name (".wav"), loaded once per session. */
let _voiceManifest = null;
async function loadVoiceManifest(sessionId) {
  if (_voiceManifest && _voiceManifest.__sid === sessionId) return _voiceManifest;
  try {
    const res = await fetch(`/game-assets/${sessionId}/audio/manifest.json`);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const m = await res.json();
    _voiceManifest = Object.assign({}, m, { __sid: sessionId });
  } catch {
    _voiceManifest = { __sid: sessionId };
  }
  return _voiceManifest;
}

/**
 * Game bridge: plays Monogatari-format scripts using a custom lightweight renderer.
 * Drives AnimatedSprite per character (idle breathing, blink, mouth-flap during dialogue),
 * speaker focus (others desaturate/shrink), smarter typewriter (punctuation pauses),
 * and audio cues for advance/choice/scene change.
 */
class GameBridge {
  constructor() {
    this.sessionId = null;
    this.container = null;
    this.characters = {};
    this.scenes = {};
    this.script = {};
    this.session = null;

    this.currentLabel = 'Start';
    this.statementIndex = 0;
    this.isWaiting = false;

    /** charId -> AnimatedSprite */
    this.sprites = {};
    this.currentSpeakerId = null;

    this._typewriterGen = 0;
    this._isTyping = false;
    this._pendingText = '';
    this._currentSceneId = null;

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

    this._voiceAudio = null; // currently playing HTMLAudioElement
    this._audioPrimed = false;
    loadVoiceManifest(sessionId);

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

    this.dialogueBox.addEventListener('click', () => this.advance());
    document.addEventListener('keydown', (e) => {
      if (e.key === ' ' || e.key === 'Enter') {
        // don't intercept text input
        if (document.activeElement === this.freeInputText) return;
        if (!this.isWaiting) { e.preventDefault(); this.advance(); }
      }
    });

    container.querySelector('#free-input-send').addEventListener('click', () => this._sendFreeInput());
    this.freeInputText.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._sendFreeInput();
    });
  }

  start() {
    // Show a "Click to begin" overlay first so the very first audio.play()
    // happens inside a real user gesture (browser autoplay policy).
    this._showStartGate();
  }

  _showStartGate() {
    const gate = document.createElement('div');
    gate.className = 'start-gate';
    gate.innerHTML = `
      <div class="start-gate-card">
        <div class="start-gate-title">${this.session?.title || 'Begin'}</div>
        <div class="start-gate-hint">Click anywhere to start. Voices will play in Japanese.</div>
        <button class="btn btn-primary btn-lg start-gate-btn">Begin</button>
      </div>`;
    this.container.appendChild(gate);
    const begin = () => {
      this._primeAudio();
      gate.classList.add('fade-out');
      setTimeout(() => gate.remove(), 350);
      this.currentLabel = 'Start';
      this.statementIndex = 0;
      this.executeNext();
    };
    gate.addEventListener('click', begin, { once: true });
  }

  _primeAudio() {
    if (this._audioPrimed) return;
    // Play a near-silent 1-frame WAV inside the click handler. After this,
    // subsequent .play() calls are allowed in this tab without further gestures.
    try {
      const a = new Audio('data:audio/wav;base64,UklGRhwAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=');
      a.volume = 0.0001;
      a.play().catch(() => {});
    } catch { /* ignore */ }
    this._audioPrimed = true;
  }

  advance() {
    if (this.isWaiting) return;

    // If text is still typing, complete it instantly instead of advancing.
    // Also stop any in-flight voice playback so the user can move on.
    if (this._isTyping) {
      this._typewriterGen++;
      this._isTyping = false;
      this.textEl.textContent = this._pendingText;
      this._stopVoice();
      this._setSpeakerTalking(false);
      this.advanceEl.style.display = 'block';
      return;
    }

    audioCue.click();
    this._stopVoice();
    this.statementIndex++;
    this.executeNext();
  }

  _stopVoice() {
    if (this._voiceAudio) {
      try { this._voiceAudio.pause(); } catch { /* ignore */ }
      this._voiceAudio = null;
    }
  }

  async _playVoiceFor(scriptString) {
    this._stopVoice();
    const manifest = await loadVoiceManifest(this.sessionId);
    const file = manifest && manifest[scriptString];
    if (!file) return;
    const url = `/game-assets/${this.sessionId}/audio/${file}`;
    const audio = new Audio(url);
    audio.preload = 'auto';
    this._voiceAudio = audio;
    audio.addEventListener('ended', () => {
      if (this._voiceAudio === audio) this._voiceAudio = null;
      // mouth-flap stops via _setSpeakerTalking(false) in typewriter completion
    });
    audio.play().catch((err) => {
      // Autoplay policy or load failure — skip silently
      console.debug('voice play blocked:', err?.message);
      if (this._voiceAudio === audio) this._voiceAudio = null;
    });
  }

  executeNext() {
    const label = this.script[this.currentLabel];
    if (!label || this.statementIndex >= label.length) return;

    const stmt = label[this.statementIndex];
    if (typeof stmt === 'string') {
      this._executeStringStatement(stmt);
    } else if (typeof stmt === 'object' && stmt !== null) {
      if (stmt.Choice) this._showChoices(stmt.Choice);
      else this.advance();
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
      const labelName = stmt.replace('jump ', '');
      this.currentLabel = labelName;
      this.statementIndex = 0;
      this.executeNext();
    } else {
      this._showDialogue(stmt);
    }
  }

  _showScene(stmt) {
    const parts = stmt.split(' ');
    const sceneId = parts[2];
    if (sceneId === this._currentSceneId) return;
    this._currentSceneId = sceneId;
    const url = `/game-assets/${this.sessionId}/backgrounds/${sceneId}.png`;
    // Crossfade by toggling a class — CSS handles the transition
    this.bgEl.style.backgroundImage = `url('${url}')`;
    this.bgEl.classList.remove('ken-burns'); // reset animation so it restarts
    void this.bgEl.offsetWidth;
    this.bgEl.classList.add('ken-burns', 'fade-in');
    setTimeout(() => this.bgEl.classList.remove('fade-in'), 600);
    audioCue.sceneIn();
  }

  _showCharacter(stmt) {
    // "show character charId expression at position with animation"
    const match = stmt.match(/show character (\w+)\s+(\w+)\s+at\s+(\w+)/);
    if (!match) return;
    const [, charId, expression, position] = match;
    const character = this.characters[charId];
    if (!character) return;

    // Reuse if already on screen — just update position/expression
    if (this.sprites[charId]) {
      this.sprites[charId].setPosition(position);
      this.sprites[charId].setExpression(expression);
      return;
    }

    const sprite = new AnimatedSprite({
      sessionId: this.sessionId,
      characterId: charId,
      name: character.name,
      color: character.color,
      position,
    });
    sprite.mount(this.charsEl);
    sprite.setExpression(expression);
    this.sprites[charId] = sprite;
  }

  _hideCharacter(stmt) {
    const match = stmt.match(/hide character (\w+)/);
    if (!match) return;
    const charId = match[1];
    const sprite = this.sprites[charId];
    if (sprite) {
      sprite.destroy();
      delete this.sprites[charId];
      if (this.currentSpeakerId === charId) this.currentSpeakerId = null;
    }
  }

  _showDialogue(stmt) {
    const dialogueMatch = stmt.match(/^(\w+):(\w+)\s+(.+)$/);
    this.dialogueBox.style.display = 'block';
    this.dialogueBox.classList.add('dialogue-active');
    this.interactionPanel.style.display = 'none';

    if (dialogueMatch) {
      const [, charId, expression, text] = dialogueMatch;
      const character = this.characters[charId];

      // Special case: when the AI marks the protagonist as the speaker (e.g.
      // "aiko_player:..." or "<protagonist_name>_player:..."), use the
      // configured protagonist name instead of the raw id.
      const protagonistName = this.session?.setup_protagonist_name;
      const isProtagonist = !character && protagonistName && (
        charId === 'player' || /_player$/i.test(charId) ||
        charId.toLowerCase() === protagonistName.toLowerCase()
      );

      this.speakerEl.textContent = character
        ? character.name
        : (isProtagonist ? protagonistName : charId);
      this.speakerEl.style.color = character ? character.color : '#c4b5fd';
      this.speakerEl.style.display = 'block';

      this._setActiveSpeaker(charId);
      const sprite = this.sprites[charId];
      if (sprite) sprite.setExpression(expression);

      this._playVoiceFor(stmt);
      this._typeText(text, /* speaker */ charId);
    } else {
      this.speakerEl.style.display = 'none';
      this._setActiveSpeaker(null);
      this._playVoiceFor(stmt);
      this._typeText(stmt, null);
    }
  }

  _setActiveSpeaker(charId) {
    if (this.currentSpeakerId === charId) return;
    this.currentSpeakerId = charId;
    for (const [id, sprite] of Object.entries(this.sprites)) {
      sprite.setSpeaker(id === charId);
    }
  }

  _setSpeakerTalking(isTalking) {
    if (!this.currentSpeakerId) return;
    const sprite = this.sprites[this.currentSpeakerId];
    if (sprite) sprite.setTalking(isTalking);
  }

  _punctuationPause(ch) {
    if (ch === '.' || ch === '!' || ch === '?') return 220;
    if (ch === ',' || ch === ';' || ch === ':') return 110;
    return 0;
  }

  _typeText(text) {
    this._typewriterGen++;
    const gen = this._typewriterGen;

    this.textEl.textContent = '';
    this.advanceEl.style.display = 'none';
    this.isWaiting = false;
    this._isTyping = true;
    this._pendingText = text;
    this._setSpeakerTalking(true);

    let i = 0;
    const baseSpeed = 22;
    const type = () => {
      if (gen !== this._typewriterGen) return;
      if (i < text.length) {
        const ch = text[i];
        this.textEl.textContent += ch;
        i++;
        const extra = this._punctuationPause(ch);
        setTimeout(type, baseSpeed + extra);
      } else {
        this._isTyping = false;
        this._setSpeakerTalking(false);
        this.advanceEl.style.display = 'block';
      }
    };
    type();
  }

  _showChoices(choiceObj) {
    this.isWaiting = true;
    this.dialogueBox.classList.remove('dialogue-active');
    this.dialogueBox.style.display = 'none';
    this.interactionPanel.style.display = 'flex';
    this.choicesPanel.style.display = 'flex';
    this.freeInputPanel.style.display = 'flex';

    this.choicesPanel.innerHTML = '';

    const entries = Object.entries(choiceObj);
    entries.forEach(([key, choice], idx) => {
      const btn = document.createElement('button');
      btn.className = 'choice-btn choice-card';
      btn.style.animationDelay = `${idx * 60}ms`;
      btn.innerHTML = `
        <span class="choice-text">${choice.Text}</span>
        ${choice._consequence ? `<span class="choice-hint">${choice._consequence}</span>` : ''}
      `;
      btn.addEventListener('mouseenter', () => audioCue.hover());
      btn.addEventListener('click', () => this._handleChoice(key, choice));
      this.choicesPanel.appendChild(btn);
    });
  }

  async _handleChoice(key, choice) {
    audioCue.select();
    this.isWaiting = true;
    this.interactionPanel.style.display = 'none';
    this.loadingOverlay.style.display = 'flex';

    try {
      const result = await api.post(`/sessions/${this.sessionId}/choice`, {
        text: choice.Text,
        consequence: choice._consequence || '',
      });
      this._injectAndPlay(result);
    } catch (err) {
      console.error('Choice handling error:', err);
      this.loadingOverlay.style.display = 'none';
      this._showDialogue(`Something went wrong: ${err.message}`);
    }
  }

  async _sendFreeInput() {
    const text = this.freeInputText.value.trim();
    if (!text) return;
    audioCue.select();

    this.isWaiting = true;
    this.interactionPanel.style.display = 'none';
    this.loadingOverlay.style.display = 'flex';
    this.freeInputText.value = '';

    try {
      const result = await api.post(`/sessions/${this.sessionId}/free-input`, { text });
      this._injectAndPlay(result);
    } catch (err) {
      console.error('Free input error:', err);
      this.loadingOverlay.style.display = 'none';
      this._showDialogue(`Something went wrong: ${err.message}`);
    }
  }

  _injectAndPlay(result) {
    this.loadingOverlay.style.display = 'none';
    this.isWaiting = false;

    if (result.newCharacter) {
      this.characters[result.newCharacter.id] = { ...result.newCharacter, quirks: [] };
    }
    if (result.newScene) {
      this.scenes[result.newScene.id] = result.newScene;
    }

    this.script[result.newLabel] = result.statements;
    if (result.extraLabels) Object.assign(this.script, result.extraLabels);

    // Merge any runtime-generated audio entries into the in-memory manifest
    if (result.audioManifest && _voiceManifest) {
      Object.assign(_voiceManifest, result.audioManifest);
    }

    this.currentLabel = result.newLabel;
    this.statementIndex = 0;
    this.executeNext();
  }
}

export const gameBridge = new GameBridge();
