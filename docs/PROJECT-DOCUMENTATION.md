# StoryPlex — Project Documentation

**AI-generated visual novels**

| | |
|---|---|
| Project | StoryPlex |
| Live at | https://storyplex.app |
| Repository | (see Repo_Link.txt) |
| Author | ____________________ |
| Enrolment no. | ____________________ |
| Institution | ____________________ |
| Submitted | ____________________ |

---

## Contents

1. Introduction and Overview
2. Installation Guide
3. User Manual
4. Test Cases
5. Validation Report
6. Compliance and Originality
7. AI Assistance Disclosure

---


# 1. Introduction and Overview

**AI-generated visual novels.** You supply a premise — genre, setting, a protagonist, a tone — and
StoryPlex writes the story, casts and draws the characters, paints the backgrounds, voices the
dialogue, and hands back something you play in the browser.

Live at **[storyplex.app](https://storyplex.app)**.

---

## What it does

A player fills in a short form. Around ten minutes later they have a complete visual novel:

- **A branching story** — a 10-beat spine with 5 possible endings, where choices carry an alignment
  weight that steers which ending you reach.
- **A cast** — characters with appearance, personality, speech style and voice, drawn as sprites in
  one of four art styles.
- **Scenes** — background art for every location the story actually visits.
- **Voices** — every line synthesised ahead of time, so playback never waits on a model.
- **A library** — stories stay private until published, then appear in Explore with likes, ratings,
  comments and follows.

Generation is paid for with **prepaid credits** (2 free on signup, then packs from ₹199), charged at
the point a story starts generating.

## How it is built

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.14), async, 40 endpoints under `/api/v1` |
| Database | PostgreSQL via SQLAlchemy, schema owned by Alembic (5 migrations, 22 tables) |
| Frontend | React 18 + Vite, React Router, TanStack Query |
| Story generation | Gemini 3.x through a LangGraph multi-agent pipeline |
| Image generation | Gemini image models + a numpy/PIL chroma-key cutout |
| Voice | Silk / Mulberry TTS, streamed over WebSocket |
| Assets | Google Cloud Storage, served straight to the browser |
| Payments | Cashfree Payment Gateway (INR) |
| Hosting | Render — Docker web service, static site, managed Postgres |

Roughly **9,300 lines of Python** and **4,100 lines of JavaScript/JSX**.

### The generation pipeline

```
POST /sessions/{id}/generate
   │  claim the slot + debit a credit   ← one transaction, both conditional writes
   │  admission control (max 3 concurrent; the rest queue and are shown their place)
   ▼
 A0  story bible      plot, world, cast, 10-beat spine, 5 endings   (LangGraph, Gemini)
 A1  dialogue text    30 beat variants + 5 ending epilogues          (cached to Postgres)
   ▼  scan the generated text for what is ACTUALLY referenced
 B   sprites          only the (character, expression) pairs used
 C   backgrounds      only the scenes a beat or ending points at
 D   cover art
 E   voices           every cached line, pre-synthesised
   ▼
 status = ready
```

Generating text *before* images is the point: it lets the pipeline see which sprites and scenes the
story really uses and skip the rest. Measured, that removed **51%** of image generation
(26 images instead of 53) with nothing lost that a player would ever see.

## Documentation

| Document | What's in it |
|---|---|
| Installation Guide (Section 2) | Running it locally, from a clean machine |
| User Manual (Section 3) | For players — signing in, creating, credits, playing |
| Test Cases (Section 4) | Every test case, with how to reproduce each |
| Validation Report (Section 5) | Results and measurements, with evidence |
| Compliance & Originality (Section 6) | Third-party licences, attribution, data handling |
| AI Assistance Disclosure (Section 7) | How AI tooling was used in development |
| Architecture (see repository: docs/ARCHITECTURE.md) | Module-level design |
| Deployment (see repository: DEPLOY-RENDER.md) | Production runbook |

## Quick start

```bash
git clone <repo-url> && cd visual-novels
cp .env.example .env          # add GEMINI_API_KEY at minimum
docker compose up -d          # Postgres
cd server && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/alembic upgrade head
./.venv/bin/python -m uvicorn app.main:app --port 3001 --reload &
cd .. && npm install && npm run dev
```

Then open <http://localhost:3000>. Full detail, including Google sign-in and the optional
services, is in the Installation Guide (Section 2).

## Tests

```bash
cd server
./.venv/bin/python scripts/verify_billing.py           # 68 checks — money paths
./.venv/bin/python scripts/verify_generation_queue.py  # 17 checks — admission control
./.venv/bin/python scripts/verify_models.py            #  8 checks — live model calls
./.venv/bin/python scripts/verify_storygraph.py        #  3 scenarios — story graph
```

93 automated checks. See Test Cases (Section 4) for what each covers.


ewpage

---

# 2. Installation Guide


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

Full runbook: **DEPLOY-RENDER.md (see repository: DEPLOY-RENDER.md)**. In outline:

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


ewpage

---

# 3. User Manual


For people using StoryPlex at **[storyplex.app](https://storyplex.app)**. If you are setting the
project up to develop on, you want the Installation Guide (Section 2) instead.

---

## 1. What StoryPlex is

You describe a story — a genre, a world, a protagonist, a mood — and StoryPlex writes and illustrates
a complete visual novel from it. Characters are drawn and voiced, backgrounds painted, and the story
branches based on what you choose. Generation takes around ten minutes.

---

## 2. Signing in

Click **Sign in** and choose your Google account. StoryPlex never sees your Google password, and no
separate account or password is created.

New accounts receive **2 free story credits**.

---

## 3. Creating a story

**Create** (or **＋ New tale**) opens the form.

| Field | What it does | Required |
|---|---|---|
| **Genre** | Sets the overall register — Fantasy, Horror, Romance, and others | Yes |
| **Art style** | Anime, Cartoon, Realistic, or Illustrated — applies to all art | Yes |
| **Setting · world** | Where and when it happens. The more specific, the better the world | Yes |
| **Protagonist name** | What the main character is called | Yes |
| **Protagonist personality** | Their temperament, which shapes how they speak and react | Yes |
| **Tone** | The emotional weather — Dark, Lighthearted, Bittersweet, and others | Yes |
| **Story premise** | A specific scenario you want to see unfold | Optional |

### Writing a good premise

Specific beats vague, every time.

> **Weaker:** "A fantasy adventure."
>
> **Stronger:** "A cartographer who maps places that do not exist yet, hired by a city that wants to
> be founded somewhere impossible."

The setting and personality fields do the most work. "A floating city of airship traders where the
guilds are at war" produces a far better story than "a fantasy city".

Press **Weave the story**. This costs **1 credit**.

---

## 4. While it generates

The loading screen shows live progress through the phases — world, cast, script, art, voices. It
takes roughly ten minutes.

**If you see "Your place is held"**, your story is queued. Only a few stories generate at once so
each gets the machine's full attention. Your position is shown and counts down, and generation starts
automatically. You can leave the page and come back through your library.

Nothing is lost by closing the tab.

---

## 5. Playing

Open a finished story and press **Begin the tale**.

| Action | How |
|---|---|
| Advance dialogue | Click, or press Space / Enter |
| Skip the typewriter | Click while text is still appearing — it completes instantly |
| Make a choice | Click one of the offered options |
| Free input | Where offered, type your own response instead of choosing |
| Pause | Press Escape |
| Save | Through the pause menu |

Characters are voiced automatically, with the voice leading each line.

### Choices matter

Choices carry weight toward one of **five possible endings**. There is no single correct path, and
the story reacts to the kind of choices you make rather than to any one decision.

### Continuing a story

After reaching an ending you can **Continue** into a new chapter that follows from the ending you
reached, keeping the same cast and world. A continuation is a full generation, so it costs another
credit.

---

## 6. Credits

One credit weaves one complete story. Your balance is the **✦ number** in the header.

| Pack | Price | Credits | Per story |
|---|---:|---:|---:|
| Taster | ₹199 | 1 | ₹199 |
| Author | ₹899 | 5 | ₹180 |
| Studio | ₹1,699 | 10 | ₹170 |

### Buying

Go to **Credits** (the ✦ chip, or the account menu). Enter a mobile number — the payment gateway
requires one for your receipt — and choose a pack. Payment is handled by **Cashfree**; StoryPlex never
sees your card or UPI details.

Credits do not expire, and there is no subscription.

### If a payment fails

You will be told what happened and whether you were charged. A failed or cancelled payment adds no
credits and takes no money. If your balance has not updated after a successful payment, wait a moment
and reload — confirmation can lag slightly.

### Refunds

Covered by the [Refund Policy](https://storyplex.app/legal/refunds). In short: if a story fails to
generate because of a fault on our side, the credit is restored; unused credits are refundable within
7 days; credits already spent on a story that generated successfully are not.

---

## 7. Your library

**Library** holds everything you have written.

- **Continue** — resume where you left off
- **Publish / Unpublish** — publishing makes a story readable by anyone on StoryPlex and lists it in
  Explore. Unpublishing removes it from public view again.
- **Delete** — permanent, and removes the generated artwork and audio with it

Stories are **private until you publish them**.

---

## 8. Explore

Published stories from everyone. You can read, like, rate, comment, and follow authors whose work you
want to see more of. Reading someone else's published story is **free** — it costs no credits.

---

## 9. Settings

Theme and appearance, including several visual packs that reskin the whole application. Settings are
stored on the device you set them on.

---

## 10. Troubleshooting

| Problem | What to do |
|---|---|
| Sign-in does nothing | Allow third-party cookies for the site, or try a different browser |
| "You're out of story credits" | Top up from the Credits page |
| Story stuck generating | Generation takes ~10 minutes; if it has been much longer, contact support with the story name |
| Paid but no credits | Wait a moment and reload; if still missing, contact support with the order reference from the Credits page |
| A character looks wrong | Regenerate by creating a new story — art is generated fresh each time |
| Audio not playing | Check the tab is not muted; audio needs one click on the page before it can start |

---

## 11. Support

**[suryansh.shakya@hawkslab.org](mailto:suryansh.shakya@hawkslab.org)** — replies within 3 working
days. Include the email address on your account, and the order reference for billing questions.

- [Terms of Service](https://storyplex.app/legal/terms)
- [Privacy Policy](https://storyplex.app/legal/privacy)
- [Refund Policy](https://storyplex.app/legal/refunds)


ewpage

---

# 4. Test Cases


Every test case in the project, what it proves, and how to reproduce it.

Testing here is organised around **the things that are expensive to get wrong**: money, concurrency,
and external models. Each suite runs against a real PostgreSQL database — only the external paid
services (payment gateway, LLM) are stubbed, and only where a real call would spend money without
adding confidence.

## Running everything

```bash
cd server
./.venv/bin/python scripts/verify_billing.py           # 68 checks
./.venv/bin/python scripts/verify_generation_queue.py  # 17 checks
./.venv/bin/python scripts/verify_models.py            #  8 checks
STORYGEN_ENGINE=graph ./.venv/bin/python scripts/verify_storygraph.py   # 3 scenarios
```

**93 automated checks.** Raw output from the recorded run is in `evidence/` (see repository: docs/evidence/).

Each script exits non-zero on failure, so all four are CI-ready as-is.

---

## Suite 1 — Billing and credits
`scripts/verify_billing.py` · 68 checks · real Postgres, gateway stubbed

The money paths. Stubbing the gateway is deliberate: the properties worth proving (can two
concurrent spends both win? can a replayed webhook credit twice?) are database properties, and only
appear under real transactions.

### TC-1: Free signup grant

| # | Case | Expected |
|---|---|---|
| 1.1 | First read of a new user's credit account | Balance = 2 (`FREE_STORY_CREDITS`) |
| 1.2 | Grant size recorded on the account | `free_granted` = 2 |
| 1.3 | Account read repeatedly | Balance still 2 — no re-grant |
| 1.4 | Ledger after repeated reads | Exactly one `signup_grant` row |

*Why:* the grant is lazy (on first touch, not at signup) so pre-existing accounts are backfilled.
That makes accidental re-granting the obvious failure mode.

### TC-2: Balance floor and ledger integrity

| # | Case | Expected |
|---|---|---|
| 2.1 | Spend 1 of 2 credits | Balance = 1 |
| 2.2 | Attempt to spend 5 with 1 held | Refused (returns `None`) |
| 2.3 | Balance after a refused spend | Unchanged at 1 |
| 2.4 | Ledger contents | Grant + accepted spend only; the refusal is not recorded |
| 2.5 | Newest ledger row | Carries the running balance |

### TC-3: Concurrent generation — the double-spend race

| # | Case | Expected |
|---|---|---|
| 3.1 | 8 concurrent `/generate` on one session, 1 credit held | Exactly **1** succeeds |
| 3.2 | Credits spent | Exactly 1 |
| 3.3 | Ledger debit rows | Exactly 1 |
| 3.4 | Final session status | `generating` |

*Why:* the original code did check-then-set on session status — a TOCTOU race where two concurrent
requests both passed the check and both started a pipeline. The fix makes the status claim and the
debit conditional writes inside one transaction, so the loser sees `rowcount 0`.

### TC-4: Insufficient credits rolls back cleanly

| # | Case | Expected |
|---|---|---|
| 4.1 | `/generate` with balance 0 | Raises `_InsufficientCredits` |
| 4.2 | Session status afterwards | Still `created`, **not** `generating` |

*Why:* if the status claim survived a failed payment, the user would own a session permanently
wedged in `generating` that could never be retried.

### TC-5: Webhook signature verification

| # | Case | Expected |
|---|---|---|
| 5.1 | Correct HMAC-SHA256 signature | Accepted |
| 5.2 | Body altered by one byte | Rejected |
| 5.3 | Timestamp altered | Rejected |
| 5.4 | Malformed signature | Rejected |
| 5.5 | Valid signature from a different secret | Rejected |

### TC-6: Settlement idempotency

| # | Case | Expected |
|---|---|---|
| 6.1 | First settle of a paid order | Credits granted |
| 6.2 | Balance | Rises by the pack's credits |
| 6.3 | Second settle of the same order | No-op |
| 6.4 | Balance after replay | Unchanged |
| 6.5 | Purchase ledger rows | Exactly one |
| 6.6 | `lifetime_purchased` | Counted once |
| 6.7 | **6 concurrent settles** of one order | Exactly one credits |

*Why:* the webhook and the browser's return-URL verify both settle, and either can arrive first.
Guarded three ways — a `SELECT … FOR UPDATE` row lock, the `credited_at` stamp, and a UNIQUE
ledger key.

### TC-7: Amount verification

| # | Case | Expected |
|---|---|---|
| 7.1 | Gateway reports PAID for ₹1 on a ₹1,699 order | Not credited |
| 7.2 | Reported status | `amount_mismatch` |
| 7.3 | Balance | Untouched |
| 7.4 | Order status | `failed` |

### TC-8: Failure recording

| # | Case | Expected |
|---|---|---|
| 8.1 | `PAYMENT_FAILED_WEBHOOK` | Order status `failed` |
| 8.2 | `error_reason` / `error_code` | Stored on the order |
| 8.3 | `cf_payment_id` | Captured |
| 8.4 | `PAYMENT_USER_DROPPED_WEBHOOK` | Status `abandoned`, tracked apart from a decline |
| 8.5 | A late failure webhook for an order already paid | Status stays `paid` |
| 8.6 | That order's failure fields | Remain empty |

### TC-9: Refund clawback

| # | Case | Expected |
|---|---|---|
| 9.1 | Full refund of an unspent 5-credit pack | 5 credits reclaimed |
| 9.2 | Order status | `refunded` |
| 9.3 | Same refund id replayed | Reclaims nothing |
| 9.4 | A second, distinct refund past 100% | Reclaims nothing |
| 9.5 | Half refund of a 10-credit pack | 5 reclaimed, status `partially_refunded` |
| 9.6 | Refund with status `PENDING` | Nothing reclaimed yet |

*Why:* refunds are issued from the Cashfree dashboard, so the webhook is the only way the app learns
money went back. Without it a refunded customer keeps their credits.

### TC-10: Refund after the credits were spent

| # | Case | Expected |
|---|---|---|
| 10.1 | Refund 5 credits already spent on stories | 5 reclaimed |
| 10.2 | Resulting balance | **−5** — negative, not absorbed |
| 10.3 | Generation attempt at −5 | Blocked |
| 10.4 | Session after the blocked attempt | Still `created`, retryable |
| 10.5 | Buying 5 credits again | Balance returns to 0 |

*Why:* silently absorbing the shortfall would hand out free stories. A negative balance is the
honest record and blocks generation until the customer buys back in.

### TC-11: Declined payments are reported as declined

| # | Case | Expected |
|---|---|---|
| 11.1 | Order `ACTIVE` + latest attempt `FAILED` | Status `failed` |
| 11.2 | Decline reason | Returned for the UI to display |
| 11.3 | Order row | Marked `failed` |
| 11.4 | Credits | None granted |
| 11.5 | Attempt `USER_DROPPED` | Status `abandoned` |
| 11.6 | Attempt `PENDING` | Status `pending` |
| 11.7 | No attempts yet | Status `pending` |
| 11.8 | `FAILED` then `SUCCESS` | Not reported as failed |

*Why:* a declined attempt leaves the **order** `ACTIVE`, because the customer may retry it. Checking
order status alone reported a failed payment as "still being confirmed" — the opposite of the truth.

---

## Suite 2 — Generation admission control
`scripts/verify_generation_queue.py` · 17 checks · pipeline stubbed, no model spend

| # | Case | Expected |
|---|---|---|
| 12.1 | 9 concurrent starts, limit 3 | Peak concurrency never exceeds 3 |
| 12.2 | Same run | Peak reaches 3 — the allowance is fully used |
| 12.3 | Same run | All 9 eventually run; none starved |
| 12.4 | After completion | Queue and active set both empty |
| 13.1 | 6 starts, limit 3 | Exactly 3 reported as queued |
| 13.2 | Queue positions | `1, 2, 3` — contiguous, no gaps |
| 13.3 | Position 1 message | "you're next in line" |
| 13.4 | Position 3 message | "2 stories ahead of you" |
| 13.5 | Queued progress value | 0% (the bar is hidden for these) |
| 13.6 | After the first batch finishes | Queue drains |
| 13.7 | At the end | Queue empty |
| 14.1 | All 3 running pipelines crash | The 3 behind still run |
| 14.2 | After the crashes | No slot leaked |
| 14.3 | After the crashes | No ghost queue entries inflating positions |
| 14.4 | Crashed sessions | Reported as errors to their players |
| 15.1 | 6 starts | The first 3 submitted run first |
| 15.2 | Same run | The queued 3 run after, not before |

*Why:* a pipeline peaks near 500 MB against a 2 GB instance. Without a cap, the 4th simultaneous
generation OOM'd the instance and killed every other in-flight story. TC-14 matters most — a queue
that wedges on the first error would be worse than no queue.

---

## Suite 3 — Model availability
`scripts/verify_models.py` · 8 checks · **live API calls, costs a few rupees**

| # | Case | Expected |
|---|---|---|
| 16.1 | Story model reachable | Responds |
| 16.2 | Story model output | Usable |
| 16.3 | Dialogue model reachable | Responds |
| 16.4 | Dialogue model output | Usable |
| 16.5 | Image model | Returns image bytes |
| 16.6 | Generated background flatness | Border spread < 25 |
| 16.7 | Generated background hue | In the magenta family |
| 16.8 | After chroma-key removal | 40–95% transparent |

*Why:* Google retires models on its own schedule. When `gemini-2.5-pro` began returning
`404 no longer available`, generation broke in production with billing live. This suite turns that
into a pre-flight check. Checks 16.6–16.8 go further than reachability: they confirm the model still
produces the flat chroma-key background the sprite cutout depends on.

**Run this after any model change, and after any generation outage.**

---

## Suite 4 — Story graph
`scripts/verify_storygraph.py` · 3 scenarios · LLM mocked, no quota spent

| # | Case | Expected |
|---|---|---|
| 17.1 | Full graph run: plot → world → characters → chapter → memory → assemble | Valid story contract |
| 17.2 | Memory gate with a deliberately broken first chapter | Revision loop runs, output repaired |
| 17.3 | `generate_world` with `STORYGEN_ENGINE=graph` | Routes to the graph engine and tags the result |

---

## Manual test cases

Cases that need a human or a real browser.

| # | Case | Steps | Expected |
|---|---|---|---|
| M-1 | Google sign-in | Click Sign in → complete Google consent | Returns signed in; `/me` shows the user |
| M-2 | End-to-end generation | Create a story, wait | Reaches `ready`; playable with art and voices |
| M-3 | Live progress | Watch the loading page | SSE progress advances through named phases |
| M-4 | Queue display | Start 4 generations at once | 4th shows its queue position, then starts |
| M-5 | Successful payment | Buy the ₹199 pack, sandbox UPI `testsuccess@gocash` | Returns to success page; balance +1; ledger row |
| M-6 | Failed payment | Same, with `testfailure@gocash` | Failure page with reason; balance unchanged |
| M-7 | Out of credits | Generate with balance 0 | 402 handled as a top-up prompt, not a raw error |
| M-8 | Publish / unpublish | Toggle in library | Appears in / disappears from Explore |
| M-9 | Missing sprite fallback | Request an expression never generated | Serves `neutral.png`, not a 404 |
| M-10 | Cross-device session | Sign in on a second device | Library and credits match |

---

## What is not covered

Stated plainly, because a test plan that claims total coverage is not credible:

- **No unit tests for pure helpers.** Coverage is concentrated on integration behaviour, where this
  project's real defects have been.
- **No frontend component tests.** UI is verified manually (M-1 to M-10).
- **No load testing.** Capacity is derived from measured per-pipeline memory against instance size,
  not from a sustained load run.
- **Story quality is not automatically assessed.** Generated prose and art are judged by reading and
  looking; the suites verify the pipeline produces well-formed output, not that it is good.
- **The live payment gateway is stubbed** in automated tests. The real integration is exercised
  manually against Cashfree's sandbox (M-5, M-6).


ewpage

---

# 5. Validation Report


**Project:** StoryPlex — AI-generated visual novels
**Date of this run:** 28 August 2026
**Environment:** macOS (Darwin 25.6.0), Python 3.14.6, PostgreSQL 16.15 (Docker), Node 18+

This report records what was actually run and what it produced. Raw console output for every suite
is in `evidence/` (see repository: docs/evidence/) and can be regenerated with the commands shown.

---

## 1. Summary

| Suite | Checks | Result |
|---|---:|---|
| Billing and credits | 68 | **PASS** |
| Generation admission control | 17 | **PASS** |
| Model availability | 8 | **PASS** |
| Story graph | 3 scenarios | **PASS** |
| **Total** | **93 + 3** | **All passing** |

```
verify_billing            68 checks   ALL CHECKS PASSED ✅
verify_generation_queue   17 checks   ALL CHECKS PASSED ✅
verify_models              8 checks   ALL MODELS OK ✅
verify_storygraph          3 scenarios ALL CHECKS PASSED ✅
```

Every script exits non-zero on failure. Evidence files are the unedited output of the run above.

---

## 2. Defects found and fixed during validation

The point of writing these suites was to find real problems. They did. Each of the following was a
genuine defect in code already running in production.

### 2.1 Double-spend / double-generation race (critical)

**Found by:** TC-3.
**Defect:** `start_generation` read the session status, then wrote it — a TOCTOU window in which two
concurrent requests both passed the check and both launched a pipeline.
**Impact:** duplicated Gemini spend, and once billing existed, an unpriced second generation.
**Fix:** the status claim and the credit debit became conditional writes inside one transaction
(`UPDATE … WHERE status IN ('created','error')`, `UPDATE … WHERE balance + delta >= 0`), so the
loser observes `rowcount 0`.
**Verified:** 8 concurrent attempts, exactly one winner, one debit, one ledger row.

### 2.2 Refund did not reclaim credits (critical, financial)

**Found by:** review while writing TC-9, prompted by asking what happens after a dashboard refund.
**Defect:** refunds are issued from the Cashfree dashboard; the application never learned of them.
A refunded customer kept their credits — money back *and* the stories.
**Fix:** `REFUND_STATUS_WEBHOOK` now reclaims credits in proportion to the amount refunded.
**Verified:** TC-9.1–9.6, TC-10.1–10.5.

### 2.3 Refund clawback could exceed the amount granted

**Found by:** TC-9.4, while writing the tests for 2.2.
**Defect:** each refund was capped proportionally but the *cumulative* total was not, so two full
refunds against one order reclaimed 10 credits for a 5-credit pack, driving an honest customer to a
false −3.
**Fix:** reclaims are capped against what remains reclaimable on the order.
**Verified:** a second, distinct refund past 100% now reclaims nothing.

### 2.4 Declined payments reported as "still confirming"

**Found by:** user report, then pinned by TC-11.
**Defect:** a declined attempt leaves the *order* `ACTIVE` (the customer may retry it). Only
`EXPIRED`/`TERMINATED` were treated as failure, so a decline fell through to polling and was
reported as pending — the opposite of what happened.
**Fix:** when the order is still `ACTIVE`, the payment *attempts* are queried and the newest mapped
to `failed` / `abandoned` / `pending`.
**Verified:** TC-11.1–11.8, including that a later `SUCCESS` is never reported as failed.

### 2.5 Unbounded generation concurrency (critical, availability)

**Found by:** capacity analysis during validation.
**Defect:** pipelines were dispatched with `asyncio.create_task` and no admission control. Each peaks
near 500 MB against a 2 GB instance with a ~129 MB baseline, so roughly the 4th simultaneous
generation exhausted memory — and an OOM killed every in-flight generation and the web service.
**Fix:** a semaphore (`MAX_CONCURRENT_GENERATIONS`, default 3); beyond it generations queue and the
player is shown their position.
**Verified:** TC-12 to TC-15, including that a crashing pipeline releases its slot.

### 2.6 Retired models broke generation

**Found by:** `verify_models.py` on first run.
**Defect:** `gemini-2.5-pro` and `gemini-2.5-flash` returned `404 … no longer available to new
users`. Generation was broken in production while billing was live.
**Fix:** migrated to the Gemini 3.x line and made model ids env-overridable
(`MODEL_STORY`/`MODEL_DIALOGUE`/`MODEL_IMAGE`), so the next retirement is a config change.
**Verified:** all three configured models called for real (TC-16).

### 2.7 Support contact address did not exist

**Found by:** pre-deployment check of the published policy pages.
**Defect:** the refund and privacy pages listed `support@storyplex.app`; the domain has no MX
records, so that mailbox could not receive mail — while the refund policy promised a reply within 3
working days.
**Fix:** changed to an address verified to resolve (MX records confirmed).

---

## 3. Performance and cost measurements

### 3.1 Selective asset generation

Measured on a complete end-to-end generation, comparing the fixed catalogue against generating only
what the produced script references.

| Asset | Before | After | Reduction |
|---|---:|---:|---:|
| Expression sprites | 40 | 18 | **55%** |
| Scene backgrounds | 12 | 7 | **42%** |
| Total images (incl. cover) | 53 | 26 | **51%** |

The pipeline was reordered so dialogue text is generated *before* images; the generated text is then
scanned for the (character, expression) pairs and scene ids actually used. A runtime fallback serves
the neutral sprite for any expression never pre-rendered, verified byte-identical to the real file.

### 3.2 Memory

| Measurement | Value | Method |
|---|---:|---|
| Application baseline | **129 MB** | `ru_maxrss` after importing the full app |
| Peak per generation pipeline | **~500 MB** | 13 sprite tasks at 6-way concurrency |
| Instance limit | 2048 MB | Render Standard |
| Derived safe concurrency | **3** | `(2048 − 129) / ~500` with headroom |

Before this work the baseline was ~750 MB, because the background-removal library loaded an ONNX
model at import. Replacing it with a numpy/PIL chroma-key cut the baseline to 129 MB and removed the
recurring OOM crashes.

### 3.3 Generation cost per story

| Component | Before | After |
|---|---:|---:|
| Images | ₹182 (53 × $0.039) | **₹77** (26 × $0.0336) |
| Text | ~₹24 | **~₹10** |
| **Total** | **~₹206** | **~₹87** |

A **~58% reduction**, from two independent changes: selective asset generation (§3.1) and migrating
to cheaper current models (§2.6).

### 3.4 Request throughput

| Measurement | Value |
|---|---:|
| 50 concurrent health requests | 64 ms total |
| 50 concurrent database-backed requests | 147 ms total |

Reading and browsing are not the constraint; generation is.

---

## 4. Image model comparison

Conducted while selecting the cheapest viable image model. The sprite pipeline requires a flat
chroma-key background it can key out, so cost alone was not sufficient grounds to choose.

| Model | Price/image | Border RGB (target: magenta) | Flat magenta background |
|---|---:|---|---:|
| `gemini-3.1-flash-lite-image` | **$0.0336** | ~(247, 14, 239) | **3/3** |
| `gemini-2.5-flash-image` | $0.039 | ~(230, 30, 140) | 0/3 |

The adaptive border-median sampler tolerates the pink drift, so the older model was not generally
broken. However one sample framed the magenta fill inside a white border, which defeats the sampler
entirely — the background survived and part of the character was erased. The selected model did not
exhibit this in any sample, and is cheaper.

**Limitation:** three samples per model. Sufficient to choose between them, not sufficient to state a
failure rate.

---

## 5. Validation limitations

- **Sample sizes are small.** The image comparison used 3 samples per model; the cost measurements
  come from one full generation each. Directionally sound, not statistically rigorous.
- **Load testing was not performed.** Concurrency limits are derived from measured per-pipeline
  memory against instance size, not from a sustained load run.
- **The payment gateway is stubbed** in automated tests; the live integration was exercised manually
  against Cashfree's sandbox.
- **Story quality is not automatically assessed.** The suites confirm well-formed output, not good
  writing or art.
- **Single-environment.** All measurements are from one macOS development machine and one Render
  Standard instance.

---

## 6. Conclusion

All 93 automated checks and 3 graph scenarios pass. Seven defects were found and fixed during
validation, four of them affecting money or availability directly. Cost per story fell ~58% and the
recurring out-of-memory failures were eliminated.

The system is functional and deployed. The most significant known risk is not a code defect but an
operational one: the production database remains on a free tier that expires 30 days after creation
and now holds financial records.


ewpage

---

# 6. Compliance and Originality


Covers third-party attribution, licensing, data handling, and the originality of the work — for both
the code and the written documentation.

> **Note on scope.** This document records verifiable facts: what dependencies are used and under
> what licences, what data is collected, and how the work was produced. It is not a plagiarism
> *score*; no similarity-detection tool (Turnitin, MOSS, JPlag) was run as part of preparing it. If
> your institution requires such a report, generate it from their system and file it alongside this.
>
> Development tooling used, including AI assistance, is disclosed separately in
> AI-ASSISTANCE-DISCLOSURE.md (Section 7).

---

## 1. Originality of the work

### 1.1 What is original

The following were designed and written for this project and are not adapted from an existing
codebase, tutorial, or template:

| Component | Description |
|---|---|
| Story generation pipeline | The multi-agent plot/world/character/chapter design with a Memory gate, and the 10-beat spine with 5 alignment-weighted endings |
| Beat-variant caching | Pre-generating 3 variants per beat keyed on the previous choice's alignment tag, so playback is a database lookup rather than a live model call |
| Selective asset generation | Generating dialogue text first, then scanning it to generate only the sprites and scenes actually referenced |
| Chroma-key sprite cutout | Prompting for a flat magenta background and removing it with adaptive border-median colour-distance thresholding in numpy/PIL |
| Credit and ledger model | Lock-free compare-and-swap balance updates with an append-only audit ledger and idempotent settlement |
| Generation admission control | Semaphore-gated pipeline starts with player-visible queue positions |
| Layered sprite animation | The breathing/blink/talk rig driving generated sprites |
| Database schema | All 22 tables and 5 migrations |
| API design | All 40 endpoints |
| Frontend | All React components, routing, and styling |

### 1.2 What is not original, and is attributed

- **Third-party libraries** — listed in §2, used under their published licences, unmodified, and
  installed through package managers rather than vendored into this repository.
- **Generated content** — stories, character art, backgrounds and voices are produced at runtime by
  third-party models (§3). They are not authored by this project and not committed to it.
- **Standard algorithms** — chroma keying by colour distance, HMAC-SHA256 signature verification, and
  OAuth 2.0 authorisation-code flow are well-known techniques implemented from their specifications.

### 1.3 Evidence of authorship

The repository holds **83 commits from 2026-02-28 onwards**, each attributable and GPG-signed. The
commit history records the project's development, including the defects found and fixed during
validation. This is stronger evidence of authorship than any declaration, and can be inspected with
`git log --show-signature`.

---

## 2. Third-party dependencies

All dependencies are installed from public registries. **None are vendored into this repository**, so
no third-party source is presented as this project's own work.

### 2.1 Backend (Python)

| Package | Version | Licence | Used for |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | Web framework |
| uvicorn | 0.52.3 | BSD-3-Clause | ASGI server |
| pydantic | 2.13.4 | MIT | Validation |
| pydantic-settings | 2.15.0 | MIT | Typed configuration |
| sqlalchemy | 2.0.52 | MIT | Database toolkit |
| alembic | 1.19.1 | MIT | Schema migrations |
| psycopg | 3.3.4 | **LGPL-3.0-only** | PostgreSQL driver |
| authlib | 1.7.2 | BSD-3-Clause | OAuth 2.0 client |
| itsdangerous | 2.2.0 | BSD-3-Clause | Signed tokens |
| python-dotenv | 1.2.3 | BSD-3-Clause | Env loading |
| google-genai | 2.18.1 | Apache-2.0 | Gemini API client |
| google-cloud-storage | 3.13.1 | Apache-2.0 | Asset storage |
| Pillow | 12.3.0 | MIT-CMU | Image processing |
| numpy | 2.5.2 | BSD-3-Clause | Array maths (chroma key) |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client |
| websockets | 15.0.1 | BSD-3-Clause | TTS streaming |
| langgraph | 1.2.11 | MIT | Multi-agent orchestration |
| email-validator | 2.3.0 | Unlicense | Email validation |

### 2.2 Frontend (JavaScript)

| Package | Version | Licence | Used for |
|---|---|---|---|
| react | 18.3.1 | MIT | UI library |
| react-dom | 18.3.1 | MIT | DOM renderer |
| react-router-dom | 6.30.4 | MIT | Routing |
| @tanstack/react-query | 5.101.4 | MIT | Server state |
| vite | 6.4.1 | MIT | Build tool |
| @vitejs/plugin-react | 4.x | MIT | React plugin |

### 2.3 Licence obligations

Every dependency is under a permissive licence (MIT, BSD, Apache-2.0, Unlicense) except one:

> **`psycopg` is LGPL-3.0-only.** The LGPL permits use in a project under any licence provided the
> library is **dynamically linked and not modified** — both true here: it is installed as a separate
> package from PyPI and used through its public API. No LGPL obligation extends to this project's own
> source. If the project were ever distributed as a single bundled binary, this would need revisiting.

The Apache-2.0 dependencies require preservation of their notices, satisfied by installing them
unmodified with their bundled licence files.

### 2.4 Third-party services

| Service | Role | Terms |
|---|---|---|
| Google Gemini API | Story, dialogue and image generation | [Google APIs ToS](https://developers.google.com/terms) |
| Google OAuth 2.0 | Authentication | Google APIs ToS |
| Google Cloud Storage | Generated asset storage | Google Cloud ToS |
| Cashfree Payments | Payment processing (INR) | [Cashfree merchant terms](https://www.cashfree.com/tnc/) |
| Silk / Mulberry TTS | Voice synthesis | Provider terms |
| Render | Application and database hosting | Render ToS |

**No credentials for any of these are committed to the repository.** All are supplied through
environment variables; `.env` is git-ignored and `.env.example` contains only placeholders.

---

## 3. Ownership of generated content

Stories, artwork and voices are produced by third-party models at runtime. Under Google's current
terms, output of the Gemini API belongs to the user who generated it. StoryPlex stores that output
and displays it back to the user who created it.

Two consequences are disclosed to users in the published Terms:

- Generated content is **not reviewed by a person** before the user sees it.
- Users **keep ownership of the premises they write**; publishing a story grants other users the
  right to read it on the platform, revocable by unpublishing.

Because output is model-generated, it may resemble other output from the same models. This is
inherent to generative systems and is disclosed rather than claimed as original authorship.

---

## 4. Data protection

### 4.1 What is collected

| Data | Source | Purpose |
|---|---|---|
| Name, email, profile picture | Google OAuth | Account identity |
| Story premises and generated stories | User input, model output | Core function |
| Credit balance and transaction ledger | Application | Billing |
| Mobile number | Entered at checkout | Required by the payment gateway |
| Payment references | Cashfree | Reconciliation |
| Request and error logs | Application | Operation |

### 4.2 What is deliberately not collected

- **No card, UPI or bank details.** These go directly to Cashfree; the application never sees them.
- **No Google password or Google access tokens in the browser.** Sign-in mints an opaque server-side
  session token, stored hashed, delivered as a Secure/HttpOnly cookie.

### 4.3 Security measures

| Measure | Implementation |
|---|---|
| Passwords | None stored — OAuth only |
| Session tokens | Random, stored SHA-256 hashed, server-revocable |
| Cookies | `HttpOnly`, `Secure`, `SameSite=Lax` in production |
| Transport | HTTPS enforced; TLS certificates managed by the platform |
| Webhooks | HMAC-SHA256 signature verified with timing-safe comparison |
| Payment amounts | Re-verified server-side against the order before crediting |
| SQL | Parameterised throughout; no string interpolation of user input |
| Authorisation | Private stories return 404 to non-owners, never 403 — existence is not disclosed |
| Secrets | Environment variables only; never committed |

### 4.4 User rights

The published [Privacy Policy](https://storyplex.app/legal/privacy) states what is collected, who it
is shared with, and how to request deletion or a copy. Users can delete individual stories
themselves, which removes their generated assets.

---

## 5. Published policies

Required for payment-gateway activation, and live:

| Page | URL |
|---|---|
| Terms of Service | https://storyplex.app/legal/terms |
| Privacy Policy | https://storyplex.app/legal/privacy |
| Refund & Cancellation Policy | https://storyplex.app/legal/refunds |
| Contact | https://storyplex.app/legal/contact |

---

## 6. Repository licensing status

**This repository currently has no `LICENSE` file.** In the absence of one, default copyright applies:
all rights reserved, and no permission is granted to others to use, copy or modify the source.

This may be intentional for an academic submission. If the work is to be shared or open-sourced, add
an explicit licence — MIT or Apache-2.0 are compatible with every dependency listed above.

---

## 7. Declaration

To be completed and signed by the author on submission.

> I declare that this project is my own work. Third-party libraries and services are used under the
> licences and terms recorded in §2, and are attributed rather than presented as my own. Content
> generated at runtime by third-party AI models is identified as such in §3. Development tooling,
> including any AI assistance, is disclosed in the accompanying
> AI Assistance Disclosure (Section 7).
>
> Name: ________________________   Enrolment no.: ________________________
>
> Signature: ____________________   Date: ______________


ewpage

---

# 7. AI Assistance Disclosure


**A separate page deliberately.** Institutional policies on AI-assisted development differ — some
require disclosure, some require a specific form of words, a few prohibit it. Check your handbook,
then include this page, adapt it, or replace it with your institution's own form.

It is written to be accurate rather than flattering in either direction: it neither hides the AI's
contribution nor understates the author's.

---

## 1. Summary

This project was developed with substantial assistance from **Claude (Anthropic)**, used through
Claude Code as a coding assistant. AI was used for implementation, debugging, and documentation. The
product decisions, the direction of the work, several of the key technical ideas, and all testing and
acceptance were the author's.

The project spans **83 commits from February 2026 to August 2026**. AI assistance was concentrated in
the August 2026 period (67 of the 83 commits), during which the deployment, billing, and optimisation
work was carried out.

---

## 2. Where AI was used

| Area | Nature of assistance |
|---|---|
| Billing and payments | Credit ledger, Cashfree integration, webhook handling, refund clawback — implemented by AI to the author's specification |
| Generation admission control | Semaphore and queue implementation |
| Model migration | Diagnosing the retired-model outage; migrating to Gemini 3.x |
| Chroma-key background removal | Implementing the author's idea (see §3), including diagnosing an integer-overflow defect |
| Selective asset generation | Implementing the author's idea (see §3) |
| Deployment | Render blueprint, GCS asset storage, DNS and TLS troubleshooting |
| Test suites | The four `verify_*.py` scripts |
| Documentation | This document set, drafted by AI from the codebase and revised by the author |

## 3. Where the substantive ideas were the author's

Recorded because it matters to an honest account of authorship. In several cases the AI's proposal
was rejected and the author's approach was better:

- **Chroma-key background removal.** When the deployed application repeatedly ran out of memory, the
  AI's first fix was to tune the existing ML-based background remover. The author proposed instead
  asking the image model for a solid background colour and removing that colour arithmetically —
  eliminating the ML dependency entirely. This cut the memory baseline from ~750 MB to 129 MB and
  ended the crashes. **The architectural insight was the author's.**

- **Selective asset generation.** Asked to reduce generation cost, the AI reported the target was not
  reachable without cutting features. The author proposed generating only the character expressions
  and scenes the story actually references. This produced a **51% reduction** in image generation
  with no loss of player-visible content. **The idea was the author's.**

- **Product and commercial decisions.** Credit-based pricing over subscription, the price points, the
  size of the free grant, and the decision to charge retries were all the author's.

- **Defect discovery.** The author identified the audio/text synchronisation problem and the
  misreported payment-failure status from using the running application — both real defects the test
  suites had not caught.

## 4. Author's role throughout

- Set the requirements and made every product decision
- Directed the technical approach and rejected proposals that were wrong
- Reviewed and accepted all changes before merge
- Ran and validated the application; reported defects found in use
- Supplied and managed all credentials, accounts, and third-party service configuration
- Retains full understanding of the system's design and operation

## 5. Verification

The claims above are checkable rather than asserted:

- **Commit history** — 83 signed commits with detailed messages recording what changed and why
- **Pull requests** — each significant change went through a PR with its rationale recorded
- **Test evidence** — `evidence/` (see repository: docs/evidence/) holds unedited output of every suite
- **Validation report** — VALIDATION-REPORT.md (Section 5) records the defects found and
  fixed, including several introduced by AI-written code and caught in review or testing

Commits are attributed to the author, who reviewed and accepted each change. No `Co-Authored-By`
trailers appear in the history; this document is the disclosure of AI involvement.

---

## 6. Suggested declaration

Adapt to your institution's required wording.

> I declare that this project was developed with the assistance of AI tooling (Claude, Anthropic),
> used as described above. The requirements, product decisions, technical direction, and validation
> were my own, as were several of the core technical approaches. I have reviewed and understood all
> code in this submission and can explain its design and operation.
>
> Name: ________________________   Enrolment no.: ________________________
>
> Signature: ____________________   Date: ______________
