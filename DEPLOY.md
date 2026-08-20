# Deploying StoryPlex to GCP + Netlify

Production topology:

```
  Browser
    │  static SPA                 ┌─────────────────────────────┐
    ├───────────────────────────▶│ Netlify (client/dist)        │
    │                             └─────────────────────────────┘
    │  REST + OAuth + WSS /api/v1  ┌────────────────────────────┐
    ├────────────────────────────▶│ Cloud Run (FastAPI)         │──▶ Cloud SQL (Postgres)
    │                              └────────────────────────────┘
    │  images / audio (public URLs) ┌───────────────────────────┐
    └─────────────────────────────▶│ GCS bucket (+ optional CDN) │
                                    └───────────────────────────┘
```

- **Frontend**: Netlify serves the Vite build. Talks to Cloud Run cross-origin via `VITE_API_BASE`; loads generated assets from the public bucket via `VITE_ASSET_BASE`.
- **Backend**: FastAPI on Cloud Run (container in `server/Dockerfile`). Everything under `/api/v1`, including the TTS WebSocket.
- **DB**: Cloud SQL for Postgres, reached over the unix socket Cloud Run mounts.
- **Assets**: generated images + audio go to a **public** GCS bucket (`ASSET_BACKEND=gcs`). The browser fetches them straight from the bucket/CDN.

> The code already supports both modes. Locally nothing changes: with no env set, `ASSET_BACKEND=local` and the app serves assets off disk through Vite — exactly as in dev.

---

## ⚠️ Two constraints that shape the Cloud Run config

1. **Generation runs in a detached background task.** `POST /api/v1/sessions/{id}/generate` fires an `asyncio` task and returns immediately; progress lives in an **in-memory dict** the SSE endpoint reads. On Cloud Run this means:
   - deploy with **`--no-cpu-throttling`** (CPU stays allocated so the background task keeps running after the POST returns), and
   - run a **single instance** (`--min-instances=1 --max-instances=1`) so the detached task and its in-memory progress are on the same instance the SSE request hits.
   - _Future scaling_ (multi-instance) requires persisting progress to the DB and moving generation to a Cloud Run **Job** / worker. Fine to defer.
2. **Netlify can't proxy WebSockets.** The TTS WS therefore connects **directly** to Cloud Run — `VITE_API_BASE` must be the real Cloud Run origin (not a Netlify proxy path). This is already handled in `game-bridge.js`.

---

## Prerequisites

- `gcloud` CLI (`gcloud auth login`, `gcloud config set project <PROJECT_ID>`), a GCP project with **billing enabled**.
- A Netlify account + the `netlify` CLI (or connect the Git repo in the Netlify UI).
- Your existing secrets: `GEMINI_API_KEY`, `SILK_API_KEY`, Google OAuth `CLIENT_ID`/`CLIENT_SECRET`.

```bash
export PROJECT_ID=your-project
export REGION=us-central1
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com
```

---

## 1. Cloud SQL (Postgres)

```bash
gcloud sql instances create storyplex-db \
  --database-version=POSTGRES_16 --tier=db-f1-micro --region="$REGION"

gcloud sql databases create storyplex --instance=storyplex-db
gcloud sql users create storyplex --instance=storyplex-db --password='CHOOSE_A_STRONG_PASSWORD'

# Connection name — you'll need it below (PROJECT:REGION:INSTANCE):
gcloud sql instances describe storyplex-db --format='value(connectionName)'
```

## 2. GCS bucket (public, for generated assets)

```bash
export BUCKET=storyplex-assets           # must be globally unique
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
  --uniform-bucket-level-access

# Make objects world-readable (they're story covers/sprites/audio):
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member=allUsers --role=roles/storage.objectViewer

# (Optional) CORS — only needed if the browser ever fetch()es assets; <img>/WSS don't.
gcloud storage buckets update "gs://$BUCKET" --cors-file=deploy/gcs-cors.json
```

Public base URL is `https://storage.googleapis.com/$BUCKET` (or put Cloud CDN / a custom domain in front and set `GCS_PUBLIC_BASE`).

## 3. Secrets (Secret Manager)

```bash
printf '%s' "$GEMINI_API_KEY"        | gcloud secrets create gemini-api-key       --data-file=-
printf '%s' "$SILK_API_KEY"          | gcloud secrets create silk-api-key         --data-file=-
printf '%s' "$GOOGLE_CLIENT_SECRET"  | gcloud secrets create google-client-secret --data-file=-
printf '%s' "$(openssl rand -hex 32)"| gcloud secrets create session-secret       --data-file=-
printf '%s' 'THE_DB_PASSWORD'        | gcloud secrets create db-password          --data-file=-
```

Grant the Cloud Run runtime service account `roles/secretmanager.secretAccessor` and `roles/cloudsql.client` (the default compute SA works to start).

## 4. Deploy the backend to Cloud Run

Deploy from source (Cloud Build reads `server/Dockerfile`). `DATABASE_URL` uses the mounted Cloud SQL socket; substitute your connection name.

```bash
export CONN=$(gcloud sql instances describe storyplex-db --format='value(connectionName)')

gcloud run deploy storyplex-api \
  --source=server \
  --region="$REGION" \
  --allow-unauthenticated \
  --add-cloudsql-instances="$CONN" \
  --no-cpu-throttling \
  --min-instances=1 --max-instances=1 \
  --memory=2Gi --cpu=2 --timeout=3600 \
  --set-env-vars="ASSET_BACKEND=gcs,GCS_BUCKET=$BUCKET,STORYGEN_ENGINE=graph,SESSION_COOKIE_SECURE=1,SESSION_COOKIE_SAMESITE=lax" \
  --set-env-vars="DATABASE_URL=postgresql+psycopg://storyplex:$(gcloud secrets versions access latest --secret=db-password)@/storyplex?host=/cloudsql/$CONN" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,SILK_API_KEY=silk-api-key:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,SESSION_SECRET=session-secret:latest" \
  --set-env-vars="GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com"
```

Grab the service URL:

```bash
export API_URL=$(gcloud run services describe storyplex-api --region="$REGION" --format='value(status.url)')
echo "$API_URL"
```

Then set the two URL-dependent vars now that you know `$API_URL` and the SPA origin (fill `$APP_URL` after step 6, or redeploy):

```bash
gcloud run services update storyplex-api --region="$REGION" \
  --update-env-vars="GOOGLE_REDIRECT_URI=$API_URL/api/v1/auth/google/callback,ALLOWED_ORIGINS=$APP_URL"
```

## 5. Run database migrations

Run Alembic once against Cloud SQL (a Cloud Run **Job** on the same image, or from Cloud Shell via the Cloud SQL Auth Proxy):

```bash
gcloud run jobs create storyplex-migrate \
  --source=server --region="$REGION" \
  --add-cloudsql-instances="$CONN" \
  --set-env-vars="DATABASE_URL=postgresql+psycopg://storyplex:$(gcloud secrets versions access latest --secret=db-password)@/storyplex?host=/cloudsql/$CONN" \
  --command=python --args=-m,alembic,upgrade,head
gcloud run jobs execute storyplex-migrate --region="$REGION" --wait
```

## 6. Deploy the frontend to Netlify

`netlify.toml` (repo root) already sets `base=client`, `command=npm run build`, `publish=client/dist`, and the SPA fallback. Set the two build-time vars in the Netlify UI (**Site settings → Environment variables**):

```
VITE_API_BASE   = <API_URL>/api/v1
VITE_ASSET_BASE = https://storage.googleapis.com/<BUCKET>
```

Then deploy (connect the repo for CI, or `netlify deploy --build --prod`). Note the site URL as `$APP_URL`, and run the step-4 `update-env-vars` command so the backend knows the SPA origin.

## 7. Google OAuth client

In **APIs & Services → Credentials → your OAuth client**, add:

- **Authorized redirect URI**: `<API_URL>/api/v1/auth/google/callback`
- **Authorized JavaScript origins**: `<APP_URL>` and `<API_URL>`

---

## Cookies & domains (read this)

The session cookie is set by the API (Cloud Run) and sent on credentialed XHR from the SPA (Netlify).

- **Recommended: custom domain, same root.** Put the app on `app.example.com` (Netlify) and the API on `api.example.com` (Cloud Run custom domain). They share the registrable domain `example.com`, so the cookie stays **`SameSite=Lax; Secure`** (keep `SESSION_COOKIE_SAMESITE=lax`) and everything is first-/same-site — no third-party-cookie problems.
- **Raw hosts (`*.netlify.app` + `*.run.app`).** These are different sites, so auth needs a **cross-site** cookie: set `SESSION_COOKIE_SAMESITE=none` (with `SESSION_COOKIE_SECURE=1`). This works but relies on third-party cookies, which Safari blocks and Chrome is phasing out — fine for a demo, not durable. Prefer the custom domain for real use.

CORS is already credentialed and pinned to `ALLOWED_ORIGINS` (first entry doubles as the post-login redirect target).

---

## Post-deploy smoke test

```bash
curl -s "$API_URL/api/v1/health"                       # {"status":"ok",...}
curl -s "$API_URL/api/v1/sessions?sort=new" | head -c 200
# open $APP_URL, sign in with Google, open a story, hit Play (scene art from the
# bucket, TTS over wss to Cloud Run), like/rate/comment.
```

## Cost / scaling notes

- One always-warm `db-f1-micro` + a single small Cloud Run instance + a bucket is a few dollars/month at low traffic. Scale the SQL tier and Cloud Run CPU/memory as needed.
- To go multi-instance later: persist generation progress to Postgres (drop the in-memory `_progress` dict) and move the pipeline to a Cloud Run Job, then raise `--max-instances` and remove the single-instance constraint.
