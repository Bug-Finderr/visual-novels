import io

import numpy as np
from PIL import Image

from app.logger import logger

# Sprites are prompted to render on this flat color (see
# prompts/sprite_generation.py) instead of asking Gemini for a transparent
# background directly — image models comply with "transparent" inconsistently
# (this is also why generate_character_overlays has to verify and discard
# non-transparent results), whereas a distinct solid color is a well-defined,
# reliably-followed instruction that a plain color-distance threshold can key
# out afterward. Chosen because it rarely appears in character art.
CHROMA_KEY_COLOR = (255, 0, 255)  # magenta


def remove_sprite_bg(image_bytes: bytes, tolerance: int = 55, feather: int = 15) -> bytes:
    """Key out the flat chroma-key background, returning RGBA PNG bytes.

    Pure PIL/numpy color-distance thresholding — no ML model. Replaced an
    rembg-based (ONNX segmentation) implementation that added ~700MB-1GB of
    resident memory per instance (rembg's own import cost, independent of
    which model file was loaded) and was the direct cause of repeated OOM
    crashes in production on a 2GB instance. This is sub-second and adds
    only the size of the image itself to memory.

    The background color is sampled adaptively from the image's own border
    pixels (median, robust to the odd stray artifact pixel) rather than
    assumed to exactly match CHROMA_KEY_COLOR — image models don't always
    render the requested hex value exactly.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGBA")
            arr = np.array(img).astype(np.float64)
            rgb = arr[:, :, :3]

            border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
            bg = np.median(border, axis=0)

            dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
            alpha = np.clip((dist - tolerance) / feather * 255, 0, 255)
            arr[:, :, 3] = np.minimum(arr[:, :, 3], alpha)

            out = Image.fromarray(arr.astype(np.uint8), "RGBA")
            buf = io.BytesIO()
            out.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception as err:
        logger.error("Background removal failed, returning original image: %s", err)
        return image_bytes
