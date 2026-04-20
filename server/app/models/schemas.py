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


class FreeInputRequest(BaseModel):
    text: str


class GameplayResponse(BaseModel):
    newLabel: str
    statements: list[Any]
    extraLabels: dict[str, list[Any]] = Field(default_factory=dict)
    choices: list[dict] = Field(default_factory=list)
    allowFreeInput: bool = False
    newCharacter: dict | None = None
    newScene: dict | None = None
    audioManifest: dict[str, str] = Field(default_factory=dict)
