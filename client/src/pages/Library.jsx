import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import StoryCard from '../components/StoryCard.jsx';
import { routeForStory } from './Landing.jsx';

export default function Library() {
  const qc = useQueryClient();
  const { data: sessions = [], isLoading, isError, error } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => api.get('/sessions'),
  });

  const del = useMutation({
    mutationFn: (id) => api.delete(`/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  });

  const onDelete = (story) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (window.confirm('Delete this tale? This cannot be undone.')) {
      del.mutate(story.id);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Library</span>
        <h1 className="display">Your tales</h1>
        <p>Everything you've woven. Pick up where you left off, or start something new.</p>
      </div>

      {isLoading ? (
        <div className="empty"><div className="dots"><span /><span /><span /></div></div>
      ) : isError ? (
        <div className="form-error">Couldn't load your library: {error.message}</div>
      ) : sessions.length === 0 ? (
        <div className="empty">
          <p>The shelves are empty. Begin a new tale.</p>
          <Link to="/create" className="btn btn-primary btn-lg">
            <span className="btn-icon">✦</span> Author a tale
          </Link>
        </div>
      ) : (
        <div className="grid-cards">
          {sessions.map((s) => (
            <StoryCard key={s.id} story={s} to={routeForStory(s)} onDelete={onDelete(s)} />
          ))}
        </div>
      )}
    </div>
  );
}
