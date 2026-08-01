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
export default function StoryCard({ story, to, onDelete }) {
  const title = story.title || 'Untitled tale';
  const initial = title.trim().charAt(0).toUpperCase() || '?';
  return (
    <div className="story-card">
      <Link className="story-card__hit" to={to}>
        <div className="story-card__cover">
          <div className="story-card__badges">
            <span className={`badge badge-${story.status}`}>{story.status}</span>
          </div>
          <span className="cover-initial" aria-hidden="true">{initial}</span>
        </div>
        <div className="story-card__body">
          <div className="story-card__tags">
            {story.setup_genre && <span className="chip">{story.setup_genre}</span>}
            {story.setup_tone && <span className="chip chip-plain">{story.setup_tone}</span>}
            {story.chapter_number > 1 && <span className="chip chip-plain">Ch. {story.chapter_number}</span>}
          </div>
          <h3 className="story-card__title">{title}</h3>
          <div className="story-card__foot">
            <span>{fmtDate(story.created_at)}</span>
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
    </div>
  );
}
