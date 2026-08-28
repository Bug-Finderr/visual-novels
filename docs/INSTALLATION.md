# Installation Guide

Getting StoryPlex running on a clean machine. Two paths: **local development** (everything on your
laptop) and **production deployment** (Render + Google Cloud).

---

## 1. Prerequisites

| Requirement | Version | Why | Required? |
|---|---|---|---|
| Python | 3.10+ (3.14 used in development) | Backend | Yes |
| Node.js | 18+ | Frontend build | Yes |
| Docker Desktop | any current | Runs Postgres locally | Yes |
| Git | any | Cloning | Yes |
| Gemini API key | — | Story + image generation | Yes |
| Google OAuth client | — | Sign-in | For accounts |
| Silk/Mulberry TTS key | — | Character voices | Optional |
| Cashfree merchant account | — | Payments | Optional |

Without the optional keys the app still runs: stories generate and play, they're just silent, and
billing stays switched off.

## 2. Clone and configure

```bash
git clone <repo-url>
cd visual-novels
cp .env.example .env
```

Open `.env` and set, at minimum:

```bash
GEMINI_API_KEY=AIza...            # from https://aistudio.google.com/apikey
```

`.env` is git-ignored. Never commit real keys.

### Where the Gemini key comes from

Get it from **[AI Studio](https://aistudio.google.com/apikey)** — a `AIza…` key, 39 characters. This
project uses the AI Studio API, not Vertex AI, so no service account or ADC is needed for generation.

> The key needs **billing enabled with credits available**. A key whose prepay credits have run dry
> returns `429 RESOURCE_EXHAUSTED` and every generation fails.

## 3. Database

```bash
docker compose up -d          # starts Postgres 16 on localhost:5432
docker ps                     # confirm "storyplex-db ... (healthy)"
```

## 4. Backend

```bash
cd server
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head          # creates all 22 tables
./.venv/bin/python -m uvicorn app.main:app --port 3001 --reload
```

Check it:

```bash
curl http://localhost:3001/api/v1/health
# {"status":"ok","name":"storyplex-server"}
```

## 5. Frontend

In a second terminal, from the repo root:

```bash
npm install
npm run dev
```

Open **<http://localhost:3000>**. Vite proxies `/api/v1` to the backend, so no CORS setup is needed
in development.

## 6. Verify the install

```bash
cd server
./.venv/bin/python scripts/verify_models.py    # proves the Gemini key + models work
```

Expected: `ALL MODELS OK ✅`. If this fails, generation will fail — fix it before going further.

---

## Optional services

### Google sign-in

Without this, the app runs but nobody can sign in, so no stories can be created.

1. [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. **Create Credentials → OAuth client ID → Web application**
3. Authorised redirect URI: `http://localhost:3001/api/v1/auth/google/callback`
4. Authorised JavaScript origin: `http://localhost:3000`
5. Put the client id and secret in `.env`:

```bash
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3001/api/v1/auth/google/callback
SESSION_SECRET=$(openssl rand -hex 32)
```

### Character voices (TTS)

```bash
SILK_API_KEY=...
```

Omit it and generation skips the voice phase — text-only playback, everything else identical.

### Payments (Cashfree)

Sandbox credentials are issued at signup with **no KYC**, which is enough to test the whole payment
flow.

1. [merchant.cashfree.com](https://merchant.cashfree.com) → switch to **Sandbox**
2. **Developers → API Keys** → copy App ID and Secret Key (the secret starts `cfsk_ma_test_`)

```bash
BILLING_ENABLED=1
CASHFREE_ENV=sandbox
CASHFREE_APP_ID=TEST...
CASHFREE_SECRET_KEY=cfsk_ma_test_...
```

Test instruments: UPI `testsuccess@gocash` / `testfailure@gocash`; card `4444333322221111`, exp
`03/2028`, CVV `123`, OTP `111000`.

> Webhooks cannot reach `localhost`. Locally, payments settle through the return-URL path only.
> That is expected — the webhook is exercised in deployment, where the URL is public.

---

## Configuration reference

Everything below has a working default; set only what you need.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Story and image generation |
| `DATABASE_URL` | local docker Postgres | Connection string; `postgres://` is auto-rewritten |
| `STORYGEN_ENGINE` | `monolith` | `graph` enables the multi-agent pipeline |
| `MODEL_STORY` | `gemini-3-flash-preview` | Story bible model |
| `MODEL_DIALOGUE` | `gemini-3.1-flash-lite` | Beat/dialogue model |
| `MODEL_IMAGE` | `gemini-3.1-flash-lite-image` | Sprite/scene model |
| `MAX_CONCURRENT_GENERATIONS` | `3` | Concurrent pipelines; the rest queue |
| `BILLING_ENABLED` | `0` | `1` charges credits for generation |
| `FREE_STORY_CREDITS` | `2` | Granted once, on first account touch |
| `CREDITS_PER_GENERATION` | `1` | Credits per story |
| `REFUND_ON_GENERATION_FAILURE` | `0` | `1` refunds when a pipeline errors |
| `ASSET_BACKEND` | `local` | `gcs` to store generated assets in a bucket |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowlist (credentialed) |
| `SESSION_SECRET` | dev placeholder | **Must be overridden in production** |

Model ids are env-overridable deliberately: Google retires models on its own schedule, and when that
happens the fix should be a config change rather than a redeploy.

---

## Production deployment

Full runbook: **[DEPLOY-RENDER.md](../DEPLOY-RENDER.md)**. In outline:

1. **GCS bucket** for generated assets, plus a scoped service-account key
2. **Render Blueprint** — `render.yaml` declares Postgres, the Docker web service, and the static site
3. **DNS** — point the domain at Render; TLS is issued automatically
4. **Google OAuth** — add the production redirect URI
5. **Cashfree** — production keys, and register the webhook endpoint

Migrations run automatically on boot (`alembic upgrade head` in the container command), so a deploy
never needs a manual schema step.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `429 RESOURCE_EXHAUSTED` | Gemini prepay credits exhausted | Top up in AI Studio |
| `404 ... no longer available` | Model retired by Google | Set `MODEL_*` to a current id; run `verify_models.py` |
| Backend won't start, DB error | Postgres not running | `docker compose up -d` |
| Sign-in returns `redirect_uri_mismatch` | URI not registered | Add the exact URI in Google Console |
| Generation stuck at 0% | Session cookie not reaching the SSE stream | Confirm `ALLOWED_ORIGINS` matches the frontend origin |
| Sprites show a coloured background | Image model not honouring the chroma-key prompt | `verify_models.py` checks this directly |
| Story queued and not starting | At `MAX_CONCURRENT_GENERATIONS` | Expected — it starts when a slot frees |
