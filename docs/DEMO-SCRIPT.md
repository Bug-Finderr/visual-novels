# Video Demo Script

**Target length: ~11 minutes.** Timings below are measured from the script at 150 words per minute,
with room for the silent demo beats — not round numbers.

| Speaker | Section | Runs | Speech |
|---|---|---|---|
| All / Suryansh | Opening hook | 0:00 – 0:55 | 0:33 + footage |
| **Sudarshan** | Frontend — UI/UX | 0:55 – 3:00 | 1:51 |
| **Abhinav** | Backend — API, data, gameplay | 3:00 – 5:05 | 1:55 |
| **Saksham** | AI orchestration layer | 5:05 – 7:30 | 2:15 |
| **Suryansh** | Inference, TTS, payments, DevOps | 7:30 – 10:25 | 2:53 |
| All | Close | 10:25 – 10:50 | 0:22 |

> **Note on the split:** Suryansh's section runs about a minute longer than the others because the
> allocation gives it four areas (inference, TTS, payments, DevOps) where the rest have one each. If
> your brief requires equal speaking time, the cleanest trim is to move **payments and the ledger**
> to Abhinav — it sits naturally next to his transaction and race-condition material — which brings
> both to roughly 2:20.

---

## ⚠️ Before you record

Generation takes ~10 minutes, so **it cannot happen live**. Prepare:

- [ ] **A finished, good-looking story** already generated and playable. Pick one with a strong cast
      and backgrounds — this carries the whole video.
- [ ] **A second story mid-generation**, started ~3 minutes before you record Sudarshan's section, so
      the loading screen shows real progress rather than 0%.
- [ ] **A screen recording of the queue state** ("Your place is held") — start 4 generations at once
      to trigger it. Hard to stage live.
- [ ] Credits page with **some ledger history** — a purchase and a few generations, not an empty table.
- [ ] Browser cleaned up: no bookmarks bar, no personal tabs, real email addresses hidden.
- [ ] **1080p minimum**, 60fps if you can. Record system audio for the character voices.
- [ ] Test that the story's **voices actually play** in the recording — silent gameplay footage
      wastes the best part of the demo.

Record each section separately and cut together. Nobody gets one clean 10-minute take.

---

## 0:00 – 0:55 · Opening

**On screen:** storyplex.app landing page, then cut to the reader playing — sprite, background,
voiced dialogue.

> **Suryansh:** "A visual novel takes months to make. You need a writer, an illustrator for the
> characters, another for the backgrounds, and voice actors for every line.
>
> This is StoryPlex. You describe a story in a form — a genre, a setting, a protagonist — and about
> ten minutes later you get this."

**[Let the reader play for ~8 seconds. Say nothing. Let a voiced line land.]**

> "A complete visual novel. Branching story, illustrated cast, voiced dialogue — generated from one
> paragraph of input. It's live at storyplex.app, and we'll walk through how it works."

---

## 0:55 – 3:00 · Sudarshan — Frontend, UI/UX

**On screen:** the create form, filled in field by field.

> "I built the interface — everything the player actually touches.
>
> The core design problem was that behind this form is a ten-minute generation pipeline costing real
> money. So the form has to extract enough signal to make a good story, without feeling like
> paperwork."

**[Fill in Genre, Art style]**

> "Six fields. Genre and tone set the register. Art style applies to every image the system
> generates, so the cast and backgrounds stay visually consistent.
>
> Setting and protagonist personality do the most work — they're free text, and how specific you are
> here decides how good the story is. 'A fantasy city' gives you something generic. 'A floating city
> of airship traders where the guilds are at war' gives you a world."

**[Submit → loading screen]**

> "Generation takes about ten minutes, which is a long time to look at a spinner. So the loading
> screen streams live progress over Server-Sent Events — the actual phase the pipeline is in, not a
> fake progress bar."

**[Cut to the pre-recorded queue footage]**

> "And because only three stories can generate at once, if the system is busy you're told your
> position in the queue and it counts down. You keep your place, and it starts automatically."

**[Cut to the reader, playing]**

> "The reader itself is the part I care most about. The sprite has a layered animation rig —
> breathing, blinking, and mouth movement synced to the voice — so a character standing still still
> feels alive rather than being a static PNG.
>
> Text is typed out, the voice leads it, and clicking skips the typewriter instead of advancing —
> because impatient players shouldn't lose a line."

**[Make a choice]**

> "Choices carry weight toward one of five endings. And the whole app is themeable — several visual
> packs that reskin everything including the reader."

---

## 3:00 – 5:05 · Abhinav — Backend

**On screen:** editor with `server/app/` open; then the API docs at `/docs`.

> "I built the backend — FastAPI, Python, forty REST endpoints, and a PostgreSQL database with
> twenty-two tables.
>
> The interesting problem here isn't serving requests. It's that a story is expensive to produce but
> has to be cheap to play."

**[Show the beat_expansions table, or the schema]**

> "So almost nothing is generated while you play. Every story has a ten-beat spine, and for each
> beat we pre-generate three variants — one for each kind of choice you could have made in the beat
> before. That's thirty dialogue variants, plus five ending epilogues, all cached in Postgres before
> you ever press play.
>
> When you make a choice, the runtime looks up the variant matching your choice's alignment tag. It's
> a database read. That's why playback is instant even though generation took ten minutes."

**[Show `routes/generation.py`, the `_claim_and_charge` function]**

> "The part I'd point at as the hardest thing I fixed: this is where a generation starts, and it's
> also where a credit gets charged.
>
> The original code read the session status, checked it, then wrote it. That's a race — two
> concurrent requests both pass the check and both start a pipeline. On a double-click, you'd pay
> once and generate twice.
>
> Now the status claim and the credit debit are conditional writes inside one transaction. The
> database decides who wins, and the loser gets rowcount zero. We test it with eight concurrent
> requests — exactly one succeeds, every time."

**[Show the auth flow briefly]**

> "Auth is Google OAuth. We never see your password, and Google's tokens never reach the browser —
> we mint our own opaque session token, store it hashed, and hand out a Secure HttpOnly cookie we
> can revoke.
>
> On authorisation: a private story returns 404 to anyone who isn't the owner, not 403. A 403 tells
> you the story exists. A 404 tells you nothing."

---

## 5:05 – 7:30 · Saksham — AI orchestration

**On screen:** the pipeline diagram (`docs/charts/pipeline.png`), then `storygraph/` in the editor.

> "I built the orchestration layer — the part that turns one paragraph into a structured, coherent
> story.
>
> The naive approach is to ask a model for a story and take what you get. That fails in two ways: it
> drifts, so characters change personality halfway through, and it has no structure, so it never
> reaches a satisfying ending."

**[Show the LangGraph node structure]**

> "So instead this is a multi-agent pipeline built on LangGraph. A plot agent designs the arc. A
> world agent builds the setting and the scene catalogue. A character agent creates the cast with
> appearance, personality and speech style. A chapter agent writes the actual beats.
>
> And then there's a Memory gate — a critic that checks the output is structurally consistent. Does
> every beat point at a scene that exists? Does every ending have a distinct alignment path? If not,
> it sends the work back for revision. Up to two rounds before it accepts best-effort."

**[Show the spine / endings structure]**

> "The output is a ten-beat spine with five endings, and choices carry an alignment weight. You don't
> pick an ending — the ending is a consequence of the kind of choices you made."

**[Switch to the pipeline diagram — highlight the usage scan]**

> "The change I'm proudest of is this one, and it's about cost.
>
> Originally we generated a fixed catalogue — every character in every one of ten expressions, and
> every scene the world agent invented. Forty sprites and twelve backgrounds. Fifty-three images per
> story.
>
> But the story doesn't use all of them. It might never show a character being angry. It might never
> visit three of those locations. We were paying to generate art nobody would ever see."

**[Point at the ordering in the diagram]**

> "So we reordered the pipeline. Text generates first — all thirty beat variants and five endings.
> Then we scan that generated script for which character-expression pairs and which scenes it
> actually references, and we only draw those.
>
> Twenty-six images instead of fifty-three. **Fifty-one percent fewer**, and nothing is lost that a
> player would ever see. There's a runtime fallback that serves the neutral sprite if the live path
> ever asks for an expression we skipped."

---

## 7:30 – 10:25 · Suryansh — Inference, TTS, payments, DevOps

**On screen:** a raw generated sprite on magenta, then the cutout, then composited in a scene.

> "I handled model inference, voice, payments and deployment.
>
> Start with sprites, because this one nearly killed the project. We need characters on transparent
> backgrounds so they composite over scenes. Image models are unreliable at producing real
> transparency, so we used a background-removal model instead.
>
> That library cost about 475 megabytes just to import — before processing a single image. On a
> two-gigabyte instance, with several generations running, production ran out of memory and crashed.
> Repeatedly."

**[Show the magenta sprite → cutout]**

> "The fix was to stop using a model at all. We ask the image model for a flat magenta background —
> models follow 'solid colour' far more reliably than they follow 'transparent' — and then remove
> that colour arithmetically. It samples the border to find the actual background shade, because the
> model never returns exactly the magenta you asked for, and cuts by colour distance.
>
> Pure numpy. No ML model. Memory baseline went from 750 megabytes to **129**, and the crashes
> stopped."

**[Show the concurrency chart]**

> "That wasn't the whole problem though. Each generation still peaks around 500 megabytes, and
> nothing limited how many ran at once. The fourth simultaneous generation would exhaust memory and
> take down every story in flight along with the web service.
>
> So generations now pass through a semaphore — three at a time, and the rest queue. That's the
> queue Sudarshan showed."

**[Show the credits page, then buy flow]**

> "Voices are streamed from a TTS service over WebSocket and pre-synthesised during generation, so
> playback never waits on a model.
>
> Billing is prepaid credits through Cashfree. Two free on signup, then packs from ₹199. One credit
> is one story."

**[Show the ledger]**

> "Every credit movement is recorded in an append-only ledger, which matters more than it sounds.
> When someone says 'I paid and got nothing', that's answerable with one query instead of a guess.
>
> Two things we got wrong and fixed: refunds are issued from the Cashfree dashboard, and originally
> the app never learned about them — so a refunded customer kept their credits. And a declined
> payment was being reported as 'still confirming', because a failed attempt leaves the *order*
> open for a retry. Both found by testing, both fixed."

**[Show the verification scripts running]**

> "It's deployed on Render — Docker backend, static frontend, managed Postgres, assets in Google
> Cloud Storage served straight to the browser. Migrations run on boot.
>
> And it's tested: ninety-three automated checks across four suites. They found seven real defects,
> including that double-spend race Abhinav described.
>
> One more thing worth mentioning — mid-project Google retired the Gemini 2.5 models we were using.
> Generation broke in production. Now the model IDs are environment variables and there's a
> pre-flight check that calls every configured model before we trust it."

---

## 10:25 – 10:50 · Close

**On screen:** the reader playing, then the landing page.

> **Suryansh:** "StoryPlex is live at storyplex.app. Sign in with Google and you get two free
> stories."
>
> **Saksham:** "Everything you see in a story — the plot, the cast, the art, the voices — is
> generated from one paragraph."
>
> **Abhinav:** "It's a real deployed service, not a prototype. Accounts, payments, the lot."
>
> **Sudarshan:** "Thanks for watching."

---

## Delivery notes

- **Show, then explain — never the reverse.** Let the thing happen on screen for a beat before you
  narrate it. Silence over good footage is fine.
- **Use real numbers.** 51%, 129 MB, 93 checks, ₹206 to ₹87. They're measured and they're in the
  validation report if anyone asks.
- **Name what went wrong.** The OOM crashes, the double-spend race, the refund gap, the retired
  models. Examiners trust a team that found its own bugs more than one that claims none.
- Keep the pace up. Ten minutes is not long — cut anything that isn't the story, the architecture, or
  a number you can defend.
