# Screenshots for the capstone deck

Drop PNGs here with **exactly these filenames**. The deck builder picks up whatever is present and
leaves a labelled placeholder for anything missing, so you can add them in any order and rebuild.

| Filename | What to capture | Slide |
|---|---|---|
| `01-landing.png` | storyplex.app home page, signed in (credit chip visible in header) | 8 |
| `02-create-form.png` | `/create` with every field filled in — a premise you'd actually use | 8 |
| `03-loading.png` | Loading screen mid-generation: progress bar, percentage, phase text | 8 |
| `04-credits.png` | `/billing` — balance, the three packs, and some ledger history | 8 |
| `05-reader.png` | **The reader playing a story** — character sprite, background, dialogue box | 9 |
| `06-choices.png` | The reader with a choice prompt on screen | 9 |
| `07-explore.png` | `/explore` — published stories grid | 9 |
| `08-library.png` | `/library` — your stories with their status badges | 9 |

## Tips

- **1440–1920px wide**, PNG. Retina/2× is ideal — they get scaled down, so more detail is better.
- Use a **finished, good-looking story** for `05-reader.png` and `06-choices.png`. That single image
  does more persuading than any bullet on the slide.
- Hide anything you don't want on a projector — real email addresses, the browser bookmark bar.
- macOS: `⌘⇧4` then Space captures a clean window with a drop shadow.

Rebuild the deck after adding any of these:

```bash
cd docs && ../server/.venv/bin/python build_capstone_pptx.py
```
