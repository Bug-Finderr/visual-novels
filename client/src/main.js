import { registerRoute, initRouter } from './utils/router.js';
import { renderLanding } from './views/landing.js';
import { renderSetupWizard } from './views/setup-wizard.js';
import { renderLoading } from './views/loading.js';
import { renderGame } from './views/game.js';
import { renderSessions } from './views/sessions.js';

// Register routes
registerRoute('/', renderLanding);
registerRoute('/setup', renderSetupWizard);
registerRoute('/loading', renderLoading);
registerRoute('/game', renderGame);
registerRoute('/sessions', renderSessions);

// Start
const app = document.getElementById('app');
initRouter(app);
