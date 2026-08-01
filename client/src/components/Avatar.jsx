import { useState } from 'react';

/**
 * Renders a user's avatar image, falling back to their initial.
 * `referrerPolicy="no-referrer"` is required — Google (lh3.googleusercontent.com)
 * returns 403 for profile images sent with a referrer. Renders the inner
 * content only; wrap it in a `.user-avatar` container.
 */
export default function Avatar({ url, name }) {
  const [ok, setOk] = useState(!!url);
  const initial = (name || '?').trim().charAt(0).toUpperCase() || '?';
  if (ok) {
    return (
      <img
        src={url}
        alt=""
        referrerPolicy="no-referrer"
        onError={() => setOk(false)}
      />
    );
  }
  return <span>{initial}</span>;
}
