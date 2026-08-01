import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import StoryCard from '../components/StoryCard.jsx';
import { routeForStory } from './Landing.jsx';

export default function Explore() {
  const { data: sessions = [], isLoading, isError, error } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => api.get('/sessions'),
  });
  const stories = sessions.filter((s) =>
    ['ready', 'playing', 'generating'].includes(s.status)
  );

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Explore</span>
        <h1 className="display">The gallery</h1>
        <p>Browse tales woven by StoryPlex and play any of them from the first page.</p>
      </div>

      <div className="banner">
        <span className="badge badge-generating">soon</span>
        Likes, ratings, comments &amp; creator profiles are on the way — this is the public
        gallery they'll plug into.
      </div>

      {isLoading ? (
        <div className="empty"><div className="dots"><span /><span /><span /></div></div>
      ) : isError ? (
        <div className="form-error">Couldn't load stories: {error.message}</div>
      ) : stories.length === 0 ? (
        <div className="empty">
          <p>No tales yet. Be the first to weave one.</p>
        </div>
      ) : (
        <div className="grid-cards">
          {stories.map((s) => (
            <StoryCard key={s.id} story={s} to={routeForStory(s)} />
          ))}
        </div>
      )}
    </div>
  );
}
