# Video Demo Script

**One speaker per section. Four contiguous blocks, no shared or alternating segments.**
Each person records their own block separately; cut them together in order.

| # | Speaker | Section | Runs | Speech |
|---|---|---|---|---|
| 1 | **Sudarshan** | Opening and the product (frontend, UI/UX) | 0:00 to 2:30 | 2:08 |
| 2 | **Saksham** | How a story gets made (AI orchestration) | 2:30 to 4:55 | 2:21 |
| 3 | **Abhinav** | How it is served and stored (backend) | 4:55 to 7:05 | 2:00 |
| 4 | **Suryansh** | Running it in production, and close | 7:05 to 10:05 | 2:49 |

Timings are measured from the script at 150 words per minute, with room for the silent demo beats,
so they are not round numbers. Suryansh runs about 45 seconds longer than Abhinav because his
allocation covers four areas plus the close. If your brief requires equal speaking time, move the
payments and ledger material to Abhinav, where it sits naturally beside his transaction work, and
both land near 2:25.

The order tells a story: see the product, learn how it is generated, learn how it is served, then
learn what it takes to run it for real. Sudarshan opens because his section is the most visual.
Suryansh closes because his is the last link in the chain.

---

## Before you record

Generation takes about ten minutes, so it cannot happen live. Have these ready:

- [ ] **A finished, good-looking story** already generated and playable. This carries the video.
- [ ] **A second story mid-generation**, started about three minutes before Sudarshan records, so the
      loading screen shows real progress rather than nothing.
- [ ] **Screen recording of the queue state** ("Your place is held"). Start four generations at once
      to trigger it.
- [ ] Credits page showing **some ledger history**, not an empty table.
- [ ] Browser cleaned up: no bookmarks bar, no unrelated tabs, no personal email addresses on screen.
- [ ] **1080p minimum.** Record system audio so the character voices are audible.
- [ ] Confirm the **voices actually play** in your recording. Silent gameplay footage wastes the best
      thing you have.

---

## 1. Sudarshan · 0:00 to 2:30

**On screen:** storyplex.app landing page, then straight into the reader with a story playing.

> "A visual novel normally takes months to make. You need a writer, an illustrator for the
> characters, another for the backgrounds, and voice actors for every line.
>
> This is StoryPlex. You describe a story in a form, and about ten minutes later you get this."

**[Let the reader play for eight seconds. Say nothing. Let a voiced line land.]**

> "A complete visual novel. Branching story, illustrated cast, voiced dialogue, all generated from
> one paragraph of input. It is live at storyplex.app.
>
> I built the interface, so I will show you what a player actually does."

**[Cut to the create form, filling it in]**

> "Six fields. Genre and tone set the register. Art style applies to every image the system
> generates, which is what keeps the cast and the backgrounds looking like they belong together.
>
> Setting and protagonist personality do the most work. They are free text, and how specific you are
> here decides how good the story is. 'A fantasy city' gives you something generic. 'A floating city
> of airship traders where the guilds are at war' gives you a world."

**[Submit, cut to the loading screen]**

> "Generation takes about ten minutes, which is a long time to stare at a spinner. So the loading
> screen streams live progress over Server-Sent Events. That is the real phase the pipeline is in,
> not a fake progress bar. Right now it is recording voices, which is the slowest part."

**[Cut to the pre-recorded queue footage]**

> "Only three stories generate at once. If the system is busy you are told your position in the
> queue and it counts down. You keep your place and it starts automatically."

**[Cut back to the reader, play a moment, then make a choice]**

> "The reader is the part I care most about. The character sprite has a layered animation rig:
> breathing, blinking, and mouth movement synced to the voice, so someone standing still still feels
> alive instead of being a static image.
>
> Text types out, the voice leads it, and clicking completes the line instead of skipping it, so an
> impatient player never loses dialogue. Choices carry weight toward one of five endings.
>
> Saksham will explain how that story gets written in the first place."

---

## 2. Saksham · 2:30 to 4:55

**On screen:** the pipeline diagram, then the storygraph code.

> "I built the orchestration layer, which is the part that turns one paragraph into a structured,
> coherent story.
>
> The obvious approach is to ask a model for a story and use what comes back. That fails two ways.
> It drifts, so characters change personality halfway through. And it has no structure, so it never
> arrives anywhere satisfying."

**[Show the LangGraph node structure]**

> "So this is a multi-agent pipeline built on LangGraph. A plot agent designs the arc. A world agent
> builds the setting and the catalogue of scenes. A character agent creates the cast with
> appearance, personality and speech style. A chapter agent writes the actual beats.
>
> Then there is a Memory gate, which is a critic that checks the result is structurally sound. Does
> every beat point at a scene that exists? Does every ending have a distinct path to it? If not, it
> sends the work back for revision, up to two rounds before it accepts what it has."

**[Show the spine and endings structure]**

> "The output is a ten-beat spine with five endings, and every choice carries an alignment weight.
> You never pick an ending directly. The ending is a consequence of the kind of choices you made."

**[Switch to the pipeline diagram, point at the usage scan]**

> "The change I am proudest of is this one, and it is about cost.
>
> Originally we generated a fixed catalogue: every character in all ten expressions, and every scene
> the world agent invented. Forty sprites and twelve backgrounds, so fifty-three images per story.
>
> But a story does not use all of them. It might never show a character angry. It might never visit
> three of those locations. We were paying to draw art that nobody would ever see."

**[Point at the ordering]**

> "So we reordered the pipeline. All the text generates first, thirty beat variants and five
> endings. Then we scan that finished script to find which character expressions and which scenes it
> actually references, and we draw only those.
>
> Twenty-six images instead of fifty-three. Fifty-one percent fewer, with nothing lost that a player
> would ever see. There is a fallback that serves the neutral sprite if the live path ever asks for
> an expression we skipped.
>
> Abhinav will cover how all of that gets stored and served."

---

## 3. Abhinav · 4:55 to 7:05

**On screen:** the editor with the backend open, then the API docs.

> "I built the backend. FastAPI, forty REST endpoints, and a PostgreSQL database with twenty-two
> tables.
>
> The interesting problem here is not serving requests. It is that a story is expensive to produce
> but has to be cheap to play."

**[Show the beat_expansions table]**

> "So almost nothing is generated while you play. Every story has a ten-beat spine, and for each
> beat we pre-generate three variants, one for each kind of choice you could have made in the beat
> before. That is thirty dialogue variants plus five ending epilogues, all cached in Postgres before
> you press play.
>
> When you make a choice, the runtime looks up the variant matching your choice's alignment tag. It
> is a database read. That is why playback is instant even though generation took ten minutes."

**[Show the generation route, the claim and charge function]**

> "This is the hardest thing I fixed. This function is where a generation starts, and it is also
> where a credit gets charged.
>
> The original code read the session status, checked it, then wrote it. That is a race. Two
> concurrent requests both pass the check and both start a pipeline. On a double click you would pay
> once and generate twice.
>
> Now the status claim and the credit debit are conditional writes inside one transaction. The
> database decides who wins and the loser gets zero rows affected. We test it with eight concurrent
> requests, and exactly one succeeds every time."

**[Show the auth flow]**

> "Authentication is Google OAuth. We never see your password, and Google's tokens never reach the
> browser. We mint our own opaque session token, store it hashed, and hand out a secure cookie we
> can revoke.
>
> One detail on authorisation: a private story returns 404 to anyone who is not the owner, not 403.
> A 403 tells you the story exists. A 404 tells you nothing.
>
> Suryansh will take it from the model layer down to deployment."

---

## 4. Suryansh · 7:05 to 10:05

**On screen:** a raw generated sprite on magenta, then the cutout, then composited into a scene.

> "I handled model inference, voice, payments and deployment.
>
> Start with sprites, because this nearly killed the project. We need characters on transparent
> backgrounds so they can composite over any scene. Image models are unreliable at producing real
> transparency, so we used a background removal model instead.
>
> That library cost about 475 megabytes just to import, before processing a single image. On a two
> gigabyte instance with several generations running, production ran out of memory and crashed.
> Repeatedly."

**[Show the magenta sprite, then the cutout]**

> "The fix was to stop using a model at all. We ask the image model for a flat magenta background,
> because models follow 'solid colour' far more reliably than they follow 'transparent', and then we
> remove that colour arithmetically. It samples the border to find the actual shade, because the
> model never returns exactly the magenta you asked for, and cuts by colour distance.
>
> Pure numpy, no machine learning model. Memory baseline went from 750 megabytes to 129, and the
> crashes stopped."

**[Show the concurrency chart]**

> "That was not the whole problem. Each generation still peaks around 500 megabytes, and nothing
> limited how many ran at once. The fourth simultaneous generation would exhaust memory and take
> down every story in flight along with the web service. So generations now pass through a
> semaphore. Three at a time, and the rest queue. That is the queue Sudarshan showed you."

**[Show the credits page and the ledger]**

> "Voices are synthesised during generation and streamed over WebSocket, so playback never waits on
> a model.
>
> Billing is prepaid credits through Cashfree. Two free on signup, then packs from 199 rupees. Every
> credit movement goes into an append-only ledger, which matters more than it sounds. When someone
> says they paid and got nothing, that is one query instead of a guess.
>
> Testing found two real billing bugs. Refunds are issued from the Cashfree dashboard and the app
> never learned about them, so a refunded customer kept their credits. And a declined payment was
> reported as still confirming, because a failed attempt leaves the order open for a retry."

**[Show the verification scripts running, then the live site]**

> "It is deployed on Render. Docker backend, static frontend, managed Postgres, assets in Cloud
> Storage. Migrations run on boot.
>
> Ninety-three automated checks across four suites, which found seven real defects including that
> double-spend race. Mid-project Google retired the models we were using and generation broke in
> production, so model IDs are now environment variables with a pre-flight check.
>
> StoryPlex is live at storyplex.app. Sign in with Google and you get two free stories. Everything
> you saw, the plot, the cast, the art and the voices, is generated from a single paragraph. Thanks
> for watching."

---

## Delivery notes

- **Show first, then explain.** Let the thing happen on screen for a beat before you narrate it.
  Silence over good footage is fine.
- **Use the real numbers.** Fifty-one percent, 129 megabytes, ninety-three checks. They are measured
  and they are in the validation report if anyone asks.
- **Say what went wrong.** The crashes, the double-spend race, the refund gap, the retired models.
  Examiners trust a team that found its own bugs more than one that claims it had none.
- **Hand off by name.** Each block ends by naming who is next, so the cuts feel deliberate rather
  than abrupt.
