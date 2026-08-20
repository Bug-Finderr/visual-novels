"""Check every configured Gemini model is reachable and does its job.

Worth running after ANY model change, and after an outage: Google retires
models on their own schedule, and the failure mode is a 404 deep inside the
generation pipeline — by which point a paying customer has already been
charged for a story that will never finish.

Costs a few rupees (one tiny text call per text model, one image).

Run:  cd server && ./.venv/bin/python scripts/verify_models.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from google.genai import types  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import config  # noqa: E402
from app.services.ai.gemini_client import get_client  # noqa: E402
from app.services.ai.prompts.sprite_generation import build_sprite_prompt  # noqa: E402
from app.services.background_remover import remove_sprite_bg  # noqa: E402

_failures: list[str] = []


def _assert(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        _failures.append(label)


def check_text(slot: str, model: str) -> None:
    print(f"\n[{slot}] {model}")
    client = get_client()
    try:
        resp = client.models.generate_content(
            model=model,
            contents='Return only this JSON and nothing else: {"ok": true}',
        )
        text = (resp.text or "").strip()
        _assert(True, "model is reachable")
        _assert('"ok"' in text or "ok" in text.lower(),
                f"returns usable output ({text[:40]!r})")
    except Exception as err:
        _assert(False, f"model is reachable — {str(err)[:120]}")


def check_image(model: str) -> None:
    print(f"\n[image] {model}")
    client = get_client()
    character = {
        "name": "Verify",
        "appearance": "young woman, short dark hair, plain jacket",
        "personality": "calm",
    }
    prompt = build_sprite_prompt(character, "neutral", "anime", False)
    try:
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        raw = next(
            (p.inline_data.data for p in resp.candidates[0].content.parts
             if getattr(p, "inline_data", None) and p.inline_data.data), None,
        )
    except Exception as err:
        _assert(False, f"model is reachable — {str(err)[:120]}")
        return

    _assert(bool(raw), "returns image bytes")
    if not raw:
        return

    arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    border = np.concatenate([arr[0, :], arr[-1, :], arr[:, 0], arr[:, -1]])
    med = border.mean(axis=0)
    spread = float(border.std(axis=0).mean())

    # The sprite pipeline keys on a flat background colour. It samples the
    # border median rather than a fixed target, so the shade can drift — but a
    # NOISY border (a scene, or a framed panel) breaks the cutout.
    _assert(spread < 25,
            f"background is flat enough to key on (border spread {spread:.1f}, want <25)")
    _assert(med[0] > 150 and med[2] > 150 and med[1] < 120,
            f"background is in the magenta family (RGB {tuple(int(x) for x in med)})")

    alpha = np.array(Image.open(io.BytesIO(remove_sprite_bg(raw))))[:, :, 3]
    transparent = float((alpha == 0).mean() * 100)
    _assert(40 < transparent < 95,
            f"background removal leaves a plausible sprite ({transparent:.0f}% transparent)")


def main() -> None:
    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set — nothing to check.")
        sys.exit(1)

    print("Model check — configured ids, called for real")
    m = config.models
    check_text("story", m.story_pro)
    check_text("dialogue", m.dialogue_flash)
    check_image(m.image_gen)

    if _failures:
        print(f"\n{len(_failures)} CHECK(S) FAILED ❌")
        for f in _failures:
            print(f"  - {f}")
        print("\nOverride without a redeploy: MODEL_STORY / MODEL_DIALOGUE / MODEL_IMAGE")
        sys.exit(1)
    print("\nALL MODELS OK ✅")


if __name__ == "__main__":
    main()
