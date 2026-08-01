import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import StoryCard from '../components/StoryCard.jsx';

export const routeForStory = (s) =>
  s.status === 'ready' || s.status === 'playing'
    ? `/play/${s.id}`
    : s.status === 'generating'
    ? `/loading/${s.id}`
    : '/library';

export default function Landing() {
  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => api.get('/sessions'),
  });
  const featured = sessions
    .filter((s) => ['ready', 'playing'].includes(s.status))
    .slice(0, 6);

  return (
    <div className="page">
      <section className="hero">
        <span className="hero__kicker">✦ AI Visual Novels · <b>infinite branches</b></span>
        <h1>
          Every premise becomes<br />a <span className="pop">playable</span> world.
        </h1>
        <p className="hero__lede">
          Give StoryPlex a spark — a genre, a hero, a setting — and it writes the story,
          draws the cast and scenes, and voices every line. Then share it, and read
          everyone else's.
        </p>
        <div className="hero__actions">
          <Link to="/create" className="btn btn-primary btn-lg">
            <span className="btn-icon">▶</span> Begin a tale
          </Link>
          <Link to="/explore" className="btn btn-secondary btn-lg">Explore stories</Link>
        </div>
      </section>

      {featured.length > 0 && (
        <section className="featured">
          <div className="featured__head">
            <h2 className="display">Recent tales</h2>
            <Link to="/library">Your library →</Link>
          </div>
          <div className="grid-cards">
            {featured.map((s) => (
              <StoryCard key={s.id} story={s} to={`/story/${s.id}`} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
