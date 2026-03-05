import { api } from './api.js';

/**
 * Game bridge: plays Monogatari-format scripts using a custom lightweight renderer.
 * Handles character display, scene backgrounds, dialogue, choices, and free input.
 * Communicates with the backend for AI-driven continuation.
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
    this.displayedCharacters = {};

    // Typewriter state
    this._typewriterGen = 0; // generation counter to cancel stale callbacks
    this._isTyping = false;
    this._pendingText = '';

    // DOM elements (set in init)
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

    // Build character lookup
    this.characters = {};
    for (const c of characters) {
      this.characters[c.id] = c;
    }

    // Build scene lookup
    this.scenes = {};
    for (const s of scenes) {
      this.scenes[s.id] = s;
    }

    // Grab DOM elements
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

    // Click to advance dialogue
    this.dialogueBox.addEventListener('click', () => this.advance());
    document.addEventListener('keydown', (e) => {
      if (e.key === ' ' || e.key === 'Enter') {
        if (!this.isWaiting) this.advance();
      }
    });

    // Free input send
    container.querySelector('#free-input-send').addEventListener('click', () => this._sendFreeInput());
    this.freeInputText.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._sendFreeInput();
    });
  }

  start() {
    this.currentLabel = 'Start';
    this.statementIndex = 0;
    this.executeNext();
  }

  advance() {
    if (this.isWaiting) return;

    // If text is still typing, complete it instantly instead of advancing
    if (this._isTyping) {
      this._typewriterGen++; // cancel pending setTimeout callbacks
      this._isTyping = false;
      this.textEl.textContent = this._pendingText;
      this.advanceEl.style.display = 'block';
      return;
    }

    this.statementIndex++;
    this.executeNext();
  }

  executeNext() {
    const label = this.script[this.currentLabel];
    if (!label || this.statementIndex >= label.length) {
      // End of current label
      return;
    }

    const stmt = label[this.statementIndex];

    if (typeof stmt === 'string') {
      this._executeStringStatement(stmt);
    } else if (typeof stmt === 'object' && stmt !== null) {
      if (stmt.Choice) {
        this._showChoices(stmt.Choice);
      } else {
        // Unknown object — skip
        this.advance();
      }
    }
  }

  _executeStringStatement(stmt) {
    // Parse the statement
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
      // Try parsing as dialogue or narration
      this._showDialogue(stmt);
    }
  }

  _showScene(stmt) {
    // "show scene sceneId with fadeIn"
    const parts = stmt.split(' ');
    const sceneId = parts[2];
    const scene = this.scenes[sceneId];
    const url = `/game-assets/${this.sessionId}/backgrounds/${sceneId}.png`;

    this.bgEl.style.backgroundImage = `url('${url}')`;
    this.bgEl.classList.add('fade-in');
    setTimeout(() => this.bgEl.classList.remove('fade-in'), 500);
  }

  _showCharacter(stmt) {
    // "show character charId expression at position with animation"
    const match = stmt.match(/show character (\w+)\s+(\w+)\s+at\s+(\w+)/);
    if (!match) return;

    const [, charId, expression, position] = match;
    const character = this.characters[charId];
    if (!character) return;

    const url = `/game-assets/${this.sessionId}/characters/${charId}/${expression}.png`;

    // Remove existing display if character is already shown
    const existing = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.className = `character-sprite position-${position} fade-in`;
    el.dataset.charId = charId;
    el.innerHTML = `<img src="${url}" alt="${character.name}" />`;
    this.charsEl.appendChild(el);

    this.displayedCharacters[charId] = { expression, position };
  }

  _hideCharacter(stmt) {
    // "hide character charId with fadeOut"
    const match = stmt.match(/hide character (\w+)/);
    if (!match) return;
    const charId = match[1];
    const el = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (el) {
      el.classList.add('fade-out');
      setTimeout(() => el.remove(), 400);
    }
    delete this.displayedCharacters[charId];
  }

  _showDialogue(stmt) {
    // Check if it's character dialogue: "charId:expression text"
    const dialogueMatch = stmt.match(/^(\w+):(\w+)\s+(.+)$/);

    this.dialogueBox.style.display = 'block';
    this.interactionPanel.style.display = 'none';

    if (dialogueMatch) {
      const [, charId, expression, text] = dialogueMatch;
      const character = this.characters[charId];

      this.speakerEl.textContent = character ? character.name : charId;
      this.speakerEl.style.color = character ? character.color : '#fff';
      this.speakerEl.style.display = 'block';

      // Update character sprite expression
      this._updateCharacterExpression(charId, expression);

      this._typeText(text);
    } else {
      // Narration
      this.speakerEl.style.display = 'none';
      this._typeText(stmt);
    }
  }

  _updateCharacterExpression(charId, expression) {
    const el = this.charsEl.querySelector(`[data-char-id="${charId}"]`);
    if (el) {
      const img = el.querySelector('img');
      const url = `/game-assets/${this.sessionId}/characters/${charId}/${expression}.png`;
      img.src = url;
    }
  }

  _typeText(text) {
    this._typewriterGen++; // invalidate any previous typewriter
    const gen = this._typewriterGen;

    this.textEl.textContent = '';
    this.advanceEl.style.display = 'none';
    this.isWaiting = false;
    this._isTyping = true;
    this._pendingText = text;

    let i = 0;
    const speed = 25;
    const type = () => {
      if (gen !== this._typewriterGen) return; // stale — abort
      if (i < text.length) {
        this.textEl.textContent += text[i];
        i++;
        setTimeout(type, speed);
      } else {
        this._isTyping = false;
        this.advanceEl.style.display = 'block';
      }
    };
    type();
  }

  _showChoices(choiceObj) {
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
      btn.addEventListener('click', () => this._handleChoice(key, choice));
      this.choicesPanel.appendChild(btn);
    }
  }

  async _handleChoice(key, choice) {
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

    // Register new character if introduced
    if (result.newCharacter) {
      this.characters[result.newCharacter.id] = {
        ...result.newCharacter,
        quirks: [],
      };
    }

    // Register new scene if introduced
    if (result.newScene) {
      this.scenes[result.newScene.id] = result.newScene;
    }

    // Inject all new labels into the script
    this.script[result.newLabel] = result.statements;
    if (result.extraLabels) {
      Object.assign(this.script, result.extraLabels);
    }

    // Jump to the new label
    this.currentLabel = result.newLabel;
    this.statementIndex = 0;
    this.executeNext();
  }
}

export const gameBridge = new GameBridge();
