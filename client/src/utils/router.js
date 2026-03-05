const routes = {};
let appContainer = null;

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

function handleRoute() {
  const hash = window.location.hash.slice(1) || '/';
  const segments = hash.split('/').filter(Boolean);
  const path = '/' + (segments[0] || '');
  const params = segments.slice(1);

  const route = routes[path] || routes['/'];
  if (route && appContainer) {
    appContainer.innerHTML = '';
    route(appContainer, params);
  }
}
