import { useState } from 'react';
import { Link } from 'react-router-dom';

function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/**
 * The manga cover card used across Explore / Library / Landing.
 * `to` is the destination route; `onDelete` (optional) shows a corner delete.
 * Social counts (likes/ratings) are intentionally omitted until that data
 * exists — no fabricated engagement numbers.
 */
export default function StoryCard({ story, to, onDelete, onTogglePublish }) {
  const title = story.title || 'Untitled tale';
  const initial = title.trim().charAt(0).toUpperCase() || '?';

  // A cover only exists once the pipeline has run; brand-new/errored sessions
  // fall straight back to the initial. On a 404/load error we drop the img.
  const mayHaveCover = ['ready', 'playing', 'generating'].includes(story.status);
  const [coverOk, setCoverOk] = useState(mayHaveCover);
  const bust = story.updated_at ? `?v=${String(story.updated_at).replace(/\D/g, '')}` : '';
  const coverUrl = `/game-assets/${story.id}/cover.png${bust}`;

  return (
    <div className="story-card">
      <Link className="story-card__hit" to={to}>
        <div className="story-card__cover">
          <span className="cover-initial" aria-hidden="true">{initial}</span>
          {coverOk && (
            <img src={coverUrl} alt="" loading="lazy" onError={() => setCoverOk(false)} />
          )}
          <div className="story-card__badges">
            <span className={`badge badge-${story.status}`}>{story.status}</span>
          </div>
        </div>
        <div className="story-card__body">
          <div className="story-card__tags">
            {story.setup_genre && <span className="chip">{story.setup_genre}</span>}
            {story.setup_tone && <span className="chip chip-plain">{story.setup_tone}</span>}
            {story.chapter_number > 1 && <span className="chip chip-plain">Ch. {story.chapter_number}</span>}
          </div>
          <h3 className="story-card__title">{title}</h3>
          {story.author_username && (
            <div className="story-card__author">by @{story.author_username}</div>
          )}
          <div className="story-card__foot">
            {story.like_count !== undefined ? (
              <>
                <span className="heartline">♥ {story.like_count || 0}</span>
                {story.rating_count > 0 && (
                  <span className="stars">★ {(story.rating_sum / story.rating_count).toFixed(1)}</span>
                )}
                <span>▶ {story.play_count || 0}</span>
              </>
            ) : (
              <span>{fmtDate(story.created_at)}</span>
            )}
          </div>
        </div>
      </Link>
      {onDelete && (
        <button
          className="story-card__del"
          title="Delete"
          aria-label={`Delete ${title}`}
          onClick={onDelete}
        >
          ✕
        </button>
      )}
      {onTogglePublish && (
        <div className="story-card__bar">
          <span className={`vis-dot vis-${story.visibility === 'public' ? 'public' : 'private'}`} />
          <span>{story.visibility === 'public' ? 'Public' : 'Private'}</span>
          <span className="spacer" />
          <button className="btn btn-sm" onClick={onTogglePublish} disabled={story.status !== 'ready'}>
            {story.visibility === 'public' ? 'Unpublish' : 'Publish'}
          </button>
        </div>
      )}
    </div>
  );
}
