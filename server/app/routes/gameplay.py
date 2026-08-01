import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_user, require_readable
from app.db.queries import playthroughs as pt_queries
from app.db.queries import sessions as session_queries
from app.logger import logger
from app.models.schemas import AdvanceRequest, ChoiceRequest, FreeInputRequest, GameplayResponse
from app.services import playthrough_service, script_builder, session_service, tts_generator
from app.services.ai import dialogue_engine

router = APIRouter(prefix="/api/v1/sessions", tags=["gameplay"])


def _process_ai_response(session_id: str, ai_output: dict, playthrough_id: str) -> dict:
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    built = script_builder.build_runtime_label(ai_output)
    label_name = built["labelName"]
    statements = built["statements"]
    extra_labels = built["extraLabels"]

    script_builder.save_label(session_id, label_name, statements)
    for name, stmts in extra_labels.items():
        script_builder.save_label(session_id, name, stmts)

    pt_queries.update_current_label(playthrough_id, label_name)

    # Synthesize voice for the new dialogue lines (stream + cache via Mulberry).
    audio_manifest: dict[str, str] = {}
    try:
        audio_manifest = tts_generator.generate_for_statements(
            session_id, ai_output.get("statements") or [],
        )
    except Exception as err:
        logger.warning("runtime TTS failed: %s", err)

    # Surface beat / ending / alignment state so the client can update its UI
    # and build save snapshots.
    fresh = pt_queries.get_by_id(playthrough_id) or {}
    chosen_ending = None
    if fresh.get("chosen_ending_id"):
        endings = json.loads(session.get("endings") or "[]")
        chosen_ending = next(
            (e for e in endings if e.get("id") == fresh["chosen_ending_id"]),
            None,
        )

    return {
        "newLabel": label_name,
        "statements": statements,
        "extraLabels": extra_labels,
        "choices": ai_output.get("choices") or [],
        "allowFreeInput": bool(ai_output.get("allowFreeInput")),
        "audioManifest": audio_manifest,
        "beatIndex": int(fresh.get("current_beat_index") or 0),
        "alignmentState": json.loads(fresh.get("alignment_state") or "{}"),
        "endingFired": bool(ai_output.get("endingFired")),
        "chosenEnding": chosen_ending,
    }


@router.post("/{session_id}/choice", response_model=GameplayResponse)
async def handle_choice(
    session_id: str,
    payload: ChoiceRequest,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    try:
        pt = playthrough_service.get_or_create(user["id"], session_id)
        ai_output = await asyncio.to_thread(
            dialogue_engine.process_player_action,
            session_id,
            {
                "type": "choice",
                "text": payload.text,
                "consequence": payload.consequence or "",
                "alignmentTag": payload.alignmentTag,
                "magnitude": payload.magnitude,
            },
            pt,
        )
        result = await asyncio.to_thread(_process_ai_response, session_id, ai_output, pt["id"])
        return result
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Choice handling error: %s", err)
        raise HTTPException(status_code=500, detail=str(err))


@router.post("/{session_id}/free-input", response_model=GameplayResponse)
async def handle_free_input(
    session_id: str,
    payload: FreeInputRequest,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    try:
        pt = playthrough_service.get_or_create(user["id"], session_id)
        ai_output = await asyncio.to_thread(
            dialogue_engine.process_player_action,
            session_id,
            {"type": "free-input", "text": payload.text},
            pt,
        )
        result = await asyncio.to_thread(_process_ai_response, session_id, ai_output, pt["id"])
        return result
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Free input handling error: %s", err)
        raise HTTPException(status_code=500, detail=str(err))


@router.post("/{session_id}/advance", response_model=GameplayResponse)
async def handle_advance(
    session_id: str,
    _payload: AdvanceRequest | None = None,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    """No-choice continue: opening script ran out, just expand the current beat."""
    try:
        pt = playthrough_service.get_or_create(user["id"], session_id)
        ai_output = await asyncio.to_thread(
            dialogue_engine.process_player_action,
            session_id,
            {"type": "advance", "text": ""},
            pt,
        )
        result = await asyncio.to_thread(_process_ai_response, session_id, ai_output, pt["id"])
        return result
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Advance handling error: %s", err)
        raise HTTPException(status_code=500, detail=str(err))


@router.get("/{session_id}/script")
def get_script(session_id: str, _s: dict = Depends(require_readable)):
    return script_builder.load_script(session_id)
