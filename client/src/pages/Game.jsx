import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../lib/api.js';
import { gameBridge } from '../engine/game-bridge.js';
import GamePlayer from '../engine/GamePlayer.jsx';

export default function Game() {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['game', id],
    queryFn: async () => {
      const [session, characters, scenes, script] = await Promise.all([
        api.get(`/sessions/${id}`),
        api.get(`/sessions/${id}/characters`),
        api.get(`/sessions/${id}/scenes`),
        api.get(`/sessions/${id}/script`),
      ]);
      return { session, characters, scenes, script };
    },
    staleTime: Infinity,
    refetchOnMount: false,
  });

  return (
    <div className="game-view">
      <div className="game-header">
        <button className="btn btn-sm" onClick={() => navigate('/library')}>← Library</button>
        <span className="game-title">{data?.session?.title || 'Loading…'}</span>
        <button
          className="btn btn-sm"
          title="Menu (Esc)"
          onClick={() => { if (data) gameBridge.togglePauseMenu(); }}
        >
          ☰ Menu
        </button>
      </div>
      <div className="game-container">
        {isLoading ? (
          <div className="loading-overlay" style={{ display: 'flex' }}>
            <div className="thinking-indicator"><span /><span /><span /></div>
            <p>Loading the stage…</p>
          </div>
        ) : isError ? (
          <div className="loading-overlay" style={{ display: 'flex' }}>
            <p>Failed to load: {error.message}</p>
            <button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button>
          </div>
        ) : (
          <GamePlayer sessionId={id} {...data} />
        )}
      </div>
    </div>
  );
}
