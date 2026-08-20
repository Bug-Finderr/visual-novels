# Deploying StoryPlex to Render (backend + frontend + DB, same-day demo)

Production topology:

```
  Browser
    │  static SPA                   ┌──────────────────────────────┐
    ├─────────────────────────────▶│ Render Static Site (client/dist)│
    │                                └──────────────────────────────┘
    │  REST + OAuth + WSS /api/v1  ┌────────────────────────────┐
    └────────────────────────────▶│ Render Web Service (FastAPI)│──▶ Render Postgres
                                    └────────────────────────────┘
```

- **Frontend**: Render Static Site serves the Vite build. Free regardless of the backend's paid plan — CDN + managed TLS + custom domains (2 free per workspace) included. (Netlify works too, and `netlify.toml` is still in the repo for that — but org-owned private repos hit Netlify's paid-plan wall, which is why this doc defaults to Render for both.)
- **Backend**: FastAPI on a Render Web Service (container in `server/Dockerfile`). Migrations run automatically on every boot (`alembic upgrade head` before `uvicorn` starts).
- **DB**: Render-managed Postgres, same platform/network as the web service.
- **Assets**: `ASSET_BACKEND=local` — generated images/audio are served straight off the web service's disk via `/api/v1/assets/...`. Simplest option, zero extra setup. They're **ephemeral**: a redeploy or restart wipes them (fine for a demo; add a Render Disk later if you need them to survive restarts — see the bottom of this doc).

> Unlike the GCP path in `DEPLOY.md`, Render doesn't freeze CPU between requests, so the `--no-cpu-throttling` / single-instance dance that Cloud Run needs isn't a thing here — just don't use the free instance tier for the backend (it sleeps after 15 min idle) and don't turn on autoscaling (the in-memory generation-progress dict only lives on one instance).

---

## Prerequisites

- A Render account with billing set up (the backend web service needs a paid plan — see below; the static site is free).
- Your secrets ready: `GEMINI_API_KEY`, `SILK_API_KEY`, Google OAuth `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
- This repo pushed to GitHub (Render deploys from a connected repo).

---

## 1. Deploy everything — via the `render.yaml` Blueprint

The repo root has a `render.yaml` that provisions the Postgres DB, the backend web service, **and** the frontend static site together, in one shot. The two services reference each other by their fixed names (`storyplex-api`, `storyplex-web`), so their URLs are predictable and pre-wired — no manual URL-copying between dashboards.

1. Push this branch (with `render.yaml`, `server/Dockerfile`, `server/app/config.py`) to your Git remote.
2. Render dashboard → **New + → Blueprint** → connect the repo.
3. Render reads `render.yaml` and shows the plan: Postgres (`storyplex-db`, free tier), a Web Service (`storyplex-api`, Standard plan, Docker), and a Static Site (`storyplex-web`, free).
4. Render prompts for the env vars marked `sync: false` — fill in:
   - `GEMINI_API_KEY`
   - `SILK_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
5. Click **Apply**. Render provisions Postgres, builds+deploys the backend container (runs `alembic upgrade head` then starts `uvicorn`), and builds+deploys the static site (`npm install && npm run build` → publishes `client/dist`).
6. Once both are live:
   - API: `https://storyplex-api.onrender.com`
   - App: `https://storyplex-web.onrender.com`

   (Render service names are globally unique — if either name was already taken by someone else, Render appends a suffix. If that happens, the blueprint's cross-referencing env vars — `GOOGLE_REDIRECT_URI`, `ALLOWED_ORIGINS` on the API; `VITE_API_BASE`, `VITE_ASSET_BASE` on the web service — won't match reality. Fix those three by hand in each service's Environment tab, which triggers a redeploy.)

**Why Standard plan for the backend, not free/Starter:** Render's free tier sleeps after 15 min idle, which would kill an in-progress generation (it's a detached background task tied to that one instance). Standard (2GB) gives real headroom beyond the app's ~115MB import baseline — sprite background removal is a plain numpy/PIL color-key with no ML model, so it's cheap even under full concurrency (profiled: a complete story's image load peaks around 570MB). $25/mo, cancel/downgrade after the demo if you don't need it running. The static site costs nothing regardless of which backend plan you pick.

**No Blueprint access, or you'd rather click through manually?** See "Manual dashboard steps" at the bottom.

---

## 2. Google OAuth client

In Google Cloud Console → **APIs & Services → Credentials → your OAuth client**, add:

- **Authorized redirect URI**: `https://storyplex-api.onrender.com/api/v1/auth/google/callback`
- **Authorized JavaScript origins**: `https://storyplex-web.onrender.com` and `https://storyplex-api.onrender.com`

(Use the actual URLs from step 1.6 if either got a name-collision suffix.)

---

## 3. Post-deploy smoke test

```bash
curl -s https://storyplex-api.onrender.com/api/v1/health
# {"status":"ok","name":"storyplex-server"}
curl -s https://storyplex-api.onrender.com/api/v1/me
# {"user":null,"googleAuthEnabled":true}
```

If `googleAuthEnabled` is `false`, double-check the Google secrets landed in `storyplex-api`'s Environment tab.

Then open `https://storyplex-web.onrender.com`, sign in with Google, create a story, hit Play — scene art/audio load from the backend, TTS streams over `wss://` directly to Render (a static site can't proxy WebSockets any more than Netlify could, which is why `VITE_API_BASE` points at the real backend origin, not a same-origin proxy path).

---

## Cookies note

`storyplex-web.onrender.com` and `storyplex-api.onrender.com` are different hosts under Render's multi-tenant domain, so the blueprint sets `SESSION_COOKIE_SAMESITE=none` + `SESSION_COOKIE_SECURE=1` — this relies on third-party cookies, which Safari blocks and Chrome is phasing out. Fine for today's demo. If this becomes a real deployment, put both services behind custom subdomains of **one domain you own** (`app.yourdomain.com` / `api.yourdomain.com` — 2 free custom domains are included per Render workspace) and switch to `SESSION_COOKIE_SAMESITE=lax`; same-registrable-domain cookies avoid the third-party-cookie problem entirely.

---

## Manual dashboard steps (if not using the Blueprint)

1. **New + → PostgreSQL**. Name it, pick a region, plan `Free` (or `Basic-256mb`, $6/mo, if you want it to outlive the 30-day free-tier expiry). Create it, then copy the **Internal Database URL** (same-region private network — faster, no egress cost) from its Info page.
2. **New + → Web Service** → connect the repo. Set:
   - **Runtime**: Docker
   - **Dockerfile path**: `server/Dockerfile`
   - **Docker build context**: `server`
   - **Plan**: Standard
   - **Health check path**: `/api/v1/health`
   - Env vars: same keys/values as `render.yaml`'s `storyplex-api` block, pasting the Postgres Internal Database URL from step 1 as `DATABASE_URL` as-is (the app auto-rewrites `postgresql://` to the `postgresql+psycopg://` driver form it needs).
3. **New + → Static Site** → connect the same repo. Set:
   - **Build command**: `npm install && npm run build`
   - **Publish directory**: `client/dist`
   - Env vars: `VITE_API_BASE` / `VITE_ASSET_BASE`, pointing at the web service's URL from step 2 (as in `render.yaml`'s `storyplex-web` block).
4. Back in the web service, set `ALLOWED_ORIGINS` to the static site's URL from step 3, and `GOOGLE_REDIRECT_URI` to its own `/api/v1/auth/google/callback` — then continue from step 2 (Google OAuth client) above.

## Optional: persist generated assets across restarts

Add a Render Disk to the web service (**Disks** tab): mount path `/app/data` (that's where `DATA_DIR`/`GENERATED_DIR` resolve inside the container — see `server/app/config.py`), a few GB. Generated sprites/backgrounds/audio then survive redeploys instead of regenerating each time. Not needed for a one-off demo.
