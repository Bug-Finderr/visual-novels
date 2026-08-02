// Dev (default): '/api/v1', which Vite proxies to the backend. Prod: set
// VITE_API_BASE to the Cloud Run origin + version, e.g.
// https://storyplex-api-xxxx.run.app/api/v1 (the SPA on Netlify talks to
// Cloud Run cross-origin; fetch sends credentials so the session cookie rides).
const BASE = import.meta.env.VITE_API_BASE || '/api/v1';

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // send the session cookie
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  delete: (path) => request('DELETE', path),

  /**
   * Connect to an SSE endpoint. Returns an EventSource.
   * @param {string} path - API path
   * @param {function} onMessage - called with parsed JSON data
   * @param {function} onError - called on error
   */
  sse(path, onMessage, onError) {
    const source = new EventSource(`${BASE}${path}`);
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('SSE parse error:', e);
      }
    };
    source.onerror = (err) => {
      if (onError) onError(err);
      source.close();
    };
    return source;
  },
};
