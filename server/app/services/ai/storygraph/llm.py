"""Thin JSON-generation wrapper over the existing Gemini client.

Nodes call `llm.gen_json(...)` (module-qualified) so tests can monkeypatch a
single seam. Reuses the project's loose-JSON parser so fenced / sloppy model
output is tolerated exactly like the monolith path.
"""
from __future__ import annotations

import json
import re
from typing import Any

from google.genai import types

from app.logger import logger
from app.services.ai.gemini_client import get_client


def parse_json_loose(text: str) -> Any:
    """Best-effort JSON parse: raw → fenced ```json``` → first{..}last slice."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first : last + 1])
        except json.JSONDecodeError:
            pass

    logger.error("storygraph: JSON parse failed (len=%d). start=%s", len(text), text[:200])
    raise ValueError("storygraph node returned unparseable JSON")


def gen_json(
    prompt: str,
    *,
    model: str,
    temperature: float = 0.9,
    max_output_tokens: int = 16384,
    system: str | None = None,
    fast: bool = False,
) -> Any:
    """Single JSON generation call. `fast` disables Gemini 2.5's thinking pass
    (lower latency) — use for the cheap Flash nodes / the gate critic."""
    client = get_client()
    cfg_kwargs: dict[str, Any] = dict(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
    )
    if system:
        cfg_kwargs["system_instruction"] = system
    if fast:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(**cfg_kwargs),
    )

    # Guard the candidate/parts chain: a prompt safety-block yields no
    # candidates, and a MAX_TOKENS / SAFETY finish can yield content with no
    # parts. Surface an actionable error instead of an opaque IndexError/
    # TypeError (which the caller would otherwise blame on a parse failure).
    candidates = response.candidates or []
    first = candidates[0] if candidates else None
    content = getattr(first, "content", None) if first else None
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        finish = getattr(first, "finish_reason", None)
        feedback = getattr(response, "prompt_feedback", None)
        raise ValueError(
            f"storygraph LLM returned no content (model={model}, "
            f"finish_reason={finish}, prompt_feedback={feedback})"
        )

    finish = getattr(first, "finish_reason", None)
    if finish is not None and str(getattr(finish, "name", finish)) == "MAX_TOKENS":
        logger.warning("storygraph LLM hit MAX_TOKENS (model=%s, cap=%d) — "
                       "output may be truncated", model, max_output_tokens)

    text = "".join(p.text for p in parts if getattr(p, "text", None))
    return parse_json_loose(text)
