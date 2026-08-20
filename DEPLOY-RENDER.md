# Deploying StoryPlex to Render + Netlify (fastest path — same-day demo)

Production topology:

```
  Browser
    │  static SPA                 ┌─────────────────────────────┐
    ├───────────────────────────▶│ Netlify (client/dist)        │
    │                             └─────────────────────────────┘
    │  REST + OAuth + WSS /api/v1  ┌────────────────────────────┐
    └────────────────────────────▶│ Render Web Service (FastAPI)│──▶ Render Postgres
                                    └────────────────────────────┘
```

- **Frontend**: Netlify serves the Vite build (`netlify.toml` already configured).
- **Backend**: FastAPI on a Render Web Service (container in `server/Dockerfile`). Migrations run automatically on every boot (`alembic upgrade head` before `uvicorn` starts).
- **DB**: Render-managed Postgres, same platform/network as the web service.
- **Assets**: `ASSET_BACKEND=local` — generated images/audio are served straight off the web service's disk via `/api/v1/assets/...`. Simplest option, zero extra setup. They're **ephemeral**: a redeploy or restart wipes them (fine for a demo; add a Render Disk later if you need them to survive restarts — see the bottom of this doc).

> Unlike the GCP path in `DEPLOY.md`, Render doesn't freeze CPU between requests, so the `--no-cpu-throttling` / single-instance dance that Cloud Run needs isn't a thing here — just don't use the free instance tier (it sleeps after 15 min idle) and don't turn on autoscaling (the in-memory generation-progress dict only lives on one instance).

---

## Prerequisites

- A Render account (render.com) with billing set up (the web service needs a paid plan — see below).
- A Netlify account (or the `netlify` CLI).
- Your secrets ready: `GEMINI_API_KEY`, `SILK_API_KEY`, Google OAuth `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
- This repo pushed to GitHub/GitLab (Render deploys from a connected repo).

---

## 1. Deploy the backend — via the `render.yaml` Blueprint

The repo root has a `render.yaml` that provisions the web service + Postgres together in one shot.

1. Push this branch (with `render.yaml`, the updated `server/Dockerfile`, and `server/app/config.py`) to your Git remote.
2. In the Render dashboard: **New + → Blueprint**.
3. Connect the repo and select it. Render reads `render.yaml` and shows you a plan: one Postgres database (`storyplex-db`, free tier) and one Web Service (`storyplex-api`, Standard plan, Docker runtime pointed at `server/Dockerfile`).
4. Render will prompt you for the env vars marked `sync: false` in the blueprint — fill in:
   - `GEMINI_API_KEY`
   - `SILK_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `ALLOWED_ORIGINS` — leave blank for now, you'll set it in step 4 below once Netlify exists.
5. Click **Apply**. Render provisions the Postgres instance, builds the Docker image, runs the container (which runs `alembic upgrade head` automatically, then starts `uvicorn`).
6. Once it's live, your API URL is `https://storyplex-api.onrender.com` (or check the exact URL in the service's dashboard page — Render appends a suffix if that name is already taken by someone else).

**Why Standard plan, not free/Starter:** this backend loads `onnxruntime` + `rembg` for sprite background-removal, which alone eats a few hundred MB at import time. Render's free tier (sleeps after 15 min idle) and Starter tier (512MB RAM) both risk breaking mid-generation or mid-demo. Standard (2GB) matches what `DEPLOY.md` already provisions on Cloud Run for the same reason. If you don't have a Render Blueprint plan restriction preventing Standard, keep it — it's $25/mo, cancel/downgrade after the demo if you don't need it running.

**No Blueprint access, or you'd rather click through manually?** See "Manual dashboard steps" at the bottom.

---

## 2. Smoke-test the backend

```bash
curl -s https://storyplex-api.onrender.com/api/v1/health
# {"status":"ok","name":"storyplex-server"}
curl -s https://storyplex-api.onrender.com/api/v1/me
# {"user":null,"googleAuthEnabled":true}
```

If `googleAuthEnabled` is `false`, double-check `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` landed in the service's Environment tab.

---

## 3. Deploy the frontend to Netlify

`netlify.toml` (repo root) already sets `base=client`, `command=npm run build`, `publish=client/dist`, and the SPA fallback.

1. Netlify UI → **Add new site → Import an existing project** → connect the repo.
2. Netlify auto-detects `netlify.toml`. Before the first deploy (or right after, then redeploy), set in **Site settings → Environment variables**:
   ```
   VITE_API_BASE   = https://storyplex-api.onrender.com/api/v1
   VITE_ASSET_BASE = https://storyplex-api.onrender.com/api/v1/assets
   ```
   (Use your actual Render URL from step 1.6 if it got a suffix.)
3. Deploy. Note the site URL — either the random `*.netlify.app` one, or set a custom subdomain in **Site settings → Domain management** for something more demo-friendly (e.g. `storyplex-demo.netlify.app`).

---

## 4. Wire the two together — set `ALLOWED_ORIGINS` on Render

Back in the Render dashboard, `storyplex-api` → **Environment**:

```
ALLOWED_ORIGINS = https://<your-netlify-site>.netlify.app
```

Save — Render redeploys automatically with the new value. This is also the post-login redirect target, so Google sign-in lands back on the right site.

---

## 5. Google OAuth client

In Google Cloud Console → **APIs & Services → Credentials → your OAuth client**, add:

- **Authorized redirect URI**: `https://storyplex-api.onrender.com/api/v1/auth/google/callback`
- **Authorized JavaScript origins**: `https://<your-netlify-site>.netlify.app` and `https://storyplex-api.onrender.com`

---

## 6. Post-deploy smoke test

```bash
curl -s https://storyplex-api.onrender.com/api/v1/health
```

Then open the Netlify URL, sign in with Google, create a story, hit Play — scene art/audio load from the Render backend, TTS streams over `wss://` directly to Render (Netlify can't proxy WebSockets, which is why `VITE_API_BASE` points at the real Render origin rather than a Netlify proxy path).

---

## Cookies note

Netlify (`*.netlify.app`) and Render (`*.onrender.com`) are different sites, so the blueprint sets `SESSION_COOKIE_SAMESITE=none` + `SESSION_COOKIE_SECURE=1` — this relies on third-party cookies, which Safari blocks and Chrome is phasing out. Fine for today's demo; if this becomes a real deployment, put both behind one root domain (`app.yourdomain.com` / `api.yourdomain.com`) and switch to `SESSION_COOKIE_SAMESITE=lax`.

---

## Manual dashboard steps (if not using the Blueprint)

1. **New + → PostgreSQL**. Name it, pick a region, plan `Free` (or `Basic-256mb`, $6/mo, if you want it to outlive the 30-day free-tier expiry). Create it, then copy the **Internal Database URL** (same-region private network — faster, no egress cost) from its Info page.
2. **New + → Web Service** → connect the repo. Set:
   - **Runtime**: Docker
   - **Dockerfile path**: `server/Dockerfile`
   - **Docker build context**: `server`
   - **Plan**: Standard
   - **Health check path**: `/api/v1/health`
3. In the new service's **Environment** tab, add every var listed in `render.yaml`'s `envVars` (same keys/values), pasting the Postgres Internal Database URL from step 1 as `DATABASE_URL` — the app now auto-rewrites `postgresql://` to the `postgresql+psycopg://` driver form it needs, so paste it as-is.
4. Deploy, then continue from step 2 above.

## Optional: persist generated assets across restarts

Add a Render Disk to the web service (**Disks** tab): mount path `/app/data` (that's where `DATA_DIR`/`GENERATED_DIR` resolve inside the container — see `server/app/config.py`), a few GB. Generated sprites/backgrounds/audio then survive redeploys instead of regenerating each time. Not needed for a one-off demo.
