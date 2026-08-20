# Deploying StoryPlex to Render (backend + frontend + DB, same-day demo)

Production topology:

```
  Browser
    │  static SPA                   ┌──────────────────────────────┐
    ├─────────────────────────────▶│ Render Static Site (client/dist)│
    │                                └──────────────────────────────┘
    │  REST + OAuth + WSS /api/v1  ┌────────────────────────────┐
    ├────────────────────────────▶│ Render Web Service (FastAPI)│──▶ Render Postgres
    │                               └────────────────────────────┘
    │  images / audio (public URLs) ┌───────────────────────────┐
    └─────────────────────────────▶│ GCS bucket (storyplex-assets)│
                                    └───────────────────────────┘
```

- **Frontend**: Render Static Site serves the Vite build. Free regardless of the backend's paid plan — CDN + managed TLS + custom domains (2 free per workspace) included. (Netlify works too, and `netlify.toml` is still in the repo for that — but org-owned private repos hit Netlify's paid-plan wall, which is why this doc defaults to Render for both.)
- **Backend**: FastAPI on a Render Web Service (container in `server/Dockerfile`). Migrations run automatically on every boot (`alembic upgrade head` before `uvicorn` starts).
- **DB**: Render-managed Postgres, same platform/network as the web service.
- **Assets**: `ASSET_BACKEND=gcs` — generated images/audio go to a **public** GCS bucket (`storyplex-assets`); the browser loads them straight from the bucket via `VITE_ASSET_BASE`, the backend only writes them. Survives redeploys/restarts (unlike the web service's own disk, which is ephemeral). Since Render isn't running on GCP, the backend authenticates with a service-account key rather than automatic credentials — see step 1a below.

> Unlike the GCP path in `DEPLOY.md`, Render doesn't freeze CPU between requests, so the `--no-cpu-throttling` / single-instance dance that Cloud Run needs isn't a thing here — just don't use the free instance tier for the backend (it sleeps after 15 min idle) and don't turn on autoscaling (the in-memory generation-progress dict only lives on one instance).

---

## Prerequisites

- A Render account with billing set up (the backend web service needs a paid plan — see below; the static site is free).
- Your secrets ready: `GEMINI_API_KEY`, `SILK_API_KEY`, Google OAuth `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
- This repo pushed to GitHub (Render deploys from a connected repo).

---

## 1. GCS bucket + service account (one-time, before the Blueprint)

The bucket and its access grant aren't declared in `render.yaml` (they're GCP resources, and the credential is a secret) — set these up once first:

1. **Bucket**: `storyplex-assets` already exists (created for the earlier GCP deploy path in `DEPLOY.md`) with public read already granted (`allUsers: roles/storage.objectViewer`). Creating a fresh one, if you ever need to: `gcloud storage buckets create gs://<name> --location=<region> --uniform-bucket-level-access`, then `gcloud storage buckets add-iam-policy-binding gs://<name> --member=allUsers --role=roles/storage.objectViewer`.
2. **Service account** (Render isn't on GCP, so it can't use automatic credentials the way Cloud Run does): create one scoped to just this bucket, not the whole project:
   ```bash
   gcloud iam service-accounts create storyplex-render-assets \
     --display-name="StoryPlex Render backend - GCS asset access"
   gcloud storage buckets add-iam-policy-binding gs://storyplex-assets \
     --member="serviceAccount:storyplex-render-assets@<PROJECT_ID>.iam.gserviceaccount.com" \
     --role="roles/storage.objectAdmin"
   ```
3. **Key**: `gcloud iam service-accounts keys create key.json --iam-account=storyplex-render-assets@<PROJECT_ID>.iam.gserviceaccount.com`. If this fails with `FAILED_PRECONDITION: Key creation is not allowed on this service account`, an org policy (`constraints/iam.disableServiceAccountKeyCreation`) is blocking it — an Organization Policy Administrator needs to run `gcloud resource-manager org-policies disable-enforce constraints/iam.disableServiceAccountKeyCreation --project=<PROJECT_ID>` to scope an exception to just this project (allow a minute or two for it to propagate before retrying the key creation).
4. **Upload the key to Render as a Secret File** — this step can't be scripted into `render.yaml` (Blueprints don't support declaring Secret File contents in YAML). In the `storyplex-api` service → **Environment → Secret Files → Add Secret File**: path `/etc/secrets/gcs-key.json`, contents = the full JSON from `key.json`. Delete your local copy of `key.json` afterward — it's a live credential.

## 2. Deploy everything — via the `render.yaml` Blueprint

The repo root has a `render.yaml` that provisions the Postgres DB, the backend web service, **and** the frontend static site together, in one shot. The two services reference each other by their fixed names (`storyplex-api`, `storyplex-web`), so their URLs are predictable and pre-wired — no manual URL-copying between dashboards.

1. Push this branch (with `render.yaml`, `server/Dockerfile`, `server/app/config.py`) to your Git remote.
2. Render dashboard → **New + → Blueprint** → connect the repo.
3. Render reads `render.yaml` and shows the plan: Postgres (`storyplex-db`, free tier), a Web Service (`storyplex-api`, Standard plan, Docker), and a Static Site (`storyplex-web`, free).
4. Render prompts for the env vars marked `sync: false` — fill in:
   - `GEMINI_API_KEY`
   - `SILK_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
5. Click **Apply**. Render provisions Postgres, builds+deploys the backend container (runs `alembic upgrade head` then starts `uvicorn`), and builds+deploys the static site (`npm install && npm run build` → publishes `client/dist`). Because `render.yaml` declares `domains:` on both services, Render will also register `storyplex.app` and `api.storyplex.app` against each — but they stay in an unverified/pending state until the DNS records in step 3 exist.
6. Add the Secret File from step 1.4 if you haven't already — `GOOGLE_APPLICATION_CREDENTIALS` won't resolve to anything until that file exists, and asset uploads will fail (story generation will still complete, but sprites/backgrounds/audio won't save).
7. Each service also keeps its default `*.onrender.com` URL live (`storyplex-api.onrender.com`, `storyplex-web.onrender.com`) — useful for testing before DNS/custom domains are verified.

**Why Standard plan for the backend, not free/Starter:** Render's free tier sleeps after 15 min idle, which would kill an in-progress generation (it's a detached background task tied to that one instance). Standard (2GB) gives real headroom beyond the app's ~115MB import baseline — sprite background removal is a plain numpy/PIL color-key with no ML model, so it's cheap even under full concurrency (profiled: a complete story's image load peaks around 570MB). $25/mo, cancel/downgrade after the demo if you don't need it running. The static site costs nothing regardless of which backend plan you pick.

**No Blueprint access, or you'd rather click through manually?** See "Manual dashboard steps" at the bottom.

---

## 3. Point `storyplex.app` (GoDaddy) at Render

Domain is registered at GoDaddy. Two records needed — one for the apex domain (frontend), one for the `api` subdomain (backend):

1. Render dashboard → `storyplex-web` → **Settings → Custom Domains** → find `storyplex.app` (already listed as pending from the Blueprint's `domains:` field, or add it if using the manual path) → note the record Render wants for the apex — typically an **A record** to a specific IP, since bare `CNAME` isn't valid at a zone apex. Render's UI shows the exact current value; use that over any value written down elsewhere, in case it's changed.
2. Render dashboard → `storyplex-api` → **Settings → Custom Domains** → `api.storyplex.app` → note the **CNAME** target it wants (subdomains can use CNAME normally).
3. **GoDaddy** → your domain → **DNS** → **Manage DNS**:
   - Edit (or add) the record for `@` (GoDaddy's way of saying the apex/root) to the **A record** Render showed you.
   - Add a new record: Type `CNAME`, Name `api`, Value = the target Render showed you.
   - Delete any existing `AAAA` records on either — Render uses IPv4, and leftover AAAA records are a common source of verification failures.
4. Back in Render, click **Verify** on each domain once DNS propagates (GoDaddy's default TTL is often ~1hr, but changes are frequently visible in minutes — Render's verify button just tells you if it isn't ready yet, safe to retry). TLS certificates are issued and renewed automatically once verified.

---

## 4. Google OAuth client

In Google Cloud Console → **APIs & Services → Credentials → your OAuth client**, add:

- **Authorized redirect URI**: `https://api.storyplex.app/api/v1/auth/google/callback`
- **Authorized JavaScript origins**: `https://storyplex.app` and `https://api.storyplex.app`

---

## 5. Post-deploy smoke test

```bash
curl -s https://api.storyplex.app/api/v1/health
# {"status":"ok","name":"storyplex-server"}
curl -s https://api.storyplex.app/api/v1/me
# {"user":null,"googleAuthEnabled":true}
```

If `googleAuthEnabled` is `false`, double-check the Google secrets landed in `storyplex-api`'s Environment tab.

Then open `https://storyplex.app`, sign in with Google, create a story, hit Play — scene art/audio load straight from the GCS bucket (`VITE_ASSET_BASE`), TTS streams over `wss://` directly to the backend (a static site can't proxy WebSockets any more than Netlify could, which is why `VITE_API_BASE` points at the real backend origin, not a same-origin proxy path). If images 404 or never appear, check `storyplex-api`'s logs for GCS auth errors — usually means the Secret File from step 1.4 is missing or has the wrong path.

---

## Cookies note

`storyplex.app` and `api.storyplex.app` share one registrable domain, so the session cookie is same-site — `SESSION_COOKIE_SAMESITE=lax` + `SESSION_COOKIE_SECURE=1`, no reliance on third-party cookies. (Earlier, before the custom domain was wired up, this ran on the raw `*.onrender.com` URLs for both services, which are different sites from the cookie's perspective — that needed `SameSite=none`, which works but depends on third-party cookies Safari blocks and Chrome is phasing out. If you ever go back to testing on the bare `onrender.com` URLs, switch this back to `none`.)

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
   - Env vars: `VITE_API_BASE` (web service URL from step 2 + `/api/v1`) and `VITE_ASSET_BASE` (`https://storage.googleapis.com/storyplex-assets`).
4. Back in the web service, set `ALLOWED_ORIGINS` to the static site's URL from step 3, and `GOOGLE_REDIRECT_URI` to its own `/api/v1/auth/google/callback` — then continue from step 1 (GCS bucket + service account), step 3 (custom domain / GoDaddy DNS), and step 4 (Google OAuth client) above.

## Local dev vs. this deploy

Nothing changes locally — `ASSET_BACKEND` defaults to `local` when unset, so `npm run dev` still serves generated assets off disk through Vite exactly as before. `ASSET_BACKEND=gcs` only needs to be set in the Render environment.
