# StoryPlex

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
| [Installation Guide](docs/INSTALLATION.md) | Running it locally, from a clean machine |
| [User Manual](docs/USER-MANUAL.md) | For players — signing in, creating, credits, playing |
| [Test Cases](docs/TEST-CASES.md) | Every test case, with how to reproduce each |
| [Validation Report](docs/VALIDATION-REPORT.md) | Results and measurements, with evidence |
| [Compliance & Originality](docs/COMPLIANCE.md) | Third-party licences, attribution, data handling |
| [AI Assistance Disclosure](docs/AI-ASSISTANCE-DISCLOSURE.md) | How AI tooling was used in development |
| [Architecture](docs/ARCHITECTURE.md) | Module-level design |
| [Deployment](DEPLOY-RENDER.md) | Production runbook |

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
services, is in the [Installation Guide](docs/INSTALLATION.md).

## Tests

```bash
cd server
./.venv/bin/python scripts/verify_billing.py           # 68 checks — money paths
./.venv/bin/python scripts/verify_generation_queue.py  # 17 checks — admission control
./.venv/bin/python scripts/verify_models.py            #  8 checks — live model calls
./.venv/bin/python scripts/verify_storygraph.py        #  3 scenarios — story graph
```

93 automated checks. See [Test Cases](docs/TEST-CASES.md) for what each covers.
