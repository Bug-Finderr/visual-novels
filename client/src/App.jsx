import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Landing from './pages/Landing.jsx';
import Explore from './pages/Explore.jsx';
import Library from './pages/Library.jsx';
import Setup from './pages/Setup.jsx';
import Loading from './pages/Loading.jsx';
import Game from './pages/Game.jsx';
import Settings from './pages/Settings.jsx';
import NotFound from './pages/NotFound.jsx';

export default function App() {
  return (
    <Routes>
      {/* Standard pages share the site chrome */}
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/library" element={<Library />} />
        <Route path="/create" element={<Setup />} />
        <Route path="/loading/:id" element={<Loading />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      {/* Fullscreen immersive reader — no nav/footer */}
      <Route path="/play/:id" element={<Game />} />
    </Routes>
  );
}
