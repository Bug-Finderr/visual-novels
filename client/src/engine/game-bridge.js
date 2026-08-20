import { api } from '../lib/api.js';
import { assetUrl } from '../lib/assets.js';
import { AnimatedSprite } from './animated-sprite.js';
import { audioCue } from './audio-cue.js';

// TTS WebSocket base. Dev: same host (Vite proxy). Prod: derive the wss host
// from VITE_API_BASE (Cloud Run) since Netlify can't proxy WebSockets.
function ttsWsUrl(sessionId) {
  const apiBase = import.meta.env.VITE_API_BASE;
  if (apiBase) {
    const u = new URL(apiBase);
    const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${u.host}/api/v1/sessions/${sessionId}/tts/stream`;
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/api/v1/sessions/${sessionId}/tts/stream`;
}

const TTS_SAMPLE_RATE = 24000;

// How many decoded lines to keep. A 24 kHz mono line is ~96 KB/second as
// Float32, so ~24 lines of typical length sits around 10-15 MB.
const VOICE_CACHE_MAX = 24;
// How far ahead to warm the cache while the current line plays.
const VOICE_PREFETCH = 3;

/**
 * Plays a line's voice, preferring the audio the generation pipeline already
 * rendered.
 *
 * Nearly every line HAS a pre-rendered WAV sitting in the public asset bucket
 * (see tts_generator's PHASE E), so the fast path just fetches that from the
 * CDN and decodes it — and upcoming lines are prefetched while the current one
 * plays, which usually makes playback start on the same frame as the text.
 *
 * The WebSocket streamer is kept ONLY as a fallback for lines with no
 * pre-rendered audio (live free-input, cache misses). It used to handle every
 * line, which meant each one paid a fresh TCP + TLS + WS handshake before its
 * first audio byte — routinely long enough that the typewriter finished first.
 * An AnalyserNode sits in the chain for both paths, so lip-sync is unchanged.
 */
class VoicePlayer {
  constructor(audioCtx, sessionId) {
    this.ctx = audioCtx;
    this.sessionId = sessionId;
    this._gain = audioCtx.createGain();
    this._gain.gain.value = 1;
    this.analyser = audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this._gain.connect(this.analyser);
    this.analyser.connect(audioCtx.destination);
    this._ws = null;
    this._sources = [];
    this._nextStart = 0;
    this._onDone = null;

    this._manifest = {};        // scriptString -> filename
    this._buffers = new Map();  // scriptString -> AudioBuffer (insertion-ordered)
    this._inflight = new Map(); // scriptString -> Promise
    // Guards against a slow fetch resolving after the player has moved on:
    // without it, advancing quickly could play the previous line's audio over
    // the current one.
    this._gen = 0;
  }

  setOnDone(cb) { this._onDone = cb; }

  /** Merge in {scriptString: filename} entries as new beats arrive. */
  mergeManifest(entries) {
    if (entries && typeof entries === 'object') Object.assign(this._manifest, entries);
  }

  hasCached(scriptString) {
    return Boolean(this._manifest[scriptString]);
  }

  /** Tear down the live stream + cancel any queued audio buffers. */
  stop() {
    this._gen++;
    if (this._ws) {
      try { this._ws.close(); } catch {}
      this._ws = null;
    }
    for (const s of this._sources) {
      try { s.stop(); } catch {}
    }
    this._sources = [];
    this._nextStart = this.ctx.currentTime;
  }

  /** Warm the decode cache for lines about to be displayed. */
  prefetch(scriptStrings) {
    for (const s of scriptStrings) {
      if (s && this._manifest[s] && !this._buffers.has(s)) this._load(s);
    }
  }

  _load(scriptString) {
    const cached = this._buffers.get(scriptString);
    if (cached) return Promise.resolve(cached);
    const pending = this._inflight.get(scriptString);
    if (pending) return pending;

    const file = this._manifest[scriptString];
    if (!file) return Promise.resolve(null);

    const task = (async () => {
      try {
        const res = await fetch(assetUrl(`${this.sessionId}/audio/${file}`));
        if (!res.ok) return null;
        const buf = await this.ctx.decodeAudioData(await res.arrayBuffer());
        this._buffers.set(scriptString, buf);
        // Map preserves insertion order, so the first key is the oldest.
        while (this._buffers.size > VOICE_CACHE_MAX) {
          this._buffers.delete(this._buffers.keys().next().value);
        }
        return buf;
      } catch {
        return null;   // fall back to streaming
      } finally {
        this._inflight.delete(scriptString);
      }
    })();
    this._inflight.set(scriptString, task);
    return task;
  }

  async play({ scriptString, text, characterId, expression }) {
    this.stop();
    const gen = this._gen;

    // Already decoded: starts this frame, in step with the first character.
    const ready = this._buffers.get(scriptString);
    if (ready) { this._playBuffer(ready, gen); return; }

    if (this._manifest[scriptString]) {
      const buf = await this._load(scriptString);
      if (gen !== this._gen) return;   // advanced past this line already
      if (buf) { this._playBuffer(buf, gen); return; }
    }

    if (gen !== this._gen) return;
    this._playStream({ scriptString, text, characterId, expression });
  }

  _playBuffer(buffer, gen) {
    if (gen !== this._gen) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this._gain);
    src.start();
    this._sources.push(src);
    src.onended = () => {
      this._sources = this._sources.filter((s) => s !== src);
      if (gen === this._gen && this._onDone) this._onDone();
    };
  }

  _playStream({ scriptString, text, characterId, expression }) {
    const url = ttsWsUrl(this.sessionId);
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.warn('voice ws open failed:', err);
      return;
    }
    ws.binaryType = 'arraybuffer';
    this._ws = ws;
    this._nextStart = this.ctx.currentTime;

    ws.onopen = () => {
      ws.send(JSON.stringify({ scriptString, text, characterId, expression }));
    };
    ws.onmessage = (evt) => {
      if (typeof evt.data === 'string') {
        try {
          const obj = JSON.parse(evt.data);
          if (obj.type === 'done') {
            if (this._onDone) this._onDone();
            // Server already closes from its side, but close eagerly here
            // too so the socket is released even if the server flush is
            // delayed. Stops the dialogue path from leaving sockets open
            // when the user advances through many lines quickly.
            try { ws.close(); } catch {}
          }
          if (obj.type === 'error') {
            console.warn('tts stream error:', obj.message);
            try { ws.close(); } catch {}
          }
        } catch { /* not JSON */ }
        return;
      }
      this._enqueuePCM(evt.data);
    };
    ws.onerror = (e) => console.debug('voice ws transport error', e);
    ws.onclose = () => {
      if (this._ws === ws) this._ws = null;
    };
  }

  _enqueuePCM(arrayBuffer) {
    // Int16 LE -> Float32 normalized [-1, 1]
    const i16 = new Int16Array(arrayBuffer);
    if (!i16.length) return;
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;

    const buf = this.ctx.createBuffer(1, f32.length, TTS_SAMPLE_RATE);
    buf.getChannelData(0).set(f32);

    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this._gain);

    const now = this.ctx.currentTime;
    const startAt = Math.max(now, this._nextStart);
    src.start(startAt);
    this._sources.push(src);
    src.onended = () => {
      this._sources = this._sources.filter((s) => s !== src);
    };
    this._nextStart = startAt + buf.duration;
  }
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

  init({ sessionId, container, characters, scenes, script, session, navigate }) {
    this.sessionId = sessionId;
    this.container = container;
    this.session = session;
    this.script = script;
    // Injected by the React host so the engine navigates through the app
    // router instead of mutating the URL hash directly.
    this._navigate = navigate || ((p) => { window.location.hash = p; });
    this._disposed = false;

    this.characters = {};
    for (const c of characters) this.characters[c.id] = c;
    this.scenes = {};
    for (const s of scenes) this.scenes[s.id] = s;

    // Voice player — plays the pipeline's pre-rendered audio from the CDN,
    // falling back to the per-line TTS WebSocket only when a line has none.
    // The AudioContext is created in the start-gate click handler (user
    // gesture) so playback is allowed by autoplay policy.
    this._audioCtx = null;
    this._audioPrimed = false;
    // Fetch the manifest now, while the player is still on the start gate —
    // by the time they click through, the first lines can play immediately.
    this._loadVoiceManifest();
    this._streamer = null;
    // {scriptString: filename} for lines the pipeline pre-rendered. Held here
    // as well as on the player because the manifest loads before the first
    // user gesture creates the AudioContext.
    this._voiceManifest = {};
    this._lipRaf = null;
    this._timeData = null;

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
    document.addEventListener('keydown', this._onGlobalKey = (e) => {
      // don't intercept text input
      if (document.activeElement === this.freeInputText) return;
      if (e.key === ' ' || e.key === 'Enter') {
        if (!this.isWaiting) { e.preventDefault(); this.advance(); }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        this.togglePauseMenu();
      }
    });

    container.querySelector('#free-input-send').addEventListener('click', () => this._sendFreeInput());
    this.freeInputText.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._sendFreeInput();
    });
  }

  start() {
    // Always start from 'Start'. A VN's opening label is the only one that
    // contains the scene + show_character commands needed to set up the
    // stage; resuming mid-story from a dynamic label would leave the screen
    // black because those commands never ran. (Proper save/resume needs to
    // replay the setup or snapshot scene + visible characters — future work.)
    this._showStartGate();
  }

  _showStartGate() {
    const gate = document.createElement('div');
    gate.className = 'start-gate';
    gate.innerHTML = `
      <div class="start-gate-card">
        <div class="start-gate-ornament">&mdash; &#10022; &mdash;</div>
        <div class="start-gate-title">${this.session?.title || 'Begin'}</div>
        <div class="start-gate-hint">Click to open the first page. Voices will play aloud.</div>
        <button class="btn btn-primary btn-lg start-gate-btn">
          <span class="btn-icon">&#9656;</span> Begin
        </button>
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
    // Create the AudioContext inside the user gesture so it starts unlocked.
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx && !this._audioCtx) this._audioCtx = new Ctx();
      this._audioCtx?.resume?.();
    } catch { /* WebAudio unavailable — procedural lip-sync still works */ }
    this._audioPrimed = true;
  }

  _ensureStreamer() {
    if (this._streamer) return true;
    if (!this._audioCtx) return false;
    try {
      this._streamer = new VoicePlayer(this._audioCtx, this.sessionId);
      this._streamer.mergeManifest(this._voiceManifest);
      this._streamer.setOnDone(() => this._stopLipSync());
      this._timeData = new Uint8Array(this._streamer.analyser.fftSize);
      return true;
    } catch (err) {
      console.warn('streamer init failed:', err);
      return false;
    }
  }

  _startLipSync() {
    if (!this._streamer) return;
    this._stopLipSync();
    const data = this._timeData;
    const analyser = this._streamer.analyser;
    const loop = () => {
      if (!this._streamer) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      const level = Math.min(1, rms * 3.4);   // quiet RMS → full open
      const sprite = this.sprites[this.currentSpeakerId];
      if (sprite) sprite.setMouthOpen(level);
      this._lipRaf = requestAnimationFrame(loop);
    };
    this._lipRaf = requestAnimationFrame(loop);
  }

  _stopLipSync() {
    if (this._lipRaf) { cancelAnimationFrame(this._lipRaf); this._lipRaf = null; }
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
    this._stopLipSync();
    if (this._streamer) this._streamer.stop();
  }

  /** Pull the session's pre-rendered audio index. Absent or unreachable just
   *  means every line falls back to the streaming path — the same behaviour as
   *  before this existed, only slower. */
  async _loadVoiceManifest() {
    try {
      const res = await fetch(assetUrl(`${this.sessionId}/audio/manifest.json`));
      if (!res.ok) return;
      this._mergeVoiceManifest(await res.json());
    } catch { /* streaming fallback covers it */ }
  }

  /** Merge manifest entries and warm the next few lines' audio. */
  _mergeVoiceManifest(entries) {
    if (!entries || typeof entries !== 'object') return;
    Object.assign(this._voiceManifest, entries);
    if (this._streamer) this._streamer.mergeManifest(entries);
  }

  /** Decode the next few lines while the current one plays, so their audio can
   *  start on the same frame as their first character rather than after a
   *  fetch. */
  _prefetchUpcomingVoices() {
    if (!this._streamer) return;
    const label = this.script[this.currentLabel];
    if (!Array.isArray(label)) return;
    const upcoming = [];
    for (let i = this.statementIndex; i < label.length && upcoming.length < VOICE_PREFETCH; i++) {
      const s = label[i];
      if (typeof s === 'string') upcoming.push(s);
    }
    this._streamer.prefetch(upcoming);
  }

  _playVoiceFor(scriptString) {
    this._stopVoice();
    if (!this._ensureStreamer()) return;

    // The flat script string is the manifest key on the server side too.
    // Parse it back to characterId + expression + text so the server can
    // resolve the voice profile.
    const m = scriptString.match(/^(\w+):(\w+)\s+(.+)$/);
    const characterId = m ? m[1] : null;
    const expression = m ? m[2] : null;
    const text = m ? m[3] : scriptString;

    this._streamer.play({ scriptString, text, characterId, expression });
    this._startLipSync();
    // Warm what's next while this line is speaking.
    this._prefetchUpcomingVoices();
  }

  executeNext() {
    const label = this.script[this.currentLabel];
    if (!label || this.statementIndex >= label.length) {
      // End of label and no choice was the final statement — the opening
      // script ran out, or the AI's expansion ended without a Choice block.
      // Ask the server to continue the spine UNLESS the ending already fired.
      if (this._endingFired) {
        this._showEndingCard();
      } else {
        this._continueBeat();
      }
      return;
    }

    const stmt = label[this.statementIndex];
    if (typeof stmt === 'string') {
      this._executeStringStatement(stmt);
    } else if (typeof stmt === 'object' && stmt !== null) {
      if (stmt.Choice) this._showChoices(stmt.Choice);
      else this.advance();
    }
  }

  async _continueBeat() {
    if (this.isWaiting) return;
    this.isWaiting = true;
    this.dialogueBox.classList.remove('dialogue-active');
    this.loadingOverlay.style.display = 'flex';
    try {
      const result = await api.post(`/sessions/${this.sessionId}/advance`, {});
      this._injectAndPlay(result);
    } catch (err) {
      console.error('continue beat error:', err);
      this.loadingOverlay.style.display = 'none';
      this.isWaiting = false;
      this._showDialogue(`Something went wrong: ${err.message}`);
    }
  }

  _showEndingCard() {
    if (this._endingCardShown) return;
    this._endingCardShown = true;
    const name = this._chosenEnding?.name || 'The End';
    const card = document.createElement('div');
    card.className = 'start-gate';
    card.innerHTML = `
      <div class="start-gate-card">
        <div class="start-gate-ornament">&mdash; &#10022; &mdash;</div>
        <div class="start-gate-title">${name}</div>
        <div class="start-gate-hint">Your tale has reached its end.</div>
        <div class="ending-card-actions">
          <button class="btn btn-primary btn-lg" data-act="continue">
            <span class="btn-icon">&#10148;</span> Continue to next chapter
          </button>
          <button class="btn btn-secondary" data-act="library">Return to library</button>
        </div>
        <div class="continue-status" id="continue-status" style="display:none;"></div>
      </div>`;
    this.container.appendChild(card);

    card.querySelector('[data-act="library"]').addEventListener('click', () => {
      this._navigate('/sessions');
    });
    card.querySelector('[data-act="continue"]').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const status = card.querySelector('#continue-status');
      btn.disabled = true;
      status.style.display = 'block';
      status.textContent = 'Authoring the next chapter…';
      try {
        const child = await api.post(`/sessions/${this.sessionId}/continue`, {});
        // Kick off the generation pipeline on the new chapter and jump to
        // the loading screen so the player can watch progress.
        await api.post(`/sessions/${child.id}/generate`, {});
        this._navigate(`/loading/${child.id}`);
      } catch (err) {
        btn.disabled = false;
        status.textContent = `Couldn't continue: ${err.message}`;
      }
    });
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
    const url = assetUrl(`${this.sessionId}/backgrounds/${sceneId}.png`);
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
      this._relayoutSprites();
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
    this._relayoutSprites();
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
      this._relayoutSprites();
    }
  }

  /**
   * Distribute visible sprites evenly across the canvas so they don't overlap.
   * Respects the AI's left/center/right intent as ordering hints.
   */
  _relayoutSprites() {
    const posOrder = { left: 0, center: 1, right: 2 };
    const entries = Object.values(this.sprites)
      .sort((a, b) => (posOrder[a.position] ?? 1) - (posOrder[b.position] ?? 1));
    const n = entries.length;

    // Tag the characters layer with the count so CSS can adjust max-height
    this.charsEl.className = `characters-layer count-${Math.min(n, 4)}`;

    // Evenly spaced slots; leaves a margin on each side
    const layouts = {
      1: ['50%'],
      2: ['28%', '72%'],
      3: ['18%', '50%', '82%'],
      4: ['14%', '38%', '62%', '86%'],
    };
    const slots = layouts[Math.min(n, 4)] || layouts[4];
    entries.forEach((sprite, i) => sprite.setSlotX(slots[i] ?? '50%'));
  }

  _showDialogue(stmt) {
    const dialogueMatch = stmt.match(/^(\w+):(\w+)\s+(.+)$/);
    this.dialogueBox.style.display = 'block';
    this.dialogueBox.classList.add('dialogue-active');
    this.interactionPanel.style.display = 'none';

    if (dialogueMatch) {
      const [, charId, expression, text] = dialogueMatch;
      const character = this.characters[charId];

      // Special case: when the AI marks the protagonist as the speaker the
      // raw id may be "player", "<name>_player", literal "None" / "null"
      // (legacy sessions), or the protagonist's own name. Use the configured
      // protagonist name for the speaker label in all of those cases.
      const protagonistName = this.session?.setup_protagonist_name;
      const cidLower = (charId || '').toLowerCase();
      const isProtagonist = !character && protagonistName && (
        cidLower === 'player' || cidLower === 'none' || cidLower === 'null' ||
        /_player$/i.test(charId) ||
        cidLower === protagonistName.toLowerCase()
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
        // Spine model: each choice carries an alignment tag + magnitude that
        // the server adds to alignment_state to pick the ending at beat 10.
        alignmentTag: choice._alignmentTag || null,
        magnitude: choice._magnitude || 1,
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

    this.script[result.newLabel] = result.statements;
    if (result.extraLabels) Object.assign(this.script, result.extraLabels);

    // Newly-expanded beats bring their own pre-rendered audio; merging it here
    // is what lets the next lines play from the CDN instead of falling back to
    // a per-line WebSocket.
    this._mergeVoiceManifest(result.audioManifest);

    this.currentLabel = result.newLabel;
    this.statementIndex = 0;
    this._currentBeatIndex = result.beatIndex ?? this._currentBeatIndex ?? 0;
    this._alignmentState = result.alignmentState || this._alignmentState || {};
    this._endingFired = !!result.endingFired;
    this._chosenEnding = result.chosenEnding || this._chosenEnding;
    this.executeNext();
  }

  // ===== Pause menu / save / load / restart ============================

  _snapshot() {
    return {
      currentLabel: this.currentLabel,
      statementIndex: this.statementIndex,
      currentSceneId: this._currentSceneId,
      currentBeatIndex: this._currentBeatIndex ?? 0,
      alignmentState: this._alignmentState ?? {},
      chosenEndingId: this._chosenEnding?.id || null,
      visibleCharacters: Object.values(this.sprites).map((s) => ({
        id: s.characterId,
        expression: s.expression || 'neutral',
        position: s.position || 'center',
      })),
    };
  }

  togglePauseMenu() {
    if (this._pauseEl) {
      this._closePauseMenu();
    } else {
      this._openPauseMenu();
    }
  }

  _closePauseMenu() {
    if (!this._pauseEl) return;
    this._pauseEl.remove();
    this._pauseEl = null;
  }

  _openPauseMenu() {
    if (this._pauseEl) return;
    const el = document.createElement('div');
    el.className = 'pause-menu';
    el.innerHTML = `
      <div class="pause-card">
        <div class="ornament">Paused</div>
        <h2 class="display-title">A pause in the tale</h2>
        <div class="pause-actions">
          <button class="btn btn-secondary" data-act="resume">Resume</button>
          <button class="btn btn-secondary" data-act="save">Save…</button>
          <button class="btn btn-secondary" data-act="load">Load…</button>
          <button class="btn btn-danger" data-act="restart">Restart</button>
          <button class="btn btn-ghost" data-act="menu">Quit to library</button>
        </div>
      </div>`;
    this.container.appendChild(el);
    this._pauseEl = el;
    el.addEventListener('click', (e) => { if (e.target === el) this._closePauseMenu(); });
    el.querySelectorAll('button[data-act]').forEach((b) => {
      b.addEventListener('click', () => this._handlePauseAction(b.dataset.act));
    });
  }

  async _handlePauseAction(act) {
    if (act === 'resume') return this._closePauseMenu();
    if (act === 'menu') return this._navigate('/sessions');
    if (act === 'save') return this._openSaveDialog();
    if (act === 'load') return this._openLoadDialog();
    if (act === 'restart') return this._confirmRestart();
  }

  async _openSaveDialog() {
    this._closePauseMenu();
    const name = await this._modal({ message: 'Name this save (optional):', prompt: true, defaultValue: `Beat ${(this._currentBeatIndex ?? 0) + 1}`, confirmText: 'Save' });
    if (name === null) return this._openPauseMenu();
    api.post(`/sessions/${this.sessionId}/saves`, {
      name: name || null,
      snapshot: this._snapshot(),
    }).then(() => this._toast('Saved.'))
      .catch((err) => this._toast(`Save failed: ${err.message}`));
  }

  async _openLoadDialog() {
    this._closePauseMenu();
    let saves;
    try {
      saves = await api.get(`/sessions/${this.sessionId}/saves`);
    } catch (err) {
      return this._toast(`Load list failed: ${err.message}`);
    }
    if (!saves.length) return this._toast('No saves yet.');

    const el = document.createElement('div');
    el.className = 'pause-menu';
    el.innerHTML = `
      <div class="pause-card">
        <div class="ornament">Saves</div>
        <h2 class="display-title">Resume a tale</h2>
        <div class="save-list">
          ${saves.map((s) => `
            <div class="save-row" data-id="${s.id}">
              <div class="save-info">
                <div class="save-name">${s.name || `Beat ${s.current_beat_index + 1}`}</div>
                <div class="save-meta">${new Date(s.created_at).toLocaleString()} · beat ${s.current_beat_index + 1}/10</div>
              </div>
              <div class="save-row-actions">
                <button class="btn btn-primary" data-act="load">Load</button>
                <button class="btn btn-danger" data-act="del">×</button>
              </div>
            </div>`).join('')}
        </div>
        <div class="pause-actions">
          <button class="btn btn-ghost" data-act="back">Back</button>
        </div>
      </div>`;
    this.container.appendChild(el);
    this._pauseEl = el;
    el.addEventListener('click', (e) => { if (e.target === el) this._closePauseMenu(); });
    el.querySelector('[data-act="back"]').addEventListener('click', () => {
      this._closePauseMenu(); this._openPauseMenu();
    });
    el.querySelectorAll('.save-row').forEach((row) => {
      const id = row.dataset.id;
      row.querySelector('[data-act="load"]').addEventListener('click', () => this._loadSave(id));
      row.querySelector('[data-act="del"]').addEventListener('click', async () => {
        if (!(await this._modal({ message: 'Delete this save?', confirmText: 'Delete', danger: true }))) return;
        try {
          await api.delete(`/sessions/${this.sessionId}/saves/${id}`);
          row.remove();
        } catch (err) { this._toast(`Delete failed: ${err.message}`); }
      });
    });
  }

  async _loadSave(saveId) {
    let save;
    try {
      save = await api.get(`/sessions/${this.sessionId}/saves/${saveId}`);
    } catch (err) {
      return this._toast(`Load failed: ${err.message}`);
    }
    this._closePauseMenu();
    this._applySnapshot(save);
  }

  async _confirmRestart() {
    this._closePauseMenu();
    if (!(await this._modal({ message: 'Restart this tale from the beginning? Your current progress will be wiped.', confirmText: 'Restart', danger: true }))) return;
    api.post(`/sessions/${this.sessionId}/restart`, {})
      .then(() => window.location.reload())
      .catch((err) => this._toast(`Restart failed: ${err.message}`));
  }

  _applySnapshot(save) {
    // Reset audio + sprites + dialogue.
    this._stopVoice();
    this._typewriterGen++;
    this._isTyping = false;
    this.dialogueBox.classList.remove('dialogue-active');
    this.interactionPanel.style.display = 'none';
    for (const cid of Object.keys(this.sprites)) {
      this.sprites[cid].destroy();
    }
    this.sprites = {};
    this._currentSceneId = null;

    // Restore scene + characters from the snapshot.
    if (save.current_scene_id) {
      this._showScene(`show scene ${save.current_scene_id} with fadeIn`);
    }
    const visible = save.visible_characters || [];
    for (const v of visible) {
      this._showCharacter(`show character ${v.id} ${v.expression || 'neutral'} at ${v.position || 'center'} with fadeIn`);
    }

    // Resume script position + spine state.
    this.currentLabel = save.current_label || 'Start';
    this.statementIndex = Math.max(0, save.statement_index || 0);
    this._currentBeatIndex = save.current_beat_index ?? 0;
    this._alignmentState = save.alignment_state || {};
    this._chosenEnding = save.chosen_ending_id ? { id: save.chosen_ending_id } : null;
    this._endingFired = false;
    this.isWaiting = false;
    this._toast('Resumed.');
    this.executeNext();
  }

  _toast(message) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = message;
    this.container.appendChild(t);
    setTimeout(() => t.classList.add('toast-out'), 1800);
    setTimeout(() => t.remove(), 2300);
  }

  /**
   * In-page animated confirm/prompt, replacing native confirm()/prompt().
   * Resolves to true/false (confirm) or the string/null (prompt). Cancel is
   * focused by default so destructive actions need a deliberate click.
   */
  _modal({ message, confirmText = 'OK', cancelText = 'Cancel', danger = false, prompt = false, defaultValue = '' }) {
    return new Promise((resolve) => {
      const el = document.createElement('div');
      el.className = 'pause-menu';
      const val = String(defaultValue || '').replace(/"/g, '&quot;');
      el.innerHTML = `
        <div class="pause-card" style="text-align:left;">
          <p class="modal-message">${message}</p>
          ${prompt ? `<input class="input vn-modal-input" type="text" value="${val}" />` : ''}
          <div class="modal-actions">
            <button class="btn" data-act="cancel">${cancelText}</button>
            <button class="btn ${danger ? 'btn-danger-solid' : 'btn-primary'}" data-act="ok">${confirmText}</button>
          </div>
        </div>`;
      this.container.appendChild(el);
      const input = el.querySelector('.vn-modal-input');
      const cancelBtn = el.querySelector('[data-act="cancel"]');
      const okBtn = el.querySelector('[data-act="ok"]');
      if (input) { input.focus(); input.select(); } else { cancelBtn.focus(); }
      const done = (v) => { el.remove(); resolve(v); };
      cancelBtn.addEventListener('click', () => done(prompt ? null : false));
      okBtn.addEventListener('click', () => done(prompt ? (input ? input.value : '') : true));
      el.addEventListener('click', (e) => { if (e.target === el) done(prompt ? null : false); });
      if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') done(input.value); });
    });
  }

  /**
   * Tear down everything init() attached so leaving the game leaks nothing:
   * the document-level keydown listener, the RAF lip-sync loop, the live TTS
   * WebSocket + AudioContext, any appended overlays, and all sprite rigs.
   * The React GamePlayer calls this on unmount.
   */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    this._stopVoice();
    if (this._streamer) { try { this._streamer.stop(); } catch {} this._streamer = null; }
    if (this._audioCtx) { try { this._audioCtx.close(); } catch {} this._audioCtx = null; }
    if (this._onGlobalKey) {
      document.removeEventListener('keydown', this._onGlobalKey);
      this._onGlobalKey = null;
    }
    this._typewriterGen++;
    this._isTyping = false;
    if (this._pauseEl) { try { this._pauseEl.remove(); } catch {} this._pauseEl = null; }
    for (const cid of Object.keys(this.sprites)) {
      try { this.sprites[cid].destroy(); } catch {}
    }
    this.sprites = {};
    this._endingCardShown = false;
  }
}

export const gameBridge = new GameBridge();
