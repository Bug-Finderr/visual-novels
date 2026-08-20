import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Landing from './pages/Landing.jsx';
import Explore from './pages/Explore.jsx';
import Library from './pages/Library.jsx';
import StoryDetail from './pages/StoryDetail.jsx';
import Profile from './pages/Profile.jsx';
import Setup from './pages/Setup.jsx';
import Loading from './pages/Loading.jsx';
import Game from './pages/Game.jsx';
import Settings from './pages/Settings.jsx';
import Billing from './pages/Billing.jsx';
import PaymentReturn from './pages/PaymentReturn.jsx';
import Terms from './pages/legal/Terms.jsx';
import Privacy from './pages/legal/Privacy.jsx';
import Refunds from './pages/legal/Refunds.jsx';
import Contact from './pages/legal/Contact.jsx';
import NotFound from './pages/NotFound.jsx';

export default function App() {
  return (
    <Routes>
      {/* Standard pages share the site chrome */}
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/story/:id" element={<StoryDetail />} />
        <Route path="/u/:handle" element={<Profile />} />
        <Route path="/library" element={<Library />} />
        <Route path="/create" element={<Setup />} />
        <Route path="/loading/:id" element={<Loading />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/billing" element={<Billing />} />
        {/* Cashfree sends the browser back here after checkout */}
        <Route path="/billing/return" element={<PaymentReturn />} />
        {/* Published policies — required for the payment gateway to stay active */}
        <Route path="/legal/terms" element={<Terms />} />
        <Route path="/legal/privacy" element={<Privacy />} />
        <Route path="/legal/refunds" element={<Refunds />} />
        <Route path="/legal/contact" element={<Contact />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      {/* Fullscreen immersive reader — no nav/footer */}
      <Route path="/play/:id" element={<Game />} />
    </Routes>
  );
}
