import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import { useAuth } from '../auth/AuthContext.jsx';
import StoryCard from '../components/StoryCard.jsx';

const SORTS = [
  { key: 'new', label: 'Newest' },
  { key: 'top', label: 'Most liked' },
  { key: 'rated', label: 'Top rated' },
  { key: 'played', label: 'Most played' },
];

export default function Explore() {
  const [sort, setSort] = useState('new');
  const { user, login } = useAuth();
  const following = sort === 'following';

  const { data: stories = [], isLoading, isError, error } = useQuery({
    queryKey: following ? ['feed'] : ['explore', sort],
    queryFn: () => api.get(following ? '/feed' : `/sessions?sort=${sort}`),
    enabled: !following || !!user, // the feed needs a signed-in user
  });

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Explore</span>
        <h1 className="display">The gallery</h1>
        <p>Published tales from the community — play any of them, then like, rate, and discuss.</p>
      </div>

      <div className="sort-tabs">
        {SORTS.map((s) => (
          <button
            key={s.key}
            className={`sort-tab ${sort === s.key ? 'active' : ''}`}
            onClick={() => setSort(s.key)}
          >
            {s.label}
          </button>
        ))}
        <span className="sort-tabs__div" aria-hidden="true" />
        <button
          className={`sort-tab ${following ? 'active' : ''}`}
          onClick={() => setSort('following')}
        >
          ✦ Following
        </button>
      </div>

      {following && !user ? (
        <div className="empty">
          <p>Sign in to see the latest tales from creators you follow.</p>
          <button className="btn btn-primary btn-sm" onClick={login}>Sign in</button>
        </div>
      ) : isLoading ? (
        <div className="empty"><div className="dots"><span /><span /><span /></div></div>
      ) : isError ? (
        <div className="form-error">Couldn't load stories: {error.message}</div>
      ) : stories.length === 0 ? (
        <div className="empty">
          {following ? (
            <p>Nothing here yet. Follow some creators from their profiles and their new tales will show up here.</p>
          ) : (
            <p>Nothing published yet. Publish a tale from your Library and it’ll appear here.</p>
          )}
        </div>
      ) : (
        <div className="grid-cards">
          {stories.map((s) => (
            <StoryCard key={s.id} story={s} to={`/story/${s.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
