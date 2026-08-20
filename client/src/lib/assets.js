// Base URL for generated assets (covers, sprites, backgrounds, audio).
//
// Dev (default): '/game-assets', which Vite proxies to the backend's
//   /api/v1/assets routes (see vite.config.js).
// Prod: set VITE_ASSET_BASE to the public GCS/CDN base, e.g.
//   https://storage.googleapis.com/<bucket>  — the browser then loads assets
//   straight from the bucket/CDN. Asset paths ('{sessionId}/cover.png', …) are
//   exactly the storage keys, so base + path resolves in either environment.
export const ASSET_BASE = import.meta.env.VITE_ASSET_BASE || '/game-assets';

export function assetUrl(path) {
  return `${ASSET_BASE}/${path}`;
}
