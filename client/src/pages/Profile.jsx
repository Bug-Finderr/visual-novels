import { Link, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import { useAuth } from '../auth/AuthContext.jsx';
import Avatar from '../components/Avatar.jsx';
import StoryCard from '../components/StoryCard.jsx';

function fmtMonth(s) {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'long' });
}

export default function Profile() {
  const { handle } = useParams();
  const qc = useQueryClient();
  const { user, login } = useAuth();

  const profileQ = useQuery({
    queryKey: ['profile', handle],
    queryFn: () => api.get(`/v1/users/${handle}`),
    retry: false,
  });

  const follow = useMutation({
    mutationFn: (isFollowing) =>
      isFollowing
        ? api.delete(`/v1/users/${handle}/follow`)
        : api.post(`/v1/users/${handle}/follow`, {}),
    // Optimistic toggle so the button feels instant.
    onMutate: async (isFollowing) => {
      await qc.cancelQueries({ queryKey: ['profile', handle] });
      const prev = qc.getQueryData(['profile', handle]);
      if (prev) {
        qc.setQueryData(['profile', handle], {
          ...prev,
          isFollowing: !isFollowing,
          followers: prev.followers + (isFollowing ? -1 : 1),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(['profile', handle], ctx.prev),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['profile', handle] });
      qc.invalidateQueries({ queryKey: ['feed'] });
    },
  });

  if (profileQ.isLoading) {
    return <div className="page page--narrow"><div className="empty"><div className="dots"><span /><span /><span /></div></div></div>;
  }
  if (profileQ.isError) {
    return (
      <div className="page page--narrow">
        <div className="empty">
          <p>No creator found at <b>@{handle}</b>.</p>
          <Link to="/explore" className="btn btn-sm">Back to Explore</Link>
        </div>
      </div>
    );
  }

  const p = profileQ.data;
  const label = p.displayName || p.username;
  const stories = p.stories || [];

  return (
    <div className="page">
      <header className="profile-head">
        <span className="profile-avatar">
          <Avatar url={p.avatarUrl} name={label} />
        </span>
        <div className="profile-id">
          <h1 className="display">{label}</h1>
          <div className="profile-handle">@{p.username}</div>
          {p.bio && <p className="profile-bio">{p.bio}</p>}
          <div className="profile-meta faint">
            {p.createdAt && <span>Joined {fmtMonth(p.createdAt)}</span>}
          </div>
        </div>
        <div className="profile-cta">
          {p.isMe ? (
            <Link to="/settings" className="btn btn-sm">Edit profile</Link>
          ) : user ? (
            <button
              className={`btn ${p.isFollowing ? '' : 'btn-primary'}`}
              onClick={() => follow.mutate(p.isFollowing)}
              disabled={follow.isPending}
            >
              {p.isFollowing ? '✓ Following' : '＋ Follow'}
            </button>
          ) : (
            <button className="btn btn-primary" onClick={login}>Follow</button>
          )}
        </div>
      </header>

      <div className="profile-stats">
        <span><b>{stories.length}</b> {stories.length === 1 ? 'story' : 'stories'}</span>
        <span><b>{p.followers}</b> {p.followers === 1 ? 'follower' : 'followers'}</span>
        <span><b>{p.following}</b> following</span>
      </div>

      <div className="page-head" style={{ marginTop: '1.6rem' }}>
        <span className="eyebrow">Published</span>
        <h2 className="display">{p.isMe ? 'Your published tales' : `Tales by ${label}`}</h2>
      </div>

      {stories.length === 0 ? (
        <div className="empty">
          <p>{p.isMe ? 'You haven’t published anything yet — publish a tale from your Library.' : 'No published tales yet.'}</p>
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
