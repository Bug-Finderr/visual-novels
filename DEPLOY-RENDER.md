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

## 6. Billing — Cashfree Payment Gateway

Billing ships **switched off** (`BILLING_ENABLED=0`), so everything below can wait until the merchant account is live. Until you flip it, generation is free and no credits are debited.

### 6.1 Sandbox first (no KYC needed)

Cashfree issues sandbox credentials the moment you sign up, before any verification. Use them to test the whole flow end to end.

1. Sign up at [merchant.cashfree.com](https://merchant.cashfree.com) → switch the dashboard to **Sandbox** (top-right toggle).
2. **Developers → API Keys** → copy the **App ID** and **Secret Key**.
3. In Render → `storyplex-api` → **Environment**, set:
   - `CASHFREE_APP_ID` and `CASHFREE_SECRET_KEY` = the sandbox pair
   - `CASHFREE_ENV` = `sandbox`
   - `BILLING_ENABLED` = `1`
4. **Developers → Webhooks → Add Webhook Endpoint**: `https://api.storyplex.app/api/v1/billing/webhook/cashfree`. Cashfree signs each delivery; the endpoint rejects anything whose HMAC doesn't verify. Subscribe to **all four**:

   | Event | What it does here |
   |---|---|
   | `PAYMENT_SUCCESS_WEBHOOK` | Credits the order. The backstop for a customer who closes the tab before the return page loads. |
   | `PAYMENT_FAILED_WEBHOOK` | Records the bank's decline reason on the order (`failed`). |
   | `PAYMENT_USER_DROPPED_WEBHOOK` | Records checkout abandonment (`abandoned`) — tracked apart from a decline, because it usually means checkout friction you can fix. |
   | `REFUND_STATUS_WEBHOOK` | **Takes the credits back.** Refunds are raised from the Cashfree dashboard, so this is the only way the app learns money went back — without it a refunded customer keeps their credits. |
5. Buy the ₹199 pack on `https://storyplex.app/billing` with a [sandbox test instrument](https://www.cashfree.com/docs/payments/online/testing) — the balance should tick up before you're even back on the return page.

### 6.2 Going live

Production keys are only issued after KYC. Have ready:

- **PAN** — a personal PAN is accepted if you have no business PAN (register as an Individual).
- **Bank account proof** — cancelled cheque or a statement showing name, account number and IFSC. Must match the PAN holder.
- **Aadhaar linked to your phone number.**

Activation also requires these pages live on the site — they ship in this repo, so just confirm they load: [`/legal/terms`](https://storyplex.app/legal/terms), [`/legal/privacy`](https://storyplex.app/legal/privacy), [`/legal/refunds`](https://storyplex.app/legal/refunds), [`/legal/contact`](https://storyplex.app/legal/contact), and visible pricing at [`/billing`](https://storyplex.app/billing). Cashfree can **deactivate an already-live account** if these later go missing.

> The support address on the policy pages is `CONTACT_EMAIL` in `client/src/pages/legal/Legal.jsx` — currently `suryansh.shakya@hawkslab.org`, which resolves (hawkslab.org has Zoho MX records). If you ever move it to `support@storyplex.app`, add MX records at GoDaddy **first**: the refund policy commits to answering within 3 working days, and Cashfree verifies that support contacts actually work.

Once approved: swap `CASHFREE_APP_ID`/`CASHFREE_SECRET_KEY` for the production pair, set `CASHFREE_ENV=production`, and re-register the webhook on the production dashboard (sandbox and production keep separate webhook config).

### 6.3 Knobs

| Variable | Default | What it does |
|---|---|---|
| `BILLING_ENABLED` | `0` | Master switch. `0` = generation is free, no debits. |
| `FREE_STORY_CREDITS` | `2` | Granted once, on first touch of a user's account. Changing it never re-grants to existing users. |
| `CREDITS_PER_GENERATION` | `1` | Credits burned per story (and per chapter continuation). |
| `REFUND_ON_GENERATION_FAILURE` | `0` | `1` hands the credit back when the pipeline errors. Flip during a Gemini outage. |

### 6.4 Refunds

Issue refunds from the **Cashfree dashboard** (Payments → find the order → Refund). There is no refund button in StoryPlex.

The `REFUND_STATUS_WEBHOOK` then takes the credits back automatically, in proportion to the amount refunded — a half refund reclaims half the credits. **If the customer already spent them, the balance goes negative**, which is deliberate: it's the honest record, and it blocks further generation until they buy back in. Repeated or over-100% refunds can't reclaim more than the order granted.

Check what happened afterwards:

```sql
SELECT r.cf_refund_id, r.amount_paise, r.status, r.credits_reclaimed, o.status
FROM refunds r JOIN payment_orders o ON o.order_id = r.order_id
ORDER BY r.created_at DESC LIMIT 10;
```

### 6.5 Operations report

```bash
cd server && ./.venv/bin/python scripts/billing_report.py --days 7
```

Revenue net of refunds, checkout conversion, **why payments are failing** (ranked), orders left open over an hour, negative balances, unprocessed webhooks, and outstanding credit liability in Gemini spend.

### 6.6 Ledger

Every credit movement is in `credit_ledger`, so a disputed balance is answerable with one query:

```sql
SELECT created_at, delta, reason, balance_after, ref_id
FROM credit_ledger WHERE user_id = '<id>' ORDER BY created_at DESC;
```

To settle an order by hand (payment took, credits didn't — should be impossible, but):

```sql
-- confirm it really is unsettled first
SELECT order_id, status, credits, amount_paise, credited_at
FROM payment_orders WHERE order_id = 'sp_...';
```

then re-run the user's verify from the billing page, or POST the order id back through `/api/v1/billing/orders/{order_id}/verify` — it's idempotent, so a duplicate can't over-credit.

---

## 7. Capacity

One Standard instance (2 GB RAM, 1 CPU) comfortably serves **several hundred concurrent readers** — playing a story is cached dialogue plus assets served straight from GCS, never through this server.

**Generation is the scarce resource.** A pipeline peaks near 500 MB resident against a ~130 MB baseline, so `MAX_CONCURRENT_GENERATIONS=3` leaves real headroom; 4–5 is the hard ceiling. Beyond the limit, generations **queue** and the player is shown their position — before this existed, the 4th simultaneous generation OOM'd the instance and killed every other in-flight story with it.

```bash
# What the queue is doing right now (from the logs)
#   "generation queued: session=… position=2 (active=3)"
```

Raising the limit needs a bigger plan, not just a bigger number — Pro ($85/mo, 4 GB, 2 CPU) supports roughly 8. Watch for `generation queued` lines appearing routinely: that's the signal to scale up, and it's a much better signal than a crash.

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
