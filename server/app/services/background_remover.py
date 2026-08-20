import io

from app.logger import logger

try:
    from rembg import new_session, remove as _rembg_remove
    # Pin explicitly: rembg.remove()'s default model has changed across
    # versions (it now defaults to "bria-rmbg", a ~1GB photoreal-segmentation
    # model — massive overkill for cutting out flat anime-style sprites, and
    # a multi-minute download on every cold start). "u2net" (~176MB) is what
    # this was written against and is plenty for that job.
    # Built once at import time — before any of the sprite-generation
    # thread pool's workers start — so the model downloads/loads exactly
    # once, not once per parallel worker racing the same cache miss.
    _SESSION = new_session("u2net")
    _REMBG_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("rembg not available (%s); sprite background removal disabled", exc)
    _REMBG_AVAILABLE = False

from PIL import Image


def remove_sprite_bg(image_bytes: bytes) -> bytes:
    """Remove background from a sprite image. Returns RGBA PNG bytes.

    Falls back to the original image if rembg fails or is unavailable.
    """
    if not _REMBG_AVAILABLE:
        return image_bytes

    try:
        logger.info("Removing background from sprite...")
        output_bytes = _rembg_remove(image_bytes, session=_SESSION)
        # Re-encode as a clean PNG with alpha channel via Pillow
        with Image.open(io.BytesIO(output_bytes)) as img:
            img = img.convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            logger.info("Background removed successfully")
            return buf.getvalue()
    except Exception as err:
        logger.error("Background removal failed, returning original image: %s", err)
        return image_bytes
