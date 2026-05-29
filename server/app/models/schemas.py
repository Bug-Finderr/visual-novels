from typing import Any

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    genre: str
    artStyle: str
    setting: str
    protagonistName: str
    protagonistPersonality: str
    tone: str
    premise: str | None = None


class SessionPatchRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    current_scene_id: str | None = None
    current_label: str | None = None


class ChoiceRequest(BaseModel):
    text: str
    consequence: str | None = ""
    alignmentTag: str | None = None
    magnitude: int | None = 1


class FreeInputRequest(BaseModel):
    text: str


class AdvanceRequest(BaseModel):
    """Empty body — the player just wants the story to continue from where
    it left off (e.g. the opening script ran out, no choice was offered yet).
    The dialogue engine expands the current beat without applying alignment.
    """
    pass


class GameplayResponse(BaseModel):
    newLabel: str
    statements: list[Any]
    extraLabels: dict[str, list[Any]] = Field(default_factory=dict)
    choices: list[dict] = Field(default_factory=list)
    allowFreeInput: bool = False
    audioManifest: dict[str, str] = Field(default_factory=dict)
    beatIndex: int = 0
    alignmentState: dict[str, int] = Field(default_factory=dict)
    endingFired: bool = False
    chosenEnding: dict | None = None
