import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import { assetUrl } from '../lib/assets.js';
import { useAuth } from '../auth/AuthContext.jsx';
import Avatar from '../components/Avatar.jsx';

function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function Stars({ value = 0, onRate, readOnly }) {
  const [hover, setHover] = useState(0);
  return (
    <span className={`stars-input ${readOnly ? 'is-readonly' : ''}`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={`star ${n <= (hover || value) ? 'on' : ''}`}
          onMouseEnter={() => !readOnly && setHover(n)}
          onMouseLeave={() => !readOnly && setHover(0)}
          onClick={() => !readOnly && onRate?.(n)}
          disabled={readOnly}
          aria-label={`${n} star${n > 1 ? 's' : ''}`}
        >
          ★
        </button>
      ))}
    </span>
  );
}

export default function StoryDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { user, login } = useAuth();
  const [body, setBody] = useState('');
  const [replyTo, setReplyTo] = useState(null);

  const detailQ = useQuery({ queryKey: ['story', id], queryFn: () => api.get(`/stories/${id}`) });
  const commentsQ = useQuery({ queryKey: ['comments', id], queryFn: () => api.get(`/stories/${id}/comments`) });

  const like = useMutation({
    mutationFn: (liked) => (liked ? api.delete(`/stories/${id}/like`) : api.post(`/stories/${id}/like`, {})),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['story', id] }),
  });
  const rate = useMutation({
    mutationFn: (score) => api.post(`/stories/${id}/rate`, { score }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['story', id] }),
  });
  const addComment = useMutation({
    mutationFn: (payload) => api.post(`/stories/${id}/comments`, payload),
    onSuccess: () => {
      setBody(''); setReplyTo(null);
      qc.invalidateQueries({ queryKey: ['comments', id] });
      qc.invalidateQueries({ queryKey: ['story', id] });
    },
  });
  const delComment = useMutation({
    mutationFn: (cid) => api.delete(`/stories/${id}/comments/${cid}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['comments', id] });
      qc.invalidateQueries({ queryKey: ['story', id] });
    },
  });

  if (detailQ.isLoading) return <div className="page page--narrow"><div className="empty"><div className="dots"><span /><span /><span /></div></div></div>;
  if (detailQ.isError) return <div className="page page--narrow"><div className="form-error">This story isn’t available.</div></div>;

  const s = detailQ.data;
  const isOwner = user && s.author?.id === user.id;
  const initial = (s.title || '?').trim().charAt(0).toUpperCase();
  const comments = commentsQ.data || [];
  const tops = comments.filter((c) => !c.parentId);
  const repliesOf = (cid) => comments.filter((c) => c.parentId === cid);

  const submitComment = (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    addComment.mutate({ body: body.trim(), parentId: replyTo });
  };

  const Comment = ({ c, isReply }) => (
    <div className={`comment ${isReply ? 'comment--reply' : ''}`}>
      <span className="user-avatar" style={{ width: 34, height: 34, fontSize: '0.85rem' }}>
        <Avatar url={c.author.avatarUrl} name={c.author.displayName || c.author.username} />
      </span>
      <div className="comment__body">
        <div className="comment__head">
          <Link to={`/u/${c.author.username}`} className="comment__author"><b>{c.author.displayName || c.author.username}</b></Link>
          <span className="faint">@{c.author.username} · {fmtDate(c.createdAt)}</span>
        </div>
        <p className={c.deleted ? 'faint' : ''}>{c.deleted ? '[deleted]' : c.body}</p>
        {!c.deleted && (
          <div className="comment__actions">
            {user && !isReply && (
              <button className="linkbtn" onClick={() => setReplyTo(replyTo === c.id ? null : c.id)}>
                {replyTo === c.id ? 'Cancel' : 'Reply'}
              </button>
            )}
            {user && c.author.id === user.id && (
              <button className="linkbtn" onClick={() => delComment.mutate(c.id)}>Delete</button>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="page page--narrow">
      <Link to="/explore" className="back-link">← Explore</Link>

      <div className="detail">
        <div className="detail__cover">
          <img
            src={assetUrl(`${s.id}/cover.png`)}
            alt=""
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
          <span className="cover-initial" aria-hidden="true">{initial}</span>
        </div>

        <div className="detail__main">
          <div className="story-card__tags">
            {s.setup_genre && <span className="chip">{s.setup_genre}</span>}
            {s.setup_tone && <span className="chip chip-plain">{s.setup_tone}</span>}
            {s.chapter_number > 1 && <span className="chip chip-plain">Ch. {s.chapter_number}</span>}
          </div>
          <h1 className="display">{s.title}</h1>
          {s.author?.username && (
            <Link to={`/u/${s.author.username}`} className="detail__author">
              <span className="user-avatar" style={{ width: 26, height: 26, fontSize: '0.7rem' }}>
                <Avatar url={s.author.avatarUrl} name={s.author.displayName || s.author.username} />
              </span>
              by <b>@{s.author.username}</b>
            </Link>
          )}
          {s.setting && <p className="detail__desc">{s.setting}</p>}

          <div className="detail__stats">
            <span className="heartline">♥ {s.likeCount}</span>
            <span className="stars">★ {s.ratingAvg ?? '–'} <span className="faint">({s.ratingCount})</span></span>
            <span>▶ {s.playCount} plays</span>
            <span>💬 {s.commentCount}</span>
          </div>

          <div className="detail__actions">
            <Link to={`/play/${s.id}`} className="btn btn-primary btn-lg"><span className="btn-icon">▶</span> Play</Link>
            {user ? (
              <button
                className={`btn ${s.me.liked ? 'btn-primary' : ''}`}
                onClick={() => like.mutate(s.me.liked)}
                disabled={like.isPending}
              >
                {s.me.liked ? '♥ Liked' : '♡ Like'}
              </button>
            ) : (
              <button className="btn" onClick={login}>Sign in to interact</button>
            )}
            {isOwner && (
              <span className={`chip ${s.visibility === 'public' ? '' : 'chip-plain'}`}>
                {s.visibility === 'public' ? 'Public' : 'Private'}
              </span>
            )}
          </div>

          {user && (
            <div className="detail__rate">
              <span className="faint">Your rating:</span>
              <Stars value={s.me.myRating || 0} onRate={(n) => rate.mutate(n)} />
            </div>
          )}
        </div>
      </div>

      <section className="comments">
        <h2 className="display">Comments <span className="faint">({s.commentCount})</span></h2>
        {user ? (
          <form className="comment-form" onSubmit={submitComment}>
            {replyTo && <div className="faint" style={{ fontSize: '0.8rem' }}>Replying… <button type="button" className="linkbtn" onClick={() => setReplyTo(null)}>cancel</button></div>}
            <textarea
              className="textarea"
              placeholder="Share your thoughts…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={2000}
              rows={3}
            />
            <div className="form-actions" style={{ marginTop: '0.6rem' }}>
              <button className="btn btn-primary" disabled={!body.trim() || addComment.isPending}>Post</button>
            </div>
          </form>
        ) : (
          <div className="banner"><span className="badge badge-created">tip</span> Sign in to join the conversation.
            <span className="spacer" /><button className="btn btn-sm" onClick={login}>Sign in</button></div>
        )}

        <div className="comment-list">
          {tops.length === 0 && <p className="faint">No comments yet — be the first.</p>}
          {tops.map((c) => (
            <div key={c.id}>
              <Comment c={c} />
              {repliesOf(c.id).map((r) => <Comment key={r.id} c={r} isReply />)}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
