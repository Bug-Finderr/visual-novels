# Compliance and Originality

Covers third-party attribution, licensing, data handling, and the originality of the work — for both
the code and the written documentation.

> **Note on scope.** This document records verifiable facts: what dependencies are used and under
> what licences, what data is collected, and how the work was produced. It is not a plagiarism
> *score*; no similarity-detection tool (Turnitin, MOSS, JPlag) was run as part of preparing it. If
> your institution requires such a report, generate it from their system and file it alongside this.
>
> Development tooling used, including AI assistance, is disclosed separately in
> [AI-ASSISTANCE-DISCLOSURE.md](AI-ASSISTANCE-DISCLOSURE.md).

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
> [AI Assistance Disclosure](AI-ASSISTANCE-DISCLOSURE.md).
>
> Name: ________________________   Enrolment no.: ________________________
>
> Signature: ____________________   Date: ______________
