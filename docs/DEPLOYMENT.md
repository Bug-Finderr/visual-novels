# Deployment plan — Netlify (frontend) + Render/Fly (backend)

Short version: Netlify can host the Vite frontend cleanly. It **cannot** host
the FastAPI backend as-is — Netlify Functions are stateless, time-limited,
and don't support persistent WebSockets, which we need for both Mulberry's
TTS stream and the planned chapter pipeline. So we split: static on Netlify,
backend on a long-running host (Render, Fly.io, or Railway).

---

## Frontend → Netlify (straightforward)

The client is a static SPA bundle once `vite build` runs.

### Build settings

```
Base directory:    client
Build command:     npm install && npm run build
Publish directory: client/dist
```

### What needs to change in the code

1. **API base URL** — currently the client calls `/api/...` and relies on
   Vite's dev proxy. In production, the backend is on a different origin,
   so we need an env-var-driven base URL.

   `client/src/services/api.js` already centralizes fetch. Add:

   ```js
   const API_BASE = import.meta.env.VITE_API_BASE || '';
   ```

   and prepend it to every URL.

2. **WebSocket URL** — `game-bridge.js` constructs the TTS WS as

   ```js
   const url = `${proto}//${location.host}/api/sessions/${sid}/tts/stream`;
   ```

   In prod the WS host is the backend host, not `location.host`. Same env var:

   ```js
   const wsBase = import.meta.env.VITE_WS_BASE || `${proto}//${location.host}`;
   const url = `${wsBase}/api/sessions/${sid}/tts/stream`;
   ```

3. **Game assets** (sprites, backgrounds, audio) — currently `/game-assets/...`
   via the Vite proxy → `/api/assets/...` on the backend. Either:
   - Make `/game-assets` also go to `${API_BASE}/api/assets/...`, or
   - Drop the `/game-assets` rewrite entirely and just call `/api/assets/...`.

### Netlify env vars

```
VITE_API_BASE = https://storyplex-api.your-host.com
VITE_WS_BASE  = wss://storyplex-api.your-host.com
```

### Netlify build env

Node 20 LTS is fine. No special build plugins needed.

### Optional: pretty URLs

Add `client/public/_redirects`:

```
/*    /index.html   200
```

so the SPA router works on hard-reloads of `/sessions`, `/game/{id}`, etc.

---

## Backend → not Netlify. Pick one of these.

### Why not Netlify Functions

- **No persistent WebSocket support** — TTS streaming relies on a long-lived
  WS to Mulberry + a long-lived WS to the browser.
- **10 s execution cap** on the free / starter tiers — sprite + scene
  generation alone takes minutes.
- **No persistent disk** — we write sprites, backgrounds, and WAVs to
  `data/generated/<sid>/`. Functions get an ephemeral filesystem.
- **SQLite needs a real disk** — not viable on serverless.

### Recommended: Render

| Item | Setting |
| --- | --- |
| Service type | Web Service |
| Runtime | Python 3.11 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Root directory | `server` |
| Plan | Starter ($7/mo) — persistent disk + WS support |
| Persistent Disk | mount at `/var/data` → set `DATA_DIR` env var to match |

### Render env vars

```
GEMINI_API_KEY     = ...
SILK_API_KEY       = ...
SILK_API_URL       = https://silk-api.rumik.ai   (default)
SILK_MODEL         = mulberry                    (default)
DATA_DIR           = /var/data                   (so SQLite + generated/ persist)
PORT               = 10000                       (Render's default; uvicorn reads this)
```

### Alternative: Fly.io

Similar story, slightly cheaper, more configuration up front.
`fly.toml` example:

```toml
app = "storyplex"

[build]
  dockerfile = "Dockerfile"

[env]
  DATA_DIR = "/data"
  PORT = "8080"

[mounts]
  source = "storyplex_data"
  destination = "/data"

[[services]]
  internal_port = 8080
  protocol = "tcp"
  [[services.ports]]
    handlers = ["http"]
    port = 80
  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443
  [services.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20
```

### Alternative: Railway

`railway init` + add a volume; identical pattern.

---

## Code changes required for deployment

1. **`server/app/config.py`** — make `DATA_DIR` env-driven:

   ```python
   DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(_SERVER_DIR / "data")))
   DB_PATH: Path = DATA_DIR / "storyplex.db"
   GENERATED_DIR: Path = DATA_DIR / "generated"
   ```

2. **`server/app/main.py`** — tighten CORS for production:

   ```python
   FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
       allow_credentials=False,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

   Set `FRONTEND_ORIGIN=https://storyplex.netlify.app` in Render.

3. **`client/src/services/api.js`** — env-driven API base (see above).

4. **`client/src/services/game-bridge.js`** — env-driven WS base.

5. **`client/public/_redirects`** — SPA fallback for Netlify.

6. **Dockerfile (server)** — optional, only needed for Fly:

   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY server/requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY server/ .
   EXPOSE 8080
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```

---

## Cost back-of-envelope

| Item | Free tier? | Paid |
| --- | --- | --- |
| Netlify (frontend) | ✓ ample | $0 |
| Render Web Service Starter | trial only | $7/mo |
| Render Persistent Disk (1 GB) | n/a | $0.25/mo |
| Gemini API (Pro + Flash + Image) | usage | $0–N depending on traffic |
| Mulberry TTS | per provider's plan | n/a |

Single-user / dev usage: under $10/mo for the host. The Gemini bill is
generation-volume bound — a single fresh-session generation is ~$0.30 in
API costs (Pro world build is the dominant term).

---

## Storage — what to do with `data/generated/`

Two options.

### Easy: persistent disk on Render/Fly

Mount a volume at `/var/data` (Render) or `/data` (Fly). Set `DATA_DIR`
to the mount path. Everything keeps working unchanged.

Pros: zero code change.
Cons: limited to the host's disk size; not CDN-served.

### Production-grade: S3 / R2 + signed URLs

Rewrite `asset_manager.py` to write to an object store (boto3 for S3,
similar for Cloudflare R2). Return signed URLs to the client instead of
serving via the FastAPI app. Audio cache + manifest stay in DB (or move
to Redis).

Pros: CDN, scales, smaller backend host.
Cons: real code change. Defer until traffic warrants it.

---

## CI / CD

Netlify auto-deploys on push to `main` for the frontend.

For the backend, Render and Fly both have GitHub integration — push to
`main` triggers a build. For safer ops, target a `prod` branch and PR
into it from `main` after frontend deploy is verified.

---

## Pre-deploy checklist

- [ ] `pip install -r server/requirements.txt` clean on Python 3.11
- [ ] `npm install && npm run build` clean from `client/`
- [ ] All env vars set on both hosts
- [ ] CORS origin tightened (no `*` in prod)
- [ ] Test a fresh-session generation end-to-end on the deployed backend
- [ ] Test WS audio streaming from the deployed frontend
- [ ] Run a save / load cycle
- [ ] Run a chapter continuation
- [ ] Confirm the persistent disk survives a service restart

---

## What we explicitly punted on

- **Multi-user auth** — every session is currently owned by "whoever has the
  link". A real launch needs Netlify Identity, Clerk, or Supabase auth.
- **Concurrency** — one uvicorn worker is fine for low traffic. For more,
  switch to gunicorn + uvicorn workers and figure out SQLite → Postgres.
- **Asset CDN** — local-disk-served PNGs and WAVs are fine for single-digit
  concurrent users; not fine at scale.
