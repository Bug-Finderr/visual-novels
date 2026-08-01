import { Link, NavLink, Outlet } from 'react-router-dom';
import ThemeMenu from './ThemeMenu.jsx';

const navClass = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`;

/** Site chrome (nav + footer) wrapping the standard pages. The fullscreen
 *  reader route (/play/:id) renders outside this. */
export default function Layout() {
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
            <Link to="/create" className="btn btn-primary btn-sm">＋ New tale</Link>
            <ThemeMenu />
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
        </div>
      </footer>
    </div>
  );
}
