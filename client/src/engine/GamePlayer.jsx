import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { gameBridge } from './game-bridge.js';

/* The exact DOM the vanilla engine expects. Built imperatively into a ref so
 * React never reconciles the nodes the engine mutates. */
const CANVAS_HTML = `
  <div class="game-canvas" id="game-canvas">
    <div class="scene-background" id="scene-bg"></div>
    <div class="characters-layer" id="characters-layer"></div>
    <div class="dialogue-box" id="dialogue-box" style="display:none;">
      <div class="speaker-name" id="speaker-name"></div>
      <div class="dialogue-text" id="dialogue-text"></div>
      <div class="dialogue-advance" id="dialogue-advance">▼</div>
    </div>
    <div class="interaction-panel" id="interaction-panel" style="display:none;">
      <div class="choices-panel" id="choices-panel"></div>
      <div class="free-input-panel" id="free-input-panel">
        <input type="text" id="free-input-text" placeholder="What do you want to say or do?" maxlength="300" />
        <button class="btn btn-primary" id="free-input-send">Send</button>
      </div>
    </div>
    <div class="loading-overlay" id="loading-overlay" style="display:none;">
      <div class="thinking-indicator"><span></span><span></span><span></span></div>
      <p>The next page is being written…</p>
    </div>
  </div>
`;

/**
 * Mounts the vanilla VN engine into a host div and tears it down cleanly on
 * unmount (dispose() removes the keydown listener, RAF, WS, AudioContext).
 * Data is loaded by the parent Game page and passed in as props.
 */
export default function GamePlayer({ sessionId, session, characters, scenes, script }) {
  const hostRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    host.innerHTML = CANVAS_HTML;
    const canvas = host.querySelector('#game-canvas');

    // Cache-buster keyed on updated_at (engine reads window global).
    window.STORYPLEX_ASSET_VERSION = (session?.updated_at || '').replace(/\D/g, '');

    gameBridge.init({
      sessionId,
      container: canvas,
      characters,
      scenes,
      // clone so the engine can mutate its own copy with injected labels
      script: { ...script },
      session,
      navigate: (path) => navigate(path === '/sessions' ? '/library' : path),
    });
    gameBridge.start();

    return () => {
      gameBridge.dispose();
      host.innerHTML = '';
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return <div className="game-canvas-host" ref={hostRef} />;
}
