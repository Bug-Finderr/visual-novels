import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import StoryCard from '../components/StoryCard.jsx';
import { routeForStory } from './Landing.jsx';
import { useAuth } from '../auth/AuthContext.jsx';
import { useConfirm } from '../components/ConfirmProvider.jsx';

export default function Library() {
  const qc = useQueryClient();
  const { user, login, googleEnabled } = useAuth();

  // Signed in → your own stories. Anonymous → the shared dev view of all.
  const query = useQuery({
    queryKey: user ? ['library', user.id] : ['sessions'],
    queryFn: () => (user ? api.get('/v1/library') : api.get('/sessions')),
  });

  const stories = user ? (query.data?.stories || []) : (query.data || []);

  const confirm = useConfirm();

  const del = useMutation({
    mutationFn: (id) => api.delete(`/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries(),
  });
  const publish = useMutation({
    mutationFn: ({ id, makePublic }) =>
      api.post(`/v1/library/${id}/${makePublic ? 'publish' : 'unpublish'}`, {}),
    onSuccess: () => qc.invalidateQueries(),
  });

  const onDelete = (story) => async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const ok = await confirm({
      title: 'Delete this tale?',
      message: 'This permanently removes the story and its generated assets. This can’t be undone.',
      confirmText: 'Delete',
      danger: true,
    });
    if (ok) del.mutate(story.id);
  };

  const onTogglePublish = (story) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    publish.mutate({ id: story.id, makePublic: story.visibility !== 'public' });
  };

  const { isLoading, isError, error } = query;

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Library</span>
        <h1 className="display">Your tales</h1>
        <p>Everything you've woven. Pick up where you left off, or start something new.</p>
      </div>

      {!user && googleEnabled && (
        <div className="banner">
          <span className="badge badge-created">tip</span>
          Sign in to keep your tales in your own library.
          <span className="spacer" />
          <button className="btn btn-sm" onClick={login}>Sign in</button>
        </div>
      )}

      {isLoading ? (
        <div className="empty"><div className="dots"><span /><span /><span /></div></div>
      ) : isError ? (
        <div className="form-error">Couldn't load your library: {error.message}</div>
      ) : stories.length === 0 ? (
        <div className="empty">
          <p>The shelves are empty. Begin a new tale.</p>
          <Link to="/create" className="btn btn-primary btn-lg">
            <span className="btn-icon">✦</span> Author a tale
          </Link>
        </div>
      ) : (
        <div className="grid-cards">
          {stories.map((s) => (
            <StoryCard
              key={s.id}
              story={s}
              to={routeForStory(s)}
              onDelete={onDelete(s)}
              onTogglePublish={user ? onTogglePublish(s) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
