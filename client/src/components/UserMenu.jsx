import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import Avatar from './Avatar.jsx';

export default function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!user) return null;
  const label = user.displayName || user.username || '?';

  return (
    <div className="theme-menu" ref={ref}>
      <button
        className="user-avatar"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        title={label}
      >
        <Avatar url={user.avatarUrl} name={label} />
      </button>
      {open && (
        <div className="theme-pop card" role="menu" style={{ width: 224 }}>
          <div className="user-head">
            <div className="user-name">{label}</div>
            <div className="user-email">{user.email}</div>
          </div>
          {user.username && (
            <Link to={`/u/${user.username}`} className="theme-pop__item" onClick={() => setOpen(false)}>Your profile</Link>
          )}
          <Link to="/library" className="theme-pop__item" onClick={() => setOpen(false)}>Your library</Link>
          <Link to="/billing" className="theme-pop__item" onClick={() => setOpen(false)}>Credits</Link>
          <Link to="/settings" className="theme-pop__item" onClick={() => setOpen(false)}>Settings</Link>
          <button className="theme-pop__item" onClick={() => { setOpen(false); logout(); }}>Sign out</button>
        </div>
      )}
    </div>
  );
}
