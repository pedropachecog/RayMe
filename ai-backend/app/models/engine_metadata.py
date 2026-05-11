from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EngineState = Literal["idle", "loading", "resident", "unavailable"]


class EngineMetadata(BaseModel, frozen=True):
    id: str
    label: str
    default: bool = False
    caveats: list[str] = Field(default_factory=list)


class EngineStatus(BaseModel):
    id: str
    label: str
    available: bool = True
    resident: bool = False
    state: EngineState = "idle"
    unavailable_reason: str | None = None


ENGINE_METADATA: tuple[EngineMetadata, ...] = (
    EngineMetadata(id="f5", label="F5-TTS", default=True),
    EngineMetadata(id="xtts_v2", label="XTTS v2"),
    EngineMetadata(id="qwen3_0_6b", label="Qwen3-TTS 0.6B-Base", caveats=["opt-in"]),
    EngineMetadata(id="luxtts", label="LuxTTS", caveats=["quality caveat"]),
    EngineMetadata(id="chatterbox_turbo", label="Chatterbox Turbo", caveats=["experimental"]),
    EngineMetadata(id="tada_1b", label="TADA 1B", caveats=["experimental"]),
    EngineMetadata(id="voxcpm2", label="VoxCPM2", caveats=["candidate"]),
)
