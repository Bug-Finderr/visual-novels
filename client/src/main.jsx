import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './lib/queryClient.js';
import { ThemeProvider } from './theme/ThemeContext.jsx';
import App from './App.jsx';

// Style layers: tokens → base → components → game (later wins on ties).
import './styles/theme.css';
import './styles/base.css';
import './styles/components.css';
import './styles/game.css';

// Note: no <StrictMode> — the VN engine is an imperative singleton that
// mounts/disposes around a real WebSocket + AudioContext; double-invoking
// effects in dev would churn those needlessly.
createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </QueryClientProvider>
);
