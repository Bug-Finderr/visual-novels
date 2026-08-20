import { Link, NavLink, Outlet } from 'react-router-dom';
import ThemeMenu from './ThemeMenu.jsx';
import UserMenu from './UserMenu.jsx';
import { useAuth } from '../auth/AuthContext.jsx';
import { useCredits } from '../lib/credits.js';

const navClass = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`;

/** Site chrome (nav + footer) wrapping the standard pages. The fullscreen
 *  reader route (/play/:id) renders outside this. */
export default function Layout() {
  const { user, googleEnabled, login, loading } = useAuth();
  const { data: credits } = useCredits(!!user);
  const balance = credits?.balance;
  return (
    <div className="app-shell">
      <header className="nav">
        <div className="nav-inner">
          <Link to="/" className="brand">
            <span className="brand-mark">✦</span> StoryPlex
          </Link>
          <nav className="nav-links">
            <NavLink to="/explore" className={navClass}>Explore</NavLink>
            <NavLink to="/library" className={navClass}>Library</NavLink>
            <NavLink to="/create" className={navClass}>Create</NavLink>
          </nav>
          <span className="nav-spacer" />
          <div className="nav-actions">
            {user && balance !== undefined && (
              <Link
                to="/billing"
                className={`credit-chip ${balance === 0 ? 'is-empty' : ''}`}
                title={`${balance} story ${balance === 1 ? 'credit' : 'credits'}`}
              >
                ✦ {balance}
              </Link>
            )}
            <Link to="/create" className="btn btn-primary btn-sm">＋ New tale</Link>
            <ThemeMenu />
            {!loading && (user
              ? <UserMenu />
              : (googleEnabled && (
                  <button className="btn btn-sm" onClick={login}>Sign in</button>
                )))}
          </div>
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>

      <footer className="site-footer">
        <div className="foot-inner">
          <span className="row">
            <span className="brand-mark" style={{ width: 24, height: 24, fontSize: '0.75rem' }}>✦</span>
            <b>StoryPlex</b>
          </span>
          <span className="nav-spacer" />
          <span>AI visual novels, woven from your premises.</span>
          <nav className="nav-links">
            <Link to="/legal/terms" className="nav-link">Terms</Link>
            <Link to="/legal/privacy" className="nav-link">Privacy</Link>
            <Link to="/legal/refunds" className="nav-link">Refunds</Link>
            <Link to="/legal/contact" className="nav-link">Contact</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
