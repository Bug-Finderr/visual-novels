const routes = {};
let appContainer = null;
let currentCleanups = [];

export function registerRoute(path, renderFn) {
  routes[path] = renderFn;
}

export function navigate(path) {
  window.location.hash = path;
}

export function initRouter(container) {
  appContainer = container;
  window.addEventListener('hashchange', handleRoute);
  handleRoute();
}

/**
 * Views can register cleanup functions that run before the next route swap.
 * Multiple registrations accumulate; all run in registration order.
 */
export function onRouteCleanup(fn) {
  if (typeof fn === 'function') currentCleanups.push(fn);
}

function handleRoute() {
  const hash = window.location.hash.slice(1) || '/';
  const segments = hash.split('/').filter(Boolean);
  const path = '/' + (segments[0] || '');
  const params = segments.slice(1);

  for (const fn of currentCleanups) {
    try { fn(); } catch (e) { console.warn('Route cleanup failed:', e); }
  }
  currentCleanups = [];

  const route = routes[path] || routes['/'];
  if (route && appContainer) {
    appContainer.innerHTML = '';
    window.scrollTo(0, 0);
    route(appContainer, params);
  }
}
