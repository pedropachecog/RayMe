# Phase 03: First Working Call (MVP) - Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 31 planned file/module groups
**Analogs found:** 26 / 31

## File Classification

| New/Modified File or Module Area | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `ai-backend/app/api/webrtc.py` | controller | request-response + signaling | `ai-backend/app/api/webrtc.py`; `ai-backend/app/api/stt.py`; `ai-backend/app/api/tts.py` | exact extension |
| `ai-backend/app/call/session.py` | service | streaming + event-driven | `ai-backend/app/api/webrtc.py`; `ai-backend/app/models/model_manager.py` | partial role |
| `ai-backend/app/call/tracks.py` | service/utility | streaming audio | `ai-backend/app/api/stt.py`; `ai-backend/app/api/tts.py`; `ai-backend/app/audio/io.py` by usage | partial role |
| `ai-backend/app/call/events.py` | utility | event-driven | `web-ui/server/app/domain/llm_stream.py`; `web-ui/client/src/lib/api/stream.ts` | role-match |
| `ai-backend/app/main.py` | app/config | request-response | `ai-backend/app/main.py` | exact |
| `ai-backend/tests/test_webrtc_signaling.py`, new call-session tests | test | request-response + streaming | `ai-backend/tests/test_webrtc_signaling.py`; `ai-backend/tests/test_stt.py` | exact extension |
| `web-ui/server/app/api/calls.py` | controller | request-response + streaming/control | `web-ui/server/app/api/chat.py`; `web-ui/server/app/api/voices.py`; `web-ui/server/app/api/ai_backend.py` | role-match |
| `web-ui/server/app/domain/call_service.py` | service | CRUD + request-response | `web-ui/server/app/domain/thread_service.py`; `web-ui/server/app/api/chat.py::ChatRepository`; `web-ui/server/app/domain/voice_service.py` | role-match |
| `web-ui/server/app/domain/ai_backend_client.py` | service | request-response proxy | `web-ui/server/app/domain/ai_backend_client.py` | exact extension |
| `web-ui/server/app/domain/prompt_builder.py` | service | transform | `web-ui/server/app/domain/prompt_builder.py` | exact extension |
| `web-ui/server/app/storage/models.py` | model | CRUD | `web-ui/server/app/storage/models.py` | exact extension |
| `web-ui/server/app/main.py` | app/config | request-response | `web-ui/server/app/main.py` | exact |
| `web-ui/server/tests/test_calls.py`, call-related server tests | test | request-response + CRUD + streaming | `web-ui/server/tests/test_chat_stream.py`; `web-ui/server/tests/test_voices.py`; `web-ui/server/tests/test_phase1_acceptance.py` | role-match |
| `web-ui/server/tests/test_prompt_builder.py` | test | transform | `web-ui/server/tests/test_prompt_builder.py` | exact extension |
| `web-ui/client/src/lib/api/calls.ts` | service/utility | request-response + streaming/control | `web-ui/client/src/lib/api/chat.ts`; `web-ui/client/src/lib/api/threads.ts`; `web-ui/client/src/lib/api/stream.ts` | exact role |
| `web-ui/client/src/lib/api/types.ts` | model/types | transform | `web-ui/client/src/lib/api/types.ts` | exact extension |
| `web-ui/client/src/lib/call/client.ts` | utility | WebRTC request-response + streaming | `web-ui/client/src/lib/api/client.ts`; `web-ui/client/src/routes/voice-lab/+page.svelte` | partial role |
| `web-ui/client/src/lib/call/store.svelte.ts` | store | event-driven FSM | `web-ui/client/src/routes/chat/[threadId]/+page.svelte`; `web-ui/client/tests/unit/chat.test.ts` | role-match |
| `web-ui/client/src/lib/call/audio.ts` | utility | browser media + streaming audio | `web-ui/client/src/lib/browser/environment.ts`; `web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte` | partial role |
| `web-ui/client/src/routes/call/[threadId]/+page.svelte` or equivalent call route | component/route | streaming + event-driven | `web-ui/client/src/routes/chat/[threadId]/+page.svelte`; `web-ui/client/src/routes/voice-lab/+page.svelte`; `web-ui/client/src/lib/components/AppShell.svelte` | role-match |
| `web-ui/client/src/routes/chat/[threadId]/+page.svelte` | component/route | request-response + streaming | same file | exact extension |
| `web-ui/client/src/lib/components/CharacterCard.svelte` | component | request-response entry action | same file; `VoiceStateBadge.svelte` | exact extension |
| `web-ui/client/src/lib/components/ChatMessageBubble.svelte` | component | render transform + streaming | same file | exact extension |
| `web-ui/client/src/lib/components/AppShell.svelte` | provider/component | browser checks + layout | same file | exact extension |
| `web-ui/client/src/lib/components/call/VoiceVisualizer.svelte` | component | event-driven audio visualization | `StatusChip.svelte`; `SynthPreviewPanel.svelte`; `app.css` | partial visual |
| `web-ui/client/src/lib/components/call/CallToolbar.svelte` | component | event-driven controls | `SynthPreviewPanel.svelte`; `TtsEnginePicker.svelte`; `ConfirmDialog.svelte` | role-match |
| `web-ui/client/src/lib/components/call/CallTranscript.svelte` | component | streaming transcript | `ChatMessageBubble.svelte`; chat route message loop | exact role |
| `web-ui/client/tests/unit/call*.test.ts` | test | event-driven + browser APIs | `web-ui/client/tests/unit/chat.test.ts`; `web-ui/client/tests/unit/api.test.ts`; `web-ui/client/tests/unit/environment.test.ts` | role-match |
| `web-ui/client/tests/e2e/call*.spec.ts`, live call specs | test | browser acceptance + streaming | `chat-stream.spec.ts`; `phase1-full-path.spec.ts`; `live-voice-lab.spec.ts` | role-match |
| `.planning/phases/03-first-working-call-mvp/PLAYWRIGHT-EVIDENCE.md` | docs/test evidence | validation | Phase 02 `PLAYWRIGHT-EVIDENCE.md` | exact |
| `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md` | docs/test evidence | validation | Phase 02 `OMEN-PC-LIVE-EVIDENCE.md`; `ai-backend/docs/RUNTIME-EVIDENCE.md` | exact |

## Pattern Assignments

### AI Backend WebRTC Signaling And Session Files

**Applies to:** `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, `ai-backend/app/call/tracks.py`, `ai-backend/app/call/events.py`, `ai-backend/app/main.py`, `ai-backend/tests/test_webrtc_signaling.py`

**Analogs:** `ai-backend/app/api/webrtc.py`, `ai-backend/app/api/stt.py`, `ai-backend/app/api/tts.py`, `ai-backend/app/models/model_manager.py`, `web-ui/server/app/domain/llm_stream.py`

**Dependency pattern** (`ai-backend/pyproject.toml` lines 6-18):
```toml
dependencies = [
  "fastapi==0.136.1",
  "uvicorn==0.46.0",
  "httpx==0.28.1",
  "pydantic==2.10.6",
  "pynvml==13.0.1",
  "soundfile==0.13.1",
  "numpy==2.2.6",
  "faster-whisper==1.2.1",
  "silero-vad==6.2.1",
  "python-multipart==0.0.26",
  "aiortc==1.14.0",
]
```

**Router pattern** (`ai-backend/app/api/webrtc.py` lines 1-5):
```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/webrtc", tags=["webrtc"])
```

**Existing WebRTC contract to replace, not preserve** (`ai-backend/app/api/webrtc.py` lines 7-31):
```python
_SKELETON_STATUS = {
    "status": "skeleton",
    "phase": "02",
    "live_call_ready": False,
    "media_transport_ready": False,
    "message": "Signaling skeleton only; Phase 3 owns live call media.",
}

@router.get("/status")
def get_webrtc_status() -> dict[str, object]:
    return dict(_SKELETON_STATUS)

@router.post("/offer")
def reject_webrtc_offer() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_CALL_NOT_READY_DETAIL,
    )
```

Planner note: Phase 3 should keep `/webrtc/status` and `/webrtc/offer` as the public AI-backend signaling surface, but the skeleton `501` contract should evolve into real session creation, answer return, state, mute, interrupt, and teardown contracts.

**Transient STT endpoint pattern** (`ai-backend/app/api/stt.py` lines 15-64):
```python
@router.post("/stt/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    vad_threshold: float | None = Form(default=None),
    vad_end_silence_ms: int | None = Form(default=None),
) -> dict[str, Any]:
    settings = _settings_from_app(request)
    threshold = settings.vad_threshold if vad_threshold is None else vad_threshold
    end_silence_ms = (
        settings.vad_end_silence_ms
        if vad_end_silence_ms is None
        else vad_end_silence_ms
    )

    try:
        audio = uploaded_bytes_to_temp_wav(
            await file.read(),
            original_filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_audio", "message": "Invalid audio input"},
        ) from exc

    try:
        stt_adapter = _stt_adapter_from_app(request, settings)
        vad_adapter = _vad_adapter_from_app(request, settings, threshold, end_silence_ms)
        result = stt_adapter.transcribe(
            audio=audio.path,
            vad_adapter=vad_adapter,
            vad_threshold=threshold,
            vad_end_silence_ms=end_silence_ms,
        )
        return _response_contract(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "stt_failed",
                "message": "Transcription failed",
                "retry_allowed": True,
                "manual_transcript_allowed": True,
            },
        ) from exc
    finally:
        audio.cleanup()
```

Planner note: call STT should use the same app-state adapter lookup and sanitized failure shape, but session audio cleanup must close tracks/timers as well as temp files.

**TTS request and sanitized failure pattern** (`ai-backend/app/api/tts.py` lines 16-72):
```python
class TtsSynthesizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=5000)
    reference_audio_b64: str = Field(
        min_length=1,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    use_default_engine: bool = False
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)

@router.post("/tts/synthesize")
def synthesize(request: Request, payload: TtsSynthesizeRequest) -> dict[str, Any]:
    target_engine = _target_engine(request, payload)
    reference_audio = _decode_reference_audio(payload.reference_audio_b64)
    manager = _manager_from_app(request)

    try:
        manager.switch_tts_engine(target_engine)
        adapter = manager.tts_adapters[target_engine]
        result = adapter.synthesize(...)
        if not result.wav_bytes:
            raise ValueError("synthesis returned empty audio")
    except HTTPException:
        raise
    except Exception as exc:
        _mark_engine_unavailable(manager, target_engine)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "tts_failed",
                "message": "Synthesis failed",
                "engine_id": target_engine,
            },
        ) from exc
```

Planner note: session TTS should use the character default voice and engine. Do not silently fall back when `switch_tts_engine()` fails.

**Model health/status pattern** (`ai-backend/app/models/model_manager.py` lines 121-142):
```python
def health(self) -> dict[str, object]:
    vram = self._safe_vram_probe()
    engine_statuses = list(self._statuses.values())
    degraded = any(not status.available for status in engine_statuses)
    status = "degraded" if degraded else "ok"
    if not self._started and self.resident_tts_engine is None:
        status = "starting"
    return {
        "service": "rayme-ai-backend",
        "status": status,
        "stt_model": self.settings.stt_model,
        "stt_compute_type": self.settings.stt_compute_type,
        "stt_language": self.settings.stt_language,
        "vad_ready": True,
        "vad_threshold": self.settings.vad_threshold,
        "vad_end_silence_ms": self.settings.vad_end_silence_ms,
        "resident_tts_engine": self.resident_tts_engine,
        "available_engines": [status.model_dump() for status in engine_statuses],
        "loading_engine": self.loading_engine,
        "vram_used_mb": vram["used_mb"],
        "vram_headroom_mb": vram["headroom_mb"],
    }
```

**Typed event pattern for call data-channel/SSE equivalents** (`web-ui/server/app/domain/llm_stream.py` lines 16-64):
```python
SSE_DATA_PREFIX = "data: "
TOKEN_EVENT_TYPE = "token"
DONE_EVENT_TYPE = "done"
ERROR_EVENT_TYPE = "error"

class TokenEvent(TypedDict):
    type: Literal["token"]
    text: str

class DoneEvent(TypedDict):
    type: Literal["done"]
    message: dict[str, Any]

class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str

def encode_sse_event(event: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(event), separators=(",", ":"))
    return f"{SSE_DATA_PREFIX}{payload}\n\n"
```

Planner note: define call events as explicit typed payloads (`user_final`, `ai_token`, `ai_audio`, `ai_done`, `interrupted`, `muted`, `ended`, `failed`) rather than ad hoc strings. If they travel over RTCDataChannel instead of SSE, keep the same typed schema idea.

**AI-backend app include pattern** (`ai-backend/app/main.py` lines 28-35):
```python
def create_app() -> FastAPI:
    app = FastAPI(title="RayMe AI Backend", version="0.2.0", lifespan=lifespan)
    app.state.model_manager = ModelManager(AiBackendSettings())
    app.include_router(health_router)
    app.include_router(stt_router)
    app.include_router(tts.router)
    app.include_router(webrtc.router)
    return app
```

**AI-backend signaling tests to evolve** (`ai-backend/tests/test_webrtc_signaling.py` lines 8-49):
```python
def test_webrtc_status_declares_non_call_skeleton_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/webrtc/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "skeleton",
        "phase": "02",
        "live_call_ready": False,
        "media_transport_ready": False,
        "message": "Signaling skeleton only; Phase 3 owns live call media.",
    }

def test_webrtc_offer_rejects_live_call_media_until_phase_three() -> None:
    client = TestClient(create_app())

    response = client.post("/webrtc/offer", json={"sdp": "ignored", "type": "offer"})

    assert response.status_code == 501

def test_openapi_does_not_expose_call_captions_or_barge_in_routes() -> None:
    client = TestClient(create_app())

    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/barge-in" not in paths
```

Planner note: update negative skeleton tests into positive live-call readiness and offer/answer tests, but keep the explicit "no barge-in routes in Phase 3" assertion because D-11 defers voice-detected interruption.

### Web UI Server Calls Facade, Thread Writeback, Prompt Context

**Applies to:** `web-ui/server/app/api/calls.py`, `web-ui/server/app/domain/call_service.py`, `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/app/domain/prompt_builder.py`, `web-ui/server/app/storage/models.py`, `web-ui/server/app/main.py`, server tests

**Analogs:** `chat.py`, `threads.py`, `voices.py`, `thread_service.py`, `voice_service.py`, `character_service.py`, `ai_backend_client.py`, `prompt_builder.py`, `models.py`

**FastAPI route/dependency style** (`web-ui/server/app/api/chat.py` lines 8-22 and 53-88):
```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("/{thread_id}/send")
async def send_chat_message(
    thread_id: str,
    payload: ChatSendRequest,
    session: AsyncSession = Depends(get_chat_session),
    runtime_settings: Settings = Depends(get_chat_runtime_settings),
    completion_client: object | None = Depends(get_chat_completion_client),
) -> StreamingResponse:
    repository = ChatRepository(session)
    try:
        await repository.append_user_message(thread_id, payload.content)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc
```

**Pydantic input validation style** (`web-ui/server/app/api/chat.py` lines 25-37):
```python
class ChatSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def strip_non_empty_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "content is required"
            raise ValueError(msg)
        return stripped
```

Planner note: use `extra="forbid"` on call start/control/writeback payloads so browser-supplied provider URLs, API keys, or undeclared control flags are rejected.

**Thread creation route pattern for character-card call start** (`web-ui/server/app/api/threads.py` lines 23-65):
```python
class ThreadCreate(BaseModel):
    character_id: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=240)
    alternate_greeting_index: int | None = None

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, str]:
    try:
        return await service.create_thread(
            character_id=payload.character_id,
            title=payload.title,
            alternate_greeting_index=payload.alternate_greeting_index,
        )
    except CharacterUnavailableError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc
```

Planner note: `POST /api/calls/start` can either call `ThreadService.create_thread()` directly for character-card starts or require the browser to create the thread first. D-02 says the thread must exist before entering the call.

**Durable chronological append pattern** (`web-ui/server/app/api/chat.py` lines 91-163):
```python
class ChatRepository:
    """Durable message writes used by the streaming chat endpoint."""

    async def append_user_message(self, thread_id: str, content_text: str) -> ThreadMessageShape:
        return await self._append_message(
            thread_id,
            content_text,
            message_kind="user_text",
            role="user",
        )

    async def append_ai_message(self, thread_id: str, content_text: str) -> ThreadMessageShape:
        return await self._append_message(
            thread_id,
            content_text,
            message_kind="ai_text",
            role="assistant",
        )

    async def _append_message(...):
        thread = await self._get_thread(thread_id)
        now = utc_now()
        message = Message(
            id=new_message_id(),
            thread_id=thread_id,
            message_kind=message_kind,
            role=role,
            sequence=await self._next_sequence(thread_id),
            content_text=content_text,
            created_at=now,
            updated_at=now,
        )
        self.session.add(message)
        thread.last_message_at = now
        thread.updated_at = now
        await self.session.commit()
        return await self._hydrate_message(thread_id, message.id)
```

Planner note: `CallService` should add explicit `append_call_start`, `append_user_speech`, `append_ai_speech`, and `append_call_end` helpers using the same `_next_sequence`, `utc_now`, commit, and hydration style. Do not create a separate call-history table for Phase 3.

**Existing message kinds and model shape** (`web-ui/server/app/storage/models.py` lines 44-51, 247-290, 366-405):
```python
MESSAGE_KIND_VALUES = (
    "user_text",
    "ai_text",
    "user_speech",
    "ai_speech",
    "call_start",
    "call_end",
)

class Message(TimestampMixin, Base):
    __tablename__ = MESSAGES_TABLE
    __table_args__ = (
        CheckConstraint(
            "message_kind IN ('user_text', 'ai_text', 'user_speech', "
            "'ai_speech', 'call_start', 'call_end')",
            name="ck_messages_message_kind",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'event')",
            name="ck_messages_role",
        ),
        UniqueConstraint("thread_id", "sequence", name="uq_messages_thread_sequence"),
        Index("ix_messages_thread_id", "thread_id"),
    )
    ...

@dataclass(frozen=True, slots=True)
class ThreadMessageShape:
    id: str
    thread_id: str
    message_kind: MessageKind
    role: MessageRole
    sequence: int
    content_text: str | None
```

Planner note: storage already supports Phase 3 call rows. Only add a migration if the plan needs durable call/session metadata that cannot honestly fit in `content_text` and existing chronology fields.

**Thread hydration pattern** (`web-ui/server/app/domain/thread_service.py` lines 142-171 and 259-285):
```python
async def get_thread_detail(self, thread_id: str) -> dict[str, Any]:
    thread = await self._get_thread(thread_id)
    messages = await self._hydrate_messages(thread.id)
    portrait = await self._active_portrait(thread.character_id)
    return {
        "id": thread.id,
        "title": thread.title,
        "character_id": thread.character_id,
        "character_name": thread.character_snapshot_name,
        "character_portrait_url": portrait_url_for_asset(thread.character_id, portrait),
        "character_snapshot": {...},
        "messages": [message.to_dict() for message in messages],
        "last_message_at": _isoformat(thread.last_message_at),
        "created_at": _isoformat(thread.created_at),
        "updated_at": _isoformat(thread.updated_at),
    }

async def _hydrate_messages(self, thread_id: str) -> list[ThreadMessageShape]:
    result = await self.session.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence)
    )
    messages = list(result.scalars())
    ...
    return [
        ThreadMessageShape(
            id=message.id,
            thread_id=message.thread_id,
            message_kind=message.message_kind,
            role=message.role,
            sequence=message.sequence,
            content_text=message.content_text,
            ...
        )
        for message in messages
    ]
```

**Voice preflight pattern** (`web-ui/server/app/domain/character_service.py` lines 224-303):
```python
async def character_to_response(self, character: Character) -> dict[str, Any]:
    active_portrait = await self._active_portrait(character.id)
    default_voice = await self._default_voice_response(character.default_voice_id)
    return {
        ...
        "default_voice_id": character.default_voice_id,
        "default_voice_state": default_voice["state"],
        "default_voice_label": default_voice["label"],
        "default_voice": default_voice["voice"],
        ...
    }

async def _default_voice_response(self, voice_id: str | None) -> dict[str, Any]:
    if voice_id is None:
        return {"state": "none", "label": "No voice", "voice": None}
    voice = await self.session.get(Voice, voice_id)
    if voice is None:
        return {"state": "unavailable", "label": "Voice unavailable", "voice": {...}}
    if voice.deleted_at is not None:
        return {"state": "unavailable", "label": "Voice unavailable", "voice": {...}}
    return {
        "state": "assigned",
        "label": voice.name,
        "voice": {"id": voice.id, "name": voice.name, "default_engine": voice.default_engine, ...},
    }
```

**Saved voice audio lookup pattern** (`web-ui/server/app/domain/voice_service.py` lines 172-209 and 218-224):
```python
async def test_play_voice(self, voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    voice = await self._voice(voice_id)
    asset = await self.asset_for_voice(voice.id)
    if asset is None:
        raise VoiceAssetNotFoundError(voice.id)
    sample = await self.sample_blob(asset.id)
    engine = voice.default_engine if payload.get("use_default_engine", True) else payload.get("engine")
    result = await self.processor.test_play(
        voice_id=voice.id,
        text=payload.get("text", ""),
        engine=engine,
        reference_transcript=voice.reference_transcript,
        content=sample.path.read_bytes(),
        content_type=asset.content_type,
        speech_speed=payload.get("speech_speed", _voice_speech_speed(voice)),
    )

async def asset_for_voice(self, voice_id: str) -> VoiceAsset | None:
    result = await self.session.execute(
        select(VoiceAsset)
        .where(VoiceAsset.voice_id == voice_id, VoiceAsset.asset_kind == ACTIVE_SAMPLE_KIND)
        .order_by(VoiceAsset.created_at.desc())
    )
    return result.scalars().first()
```

Planner note: call preflight must reject `none` and `unavailable` voice states. For an assigned voice, reuse the saved sample, transcript, engine, and speech speed metadata.

**AI backend status facade pattern** (`web-ui/server/app/api/ai_backend.py` lines 22-71):
```python
@router.get("/status")
async def read_ai_backend_status(
    service: SettingsService = Depends(get_settings_service),
    client: AiBackendClient = Depends(get_ai_backend_client),
) -> dict[str, object]:
    settings = await service.read()
    if not settings.ai_backend_url.strip():
        return _unavailable_status("Not configured")

    try:
        status = await client.get_status(settings.ai_backend_url)
    except AiBackendUnavailable as exc:
        endpoint_status = "Unauthorized" if exc.code == "unauthorized" else "Unreachable"
        return _unavailable_status(endpoint_status)

    return compact_ai_backend_status(status)
```

**Sanitized AI backend client pattern** (`web-ui/server/app/domain/ai_backend_client.py` lines 65-83 and 145-170):
```python
class AiBackendClientError(Exception):
    """Public-safe AI backend client error."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}

async def _request(...):
    try:
        if self._http_client is not None:
            response = await self._http_client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=timeout or self._timeout, verify=False) as client:
                response = await client.request(method, url, **kwargs)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE) from exc

    if response.status_code >= 500 and processing_message and processing_code:
        raise AiBackendProcessingError(code=processing_code, message=processing_message)
    if response.status_code in {401, 403}:
        raise AiBackendUnavailable(code="unauthorized", message=UNREACHABLE_MESSAGE)
    if response.status_code >= 400:
        raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE)
    return response
```

Planner note: add `start_call`/`offer`/`control`/`end` methods here or a narrow call-specific client wrapper that uses the same safe error categories. Never leak raw backend tracebacks to the browser.

**Prompt builder transform pattern to extend with sliding window** (`web-ui/server/app/domain/prompt_builder.py` lines 38-87):
```python
async def build_prompt_context(
    thread_id: str,
    *,
    repository: PromptContextRepository | None = None,
    until_message_id: str | None = None,
    action: PromptAction | None = None,
    composer_text: str | None = None,
) -> list[PromptContextMessage]:
    """Build LLM messages from the selected non-stale branch only."""
    ...
    context: list[PromptContextMessage] = []
    system_prompt = _system_prompt(prompt_thread)
    if system_prompt:
        context.append({"role": "system", "content": system_prompt})

    for message in _messages(prompt_thread):
        if _is_stale(message):
            continue
        role = _message_role(message)
        if role not in {"user", "assistant"}:
            continue
        content = _selected_content(message)
        if content:
            context.append({"role": role, "content": content})
        if until_message_id is not None and _field(message, "id") == until_message_id:
            break
```

Planner note: add a recency cap after filtering stale rows and before returning context. Include `user_speech` and `ai_speech` rows because they use roles `user`/`assistant`; exclude `call_start`/`call_end` event rows unless the phase explicitly wants them in prompts.

**LLM streaming/persist-final pattern** (`web-ui/server/app/domain/llm_stream.py` lines 67-87):
```python
async def stream_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
    persist_final: PersistFinalMessage | None = None,
) -> AsyncIterator[str]:
    """Yield SSE token events and a final done event with a full ThreadMessageShape."""

    collected: list[str] = []
    try:
        async for token in _stream_text_tokens(settings, messages, client=client):
            collected.append(token)
            yield encode_sse_event(token_event(token))

        if persist_final is not None:
            message = await persist_final("".join(collected))
            yield encode_sse_event(done_event(message))
    except Exception:
        yield encode_sse_event(error_event("LLM stream failed"))
```

Planner note: for calls, persist final `ai_speech` only once per finalized/partial AI turn. If interrupted, write the truthful partial text/audio state and do not keep generating after cancel.

**Web server app include pattern** (`web-ui/server/app/main.py` lines 10-18 and 57-65):
```python
from app.api.ai_backend import router as ai_backend_router
from app.api.chat import router as chat_router
from app.api.characters import router as characters_router
from app.api.health import router as health_router
from app.api.messages import router as messages_router
from app.api.settings import router as settings_router
from app.api.threads import router as threads_router
from app.api.voices import router as voices_router

...
app.include_router(health_router)
app.include_router(ai_backend_router)
app.include_router(settings_router)
app.include_router(characters_router)
app.include_router(threads_router)
app.include_router(chat_router)
app.include_router(messages_router)
app.include_router(voices_router)
```

Planner note: add `calls_router` next to chat/messages/threads, not under the AI backend status router.

**Server test fixture pattern** (`web-ui/server/tests/test_chat_stream.py` lines 68-99):
```python
@pytest.fixture()
def chat_client(tmp_path: Path) -> Iterator[tuple[TestClient, async_sessionmaker, FakeStreamingClient]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-test.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())
    fake_client = FakeStreamingClient()
    app = create_app(Settings(...), static_client_dir=None)

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_chat_session] = override_session
    app.dependency_overrides[get_chat_completion_client] = lambda: fake_client
```

**Chronology assertion pattern** (`web-ui/server/tests/test_chat_stream.py` lines 246-271):
```python
rows = asyncio.run(_messages_for_thread(sessionmaker, thread_id))
assert [(row.message_kind, row.role, row.content_text) for row in rows] == [
    ("ai_text", "assistant", "Opening from card."),
    ("user_text", "user", "Keep this user turn"),
]
```

Planner note: add call tests that assert `call_start`, `user_speech`, `ai_speech`, `call_end` are written in chronological sequence and that failed/ended calls preserve the rows that truthfully happened.

### Svelte Client Call APIs, Route, Store, Audio, Components

**Applies to:** `web-ui/client/src/lib/api/calls.ts`, `types.ts`, `src/lib/call/*`, call route, chat route, `CharacterCard`, `ChatMessageBubble`, `AppShell`, call components, client tests

**Analogs:** `api/client.ts`, `api/chat.ts`, `api/stream.ts`, `routes/chat/[threadId]/+page.svelte`, `routes/voice-lab/+page.svelte`, `AppShell.svelte`, voice components

**Client API boundary pattern** (`web-ui/client/src/lib/api/client.ts` lines 7-48):
```typescript
export function toApiPath(path: string, apiPrefix = '/api'): string {
  if (ABSOLUTE_HTTP_URL.test(path)) {
    throw new Error('Client API requests must use RayMe backend routes, not absolute provider URLs.');
  }
  ...
  return `${normalizedPrefix}${normalizedPath}`;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { apiPrefix, headers, body, ...requestOptions } = options;
  const initHeaders = new Headers(headers);
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isFormData && !initHeaders.has('Content-Type')) {
    initHeaders.set('Content-Type', 'application/json');
  }
  const response = await fetch(toApiPath(path, apiPrefix), {...});
  if (!response.ok) {
    throw new Error(`RayMe API request failed: ${response.status} ${response.statusText}`.trim());
  }
  return (await response.json()) as T;
}
```

Planner note: call API wrappers must use same-origin `/api/calls/*`. Browser WebRTC SDP can be posted to the web server facade, but the browser must not call the AI backend URL directly.

**SSE/client stream parser pattern** (`web-ui/client/src/lib/api/stream.ts` lines 3-71):
```typescript
export interface ChatStreamHandlers {
  onToken?: (text: string) => void;
  onDone?: (message: ThreadMessage) => void;
  onError?: (message: string) => void;
}

export async function readChatStream(response: Response, handlers: ChatStreamHandlers): Promise<void> {
  if (!response.body) {
    throw new Error('No response stream');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = dispatchCompleteEvents(buffer, handlers);
  }
  buffer += decoder.decode();
  dispatchCompleteEvents(`${buffer}\n\n`, handlers);
}
```

Planner note: if call transcript/control events use SSE from the Web UI server, extend this parser with typed call event handlers. If using RTCDataChannel, copy the discriminated-union event handling, not the byte reader.

**Existing client call-like stream wrapper** (`web-ui/client/src/lib/api/chat.ts` lines 109-125):
```typescript
export async function sendChatMessage(
  threadId: string,
  content: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  const response = await fetch(toApiPath(`/chat/${encodeURIComponent(threadId)}/send`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });

  if (!response.ok) {
    throw new Error(`RayMe chat stream failed: ${response.status} ${response.statusText}`.trim());
  }

  await readChatStream(response, handlers);
}
```

**Forward-stable transcript mutation helpers** (`web-ui/client/src/lib/api/chat.ts` lines 162-251):
```typescript
export function upsertBackendMessage(
  messages: ChatMessageView[],
  backendMessage: ThreadMessage
): ChatMessageView[] {
  let replaced = false;
  const nextMessages = messages.map((message) => {
    if (message.id !== backendMessage.id) return message;
    replaced = true;
    return { ...backendMessage, streaming: false, error: null, retryContent: null };
  });
  if (!replaced) {
    nextMessages.push({ ...backendMessage, streaming: false, error: null, retryContent: null });
  }
  return nextMessages.sort((left, right) => left.sequence - right.sequence);
}

export function appendTokenToStreamingMessage(
  messages: ChatMessageView[],
  streamingMessageId: string,
  token: string
): ChatMessageView[] {
  return messages.map((message) =>
    message.id === streamingMessageId
      ? { ...message, content_text: `${message.content_text ?? ''}${token}` }
      : message
  );
}
```

Planner note: AI call text must be append-only while streaming. Do not replace or rewrite visible tokens except when swapping a local draft row for the final backend message.

**Svelte route state style** (`web-ui/client/src/routes/chat/[threadId]/+page.svelte` lines 50-83 and 103-128):
```svelte
let thread = $state<ThreadDetail | null>(null);
let messages = $state<ChatMessageView[]>([]);
let loadState = $state<'loading' | 'ready' | 'error'>('loading');
let sendState = $state<'idle' | 'sending'>('idle');
...
const threadId = $derived(page.params.threadId ?? '');
const characterName = $derived(thread?.character_name ?? 'Character');
const threadTitle = $derived(thread?.title?.trim() || characterName);

$effect(() => {
  if (!threadId || threadId === loadedThreadId) {
    return;
  }
  loadedThreadId = threadId;
  void refreshThread(threadId);
});

async function refreshThread(id = threadId) {
  loadState = 'loading';
  pageError = '';
  try {
    const detail = await loadThread(id);
    thread = detail;
    messages = sortMessages(detail.messages);
    loadState = 'ready';
  } catch {
    thread = null;
    messages = [];
    loadState = 'error';
    pageError = 'RayMe could not load this thread.';
  }
}
```

**Streaming send/scroll preservation pattern** (`web-ui/client/src/routes/chat/[threadId]/+page.svelte` lines 130-214):
```svelte
async function handleSend(content: string) {
  if (!threadId || sendState === 'sending') {
    return;
  }

  const stickToLatest = isNearBottom();
  const scrollAnchor = stickToLatest ? null : captureScrollAnchor();
  sendState = 'sending';
  const nextSequence = nextMessageSequence(messages);
  const draftKey = `${Date.now()}`;
  const userMessage = createDraftMessage({...});
  const streamingMessage = createDraftMessage({... streaming: true, retryContent: content });

  messages = [...messages, userMessage, streamingMessage];
  await settleSendLayout(stickToLatest, 'smooth');

  try {
    await sendChatMessage(threadId, content, {
      onToken: (token) => {
        const shouldStick = stickToLatest && isNearBottom();
        preserveCurrentScrollTop(shouldStick);
        messages = appendTokenToStreamingMessage(messages, streamingMessage.id, token);
        void settleSendLayout(shouldStick);
      },
      onDone: (message) => {
        messages = sortMessages(replaceStreamingMessage(messages, streamingMessage.id, message));
      },
      onError: () => {
        messages = markStreamingMessageError(messages, streamingMessage.id, content);
      }
    });
  } finally {
    sendState = 'idle';
  }
}
```

Planner note: call transcript rendering should reuse the same "stick only if near bottom" behavior while live tokens/audio states arrive.

**Thread header integration point** (`web-ui/client/src/routes/chat/[threadId]/+page.svelte` lines 592-615):
```svelte
<header class="chat-header">
  <button class="back-button" type="button" aria-label="Back to Home" onclick={() => goto('/')}>
    <ArrowLeft size={18} strokeWidth={1.8} aria-hidden="true" />
  </button>
  ...
  <div class="thread-identity">
    <p>{characterName}</p>
    <h1>{threadTitle}</h1>
  </div>

  <button class="refresh-button" type="button" aria-label="Reload thread" onclick={() => refreshThread()}>
    <RefreshCw size={18} strokeWidth={1.8} aria-hidden="true" />
  </button>
</header>
```

Planner note: add the thread-header `Start call` icon button here. Keep 44px touch target, lucide icon, and accessible label.

**Message loop / transcript pattern** (`web-ui/client/src/routes/chat/[threadId]/+page.svelte` lines 632-715):
```svelte
<div
  class:virtualized={shouldVirtualize}
  class="messages"
  bind:this={messagesViewport}
  aria-label="Chat messages"
  data-message-count={messages.length}
  data-virtualized={shouldVirtualize ? 'true' : 'false'}
  onscroll={handleMessagesScroll}
>
  {#each messages as message (message.id)}
    <ChatMessageBubble
      {message}
      {characterName}
      {portraitUrl}
      openingGreeting={isOpeningGreeting(message)}
      actionBusy={isMessageBusy(message)}
      busyLabel={busyLabelFor(message)}
      ...
    />
  {/each}
</div>
```

**Chat bubble metadata and streaming caret pattern** (`web-ui/client/src/lib/components/ChatMessageBubble.svelte` lines 167-251):
```svelte
<article
  class:user={isUser}
  class:assistant={!isUser}
  class:stale={message.stale_after_edit}
  class="message-row"
  data-message-id={message.id}
  data-message-kind={message.message_kind}
  data-message-role={message.role}
  data-message-sequence={message.sequence}
  data-streaming={message.streaming ? 'true' : 'false'}
>
  <div class="bubble">
    <div class="message-meta">
      <span>{displayName}</span>
      {#if message.streaming}
        <span class="chip streaming-chip">Streaming</span>
      {/if}
    </div>
    <div class="message-content">
      {@html renderedContent}
      {#if message.streaming}
        <span class="stream-caret" aria-hidden="true"></span>
      {/if}
    </div>
  </div>
</article>
```

Planner note: extend `displayName`, chips, and styling for `call_start`, `call_end`, `user_speech`, and `ai_speech`. Keep `data-message-kind` because e2e tests use it.

**Audio playback pattern** (`web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte` lines 13-38 and 70-87):
```svelte
let playing = false;
let audioElement: HTMLAudioElement;

$: if (audioUrl) {
  playing = false;
  if (audioElement) {
    audioElement.load();
  }
}

function togglePlayback() {
  if (!audioElement || !audioUrl) return;
  if (playing) {
    audioElement.pause();
    playing = false;
    return;
  }
  playing = true;
  void audioElement.play().catch(() => {
    playing = false;
  });
}

{#if audioUrl}
  <audio bind:this={audioElement} src={audioUrl} on:ended={() => (playing = false)} preload="metadata"></audio>
{/if}
```

Planner note: call playback needs a remote `MediaStream`, not data URL audio, but copy the guarded play/pause, failure-to-play handling, and state reset style.

**Browser readiness guard pattern** (`web-ui/client/src/lib/browser/environment.ts` lines 13-33):
```typescript
export function getBrowserReadiness(): BrowserReadiness {
  const hasWindow = typeof window !== 'undefined';
  const hasNavigator = typeof navigator !== 'undefined';
  const hasLocation = typeof location !== 'undefined';

  return {
    secureContext: hasWindow ? window.isSecureContext === true : false,
    mediaDevicesAvailable: hasNavigator ? Boolean(navigator.mediaDevices) : false,
    protocol: hasLocation ? location.protocol : '',
    href: hasLocation ? location.href : ''
  };
}
```

**AppShell secure/media status and mobile-nav reservation** (`web-ui/client/src/lib/components/AppShell.svelte` lines 18-40 and 225-281):
```svelte
let secureContext = $state<boolean | null>(null);
let mediaDevicesAvailable = $state<boolean | null>(null);

$effect(() => {
  if (!browser) {
    return;
  }

  secureContext = window.isSecureContext;
  mediaDevicesAvailable = Boolean(navigator.mediaDevices);
});

...
.bottom-nav {
  position: fixed;
  inset: auto 0 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  min-height: 64px;
}

@media (min-width: 800px) {
  .bottom-nav {
    display: none;
  }
}
```

Planner note: call route must either hide bottom nav or reserve enough bottom space so sticky call controls never overlap it.

**Character card action and voice badge integration** (`web-ui/client/src/lib/components/CharacterCard.svelte` lines 50-85):
```svelte
<VoiceStateBadge
  state={character.default_voice_state}
  label={character.default_voice_label}
  voice={character.default_voice}
/>

<div class="actions" aria-label={`Actions for ${character.name}`}>
  <button class="primary" type="button" disabled={busy} on:click={() => onStartChat(character)}>
    <MessageSquarePlus size={16} strokeWidth={1.8} />
    <span>Start Chat</span>
  </button>
  ...
</div>
```

Planner note: add `Start Call` beside `Start Chat` or as a call-specific action. Disable with recovery copy when `default_voice_state !== 'assigned'`.

**Unavailable voice display pattern** (`web-ui/client/src/lib/components/voice/VoiceStateBadge.svelte` lines 10-31):
```svelte
$: badgeText =
  displayState === 'assigned' && voiceName
    ? `Voice: ${voiceName}`
    : displayState === 'unavailable'
      ? 'Voice unavailable'
      : 'No voice';

<span class={`voice-state ${displayState}`} aria-label={ariaText} title={ariaText}>
  {#if displayState === 'unavailable'}
    <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
  {/if}
  <span>{badgeText}</span>
</span>
```

**Disabled-but-visible picker pattern** (`web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` lines 31-59):
```svelte
<div class="engine-grid" role="radiogroup" aria-label="TTS engine">
  {#each engines as engine (engine.id)}
    {@const available = engine.availability?.available !== false}
    <label class:selected={selectedEngine === engine.id} class:unavailable={!available}>
      <input
        type="radio"
        name="tts-engine"
        value={engine.id}
        bind:group={selectedEngine}
        disabled={!available}
      />
      <span class="engine-name">{engine.label}</span>
      <span class="engine-meta">
        {#if !available}
          {engine.availability?.unavailable_reason || 'This engine is not available in the current runtime.'}
        {/if}
      </span>
    </label>
  {/each}
</div>
```

Planner note: apply this to input/output device pickers: keep unsupported pickers visible, disabled, and accompanied by the UI-SPEC recovery copy.

**Destructive confirmation pattern** (`web-ui/client/src/lib/components/ConfirmDialog.svelte` lines 16-59 and 62-89):
```svelte
$: if (open) {
  focusInitialControl();
}

async function focusInitialControl() {
  await tick();
  cancelButton?.focus();
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !submitting) {
    event.preventDefault();
    onCancel();
    return;
  }
  ...
}

{#if open}
  <div class="dialog-backdrop" role="presentation" on:click={closeFromBackdrop}>
    <div
      bind:this={dialogElement}
      class="dialog-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-body"
      tabindex="-1"
      on:keydown={handleKeydown}
    >
```

Planner note: use this focus/escape/backdrop pattern for browser navigation-away or destructive hangup confirmation if the call is active. Toolbar End Call itself can be immediate per UI-SPEC.

**Design token pattern** (`web-ui/client/src/app.css` lines 1-34 and 96-104):
```css
:root {
  color-scheme: dark;
  --color-surface: #060e20;
  --color-surface-low: #091328;
  --color-surface-high: #141f38;
  --color-surface-highest: #192540;
  --color-primary: #b6a0ff;
  --color-secondary: #00e3fd;
  --color-text: #dee5ff;
  --color-text-muted: #9eaad5;
  --color-danger: #ff716c;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --font-body: 14px;
  --font-label: 12px;
  --font-heading: 20px;
  --font-display: 28px;
  --radius-sm: 4px;
  --radius-md: 8px;
  --pulse-gradient: linear-gradient(135deg, #b6a0ff 0%, #70aaff 100%);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

### Test And Evidence Patterns

**Applies to:** backend tests, client unit/e2e tests, live call tests, Phase 3 evidence docs

**Analogs:** `test_chat_stream.py`, `test_voices.py`, `chat.test.ts`, `chat-stream.spec.ts`, `phase1-full-path.spec.ts`, `live-voice-lab.spec.ts`, Phase 02 evidence docs

**Server streaming contract test pattern** (`web-ui/server/tests/test_chat_stream.py` lines 212-245):
```python
def test_send_endpoint_streams_tokens_persists_final_once_and_emits_done_shape(...):
    client, sessionmaker, fake_client = chat_client
    thread_id = asyncio.run(_create_thread(sessionmaker))

    response = client.post(f"/api/chat/{thread_id}/send", json={"content": "Say hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response.text)
    assert events[0] == {"type": "token", "text": "Hel"}
    assert events[1] == {"type": "token", "text": "lo"}
    assert events[-1]["type"] == "done"
    done_message = events[-1]["message"]
    assert done_message["message_kind"] == "ai_text"
    assert done_message["role"] == "assistant"
```

**Prompt builder test pattern** (`web-ui/server/tests/test_prompt_builder.py` lines 50-147):
```python
async def test_swipe_selected_branch_only_enters_prompt() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository, action="swipe")

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Selected branch" in prompt_text
    assert "Hidden branch" not in prompt_text

async def test_stale_rows_are_excluded_from_prompt_context() -> None:
    repository = FakePromptRepository()
    messages = await build_prompt_context("thread-1", repository=repository)
    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Edited-away downstream prompt" not in prompt_text
```

Planner note: add call-specific cases for speech rows and sliding-window truncation.

**Voice unavailable test pattern** (`web-ui/server/tests/test_voices.py` lines 394-422):
```python
def test_force_delete_tombstones_voice_and_characters_show_unavailable_state(...):
    voice = _create_voice(client, name="Referenced voice")
    character = _create_character(client)
    assigned = client.put(
        f"/api/characters/{character['id']}",
        json={**_character_payload(name="Character with voice"), "default_voice_id": voice.voice_id},
    )
    assert assigned.status_code == 200

    deleted = client.delete(f"/api/voices/{voice.voice_id}?force=true")
    character_detail = client.get(f"/api/characters/{character['id']}")

    assert deleted.status_code == 200
    assert character_detail.json()["default_voice_state"] == "unavailable"
    assert character_detail.json()["default_voice_label"] == "Voice unavailable"
```

**Client unit raw-source contract pattern** (`web-ui/client/tests/unit/chat.test.ts` lines 108-149 and 158-233):
```typescript
describe('chat route contract', () => {
  it('uses thread hydration for selected alternates, swipe controls, and stale flags', async () => {
    const fetchMock = installFetch(mockJsonResponse(threadDetail));
    const result = await loadThread('thread 1');
    const request = lastRequest(fetchMock);

    expect(request.url).toBe('/api/threads/thread%201');
    expect(selectedMessageContent(result.messages[0])).toBe('Persisted alternate greeting');
    expect(result.messages[1].stale_after_edit).toBe(true);
    expect(routeSource).toContain('loadThread');
    expect(bubbleSource).toContain('stale_after_edit');
  });

  it('appends token chunks into one streaming AI bubble and replaces it with done.message', async () => {
    ...
    await sendChatMessage('thread-1', 'Hello?', {
      onToken: (token) => {
        tokens.push(token);
        messages = appendTokenToStreamingMessage(messages, streaming.id, token);
      },
      onDone: (message) => {
        done = message;
        messages = replaceStreamingMessage(messages, streaming.id, message);
      }
    });
  });
});
```

Planner note: add raw-source tests for call FSM states, button interrupt presence, disabled picker copy, no typed composer on active call route, and reduced-motion visualizer fallback.

**Browser readiness unit pattern** (`web-ui/client/tests/unit/environment.test.ts` lines 25-95):
```typescript
describe('getBrowserReadiness', () => {
  it('reports secure context and media-device availability', () => {
    installBrowserState({
      secureContext: true,
      mediaDevices: {} as MediaDevices,
      protocol: 'https:',
      href: 'https://192.168.1.199:8443/'
    });

    expect(getBrowserReadiness()).toEqual({
      secureContext: true,
      mediaDevicesAvailable: true,
      protocol: 'https:',
      href: 'https://192.168.1.199:8443/'
    });
  });
});
```

**Playwright mocked route + SSE pattern** (`web-ui/client/tests/e2e/chat-stream.spec.ts` lines 96-149):
```typescript
async function mockThread(page: Page, threadId: string) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(hydratedThread(threadId))
    });
  });
}

test('chat hydrates selected alternates, streams send, and preserves done message fields', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const threadId = 'e2e-thread';
  await mockThread(page, threadId);
  await page.route(`**/api/chat/${threadId}/send`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        'data: {"type":"token","text":"Gen"}\n\n',
        'data: {"type":"token","text":"erated"}\n\n',
        `data: ${JSON.stringify({ type: 'done', message })}\n\n`
      ].join('')
    });
  });
  await page.goto(`/chat/${threadId}`);
  await expectNoBrowserErrors();
});
```

**Acceptance helper pattern** (`web-ui/client/tests/e2e/helpers/acceptance.ts` lines 10-37 and 58-92):
```typescript
export function installBrowserErrorGuard(page: Page, options: BrowserErrorGuardOptions = {}) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (message: ConsoleMessage) => {
    if (message.type() !== 'error') return;
    ...
    if (!allowed) {
      consoleErrors.push(`console.error: ${text}`);
    }
  });
  page.on('pageerror', (error: Error) => {
    pageErrors.push(`pageerror: ${error.message}`);
  });
  return () => {
    expect([...consoleErrors, ...pageErrors]).toEqual([]);
  };
}

export function expectRayMeApiRequest(request: Request) {
  const rawUrl = request.url();
  const url = new URL(rawUrl);
  if (url.search.includes('sk-')) {
    throw new Error(`Browser request includes a raw API key query string: ${rawUrl}`);
  }
  ...
  if (isDirectProviderUrl(url)) {
    throw new Error(`Browser made a direct provider request instead of using RayMe /api: ${rawUrl}`);
  }
}
```

Planner note: live call tests should use `expectRayMeApiRequest()` to prove the browser never bypasses the Web UI server facade.

**Live opt-in Playwright pattern** (`web-ui/client/tests/e2e/live-voice-lab.spec.ts` lines 8-18 and 19-98):
```typescript
const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;

test.skip(
  !liveEnabled || !liveWebUrl || !liveAiHealthUrl,
  'Set RAYME_ENABLE_LIVE_E2E=1, RAYME_LIVE_WEB_URL, and RAYME_LIVE_AI_HEALTH_URL to run live Voice Lab acceptance.'
);

test.use({ ignoreHTTPSErrors: true });

test('live OMEN-PC Voice Lab upload transcribe save and test-play path passes before Android handoff', async ({
  page,
  request: apiRequest
}) => {
  test.setTimeout(300_000);
  expect(liveWebUrl).toBe(canonicalLiveWebUrl);
  expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);
  ...
});
```

Planner note: create a gated live call spec with canonical `https://192.168.1.199:8443` and `https://192.168.1.199:9443/health`, desktop Chromium first, then Android product-owner acceptance.

**Playwright config pattern** (`web-ui/client/playwright.config.ts` lines 3-27):
```typescript
export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: process.env.RAYME_ENABLE_LIVE_E2E === '1' ? [] : ['**/live-*.spec.ts'],
  fullyParallel: true,
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 5'] } }
  ]
});
```

**Phase 02 Playwright evidence style** (`.planning/phases/02-ai-backend-skeleton-voice-lab/PLAYWRIGHT-EVIDENCE.md` lines 105-127):
````markdown
## Phase 02 Final Live Acceptance

- Saved test: `web-ui/client/tests/e2e/live-voice-lab.spec.ts`
- Saved result:
  `playwright-results/live-voice-lab-02-18-20260425T145656Z.json`
- Deployed commit: `e5fcccf`
- Live target: `https://192.168.1.199:8443/voice-lab`
- AI health target: `https://192.168.1.199:9443/health`

Command:

```bash
cd web-ui/client
RAYME_ENABLE_LIVE_E2E=1 \
RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 \
RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health \
npx playwright test tests/e2e/live-voice-lab.spec.ts --project=desktop-chromium --reporter=json
```
````

**OMEN evidence style** (`.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` lines 118-139):
````markdown
## Final Phase 02 Closure Evidence

- Runtime commit under test: `e5fcccf0f318fd4f658fdd10a680a2a99995ed79`
- OMEN deployed commit: `e5fcccf0f318fd4f658fdd10a680a2a99995ed79`
- Live desktop Playwright saved artifact:
  `.planning/phases/02-ai-backend-skeleton-voice-lab/playwright-results/live-voice-lab-02-18-20260425T145656Z.json`
- Live desktop Playwright result: `1 expected`, `0 unexpected`, `0 skipped`, `0 flaky`, duration `74671.898 ms`
- Full local acceptance command passed on 2026-04-25:

```text
uv run --project web-ui/server pytest web-ui/server/tests -q
120 passed

uv run --project ai-backend pytest ai-backend/tests -q
44 passed, 1 warning

npm --prefix web-ui/client run test:unit -- --run
78 passed

npm --prefix web-ui/client run test:e2e
40 passed
```
````

**Runtime gate pattern** (`ai-backend/docs/RUNTIME-EVIDENCE.md` lines 62-109):
````markdown
### 3. Health Check

Capture the full JSON response:

```cmd
curl.exe -k https://192.168.1.199:9443/health
```

Required evidence fields:

- STT model and compute type
- VAD readiness
- resident TTS engine
- available engines
- loading engine, if any
- per-engine unavailable reasons, if any
- VRAM used and headroom

### 5. VRAM Headroom Check
...
The live evidence gate requires used VRAM to stay under `11000` MB with enough
headroom for the later call path.
````

## Shared Patterns

### Ownership Split

**Source:** `03-CONTEXT.md`; `web-ui/client/src/lib/api/client.ts` lines 7-22; `web-ui/server/app/api/ai_backend.py` lines 22-37; `ai-backend/app/api/webrtc.py` lines 21-31

**Apply to:** all call start/signaling/control flows

Browser owns permissions, device selection, local peer, AudioContext, playback, visualizer, and visible FSM. Web UI server owns thread creation, voice/readiness checks, prompt hydration, sanitized AI-backend calls, and durable message writes. AI backend owns the live WebRTC peer, RTP/media processing, STT/TTS runtime, stats, mute consumption, interrupt cancellation, and teardown.

### Same-Origin Browser Boundary

**Source:** `web-ui/client/src/lib/api/client.ts` lines 7-22; `web-ui/client/tests/e2e/helpers/acceptance.ts` lines 71-92

**Apply to:** `calls.ts`, call route, live e2e tests

All browser API traffic must go through RayMe `/api/*` routes. Tests should fail if direct AI backend, LLM provider, OpenAI-compatible, or raw-key URLs appear in browser requests.

### Durable Thread Chronology

**Source:** `web-ui/server/app/storage/models.py` lines 44-51 and 247-290; `web-ui/server/app/api/chat.py` lines 91-163; `web-ui/server/app/domain/thread_service.py` lines 259-285

**Apply to:** `CallService`, call API, call screen transcript, thread return flow

Use the existing `messages.sequence` chronology for `call_start`, finalized `user_speech`, streamed/final `ai_speech`, and `call_end`. The originating thread remains the user-visible source of truth.

### Forward-Stable AI Text

**Source:** `web-ui/server/app/domain/llm_stream.py` lines 67-87; `web-ui/client/src/lib/api/chat.ts` lines 213-233; `web-ui/client/src/routes/chat/[threadId]/+page.svelte` lines 166-186

**Apply to:** AI call turns and live transcript

Append visible AI text chunks. Persist final or partial AI speech once. Do not rewrite already visible text during normal streaming.

### Honest Blocking And Sanitized Errors

**Source:** `ai-backend/app/api/stt.py` lines 51-64; `ai-backend/app/api/tts.py` lines 52-63; `web-ui/server/app/domain/ai_backend_client.py` lines 65-83 and 145-170; `web-ui/server/app/api/voices.py` lines 164-183 and 186-203

**Apply to:** call preflight, offer/control proxy, mic/voice/backend readiness, mid-call failure

Return clear public-safe errors and recovery states. Do not leak tracebacks, local paths, model internals, or secrets. Prefer blocking start or clean teardown over half-connected UI.

### Voice Availability

**Source:** `web-ui/server/app/domain/character_service.py` lines 268-303; `web-ui/server/app/domain/voice_service.py` lines 172-209; `web-ui/client/src/lib/components/voice/VoiceStateBadge.svelte` lines 10-31

**Apply to:** character-card call start, thread-header call start, server preflight

Only assigned, available voices can start a call. Missing or unavailable voices must produce the UI-SPEC recovery copy and must not silently fall back.

### Android-Safe Media And Layout

**Source:** `web-ui/client/src/lib/browser/environment.ts` lines 13-33; `web-ui/client/src/lib/components/AppShell.svelte` lines 18-40 and 225-281; `web-ui/client/src/app.css` lines 96-104

**Apply to:** call route, call audio helper, toolbar, visualizer, Playwright mobile tests

Gate active call entry on secure context and media device availability. Hide or reserve mobile bottom navigation for sticky call controls. Respect `prefers-reduced-motion`.

### Test Coverage Shape

**Source:** `web-ui/server/tests/test_chat_stream.py` lines 68-99 and 212-271; `web-ui/client/tests/unit/chat.test.ts` lines 108-149; `web-ui/client/tests/e2e/chat-stream.spec.ts` lines 96-149; `live-voice-lab.spec.ts` lines 8-18

**Apply to:** all Phase 3 plans

Use pytest for server/AI-backend contracts, Vitest for state/API/browser-helper units, mocked Playwright for desktop/mobile UI contracts, gated live Playwright for OMEN-PC, and evidence docs before Android product-owner acceptance.

## No Analog Found

| File or Module Area | Role | Data Flow | Reason |
|---|---|---|---|
| `ai-backend/app/call/session.py` live `aiortc` peer/session manager | service | streaming + event-driven | Repo has only a Phase 2 skeleton and pinned `aiortc`; no existing live `RTCPeerConnection` implementation. |
| `ai-backend/app/call/tracks.py` RTP inbound/outbound media tracks | service/utility | streaming audio | Existing STT/TTS endpoints process whole transient files/base64; no custom RTP track classes exist. |
| `web-ui/client/src/lib/call/client.ts` browser `RTCPeerConnection` setup | utility | WebRTC streaming | Existing browser code has fetch/SSE/audio playback, but no local peer connection, `addTrack`, or `ontrack` code. |
| `web-ui/client/src/lib/call/audio.ts` mic capture, device selection, AudioContext metering | utility | browser media + streaming audio | Existing code checks `navigator.mediaDevices` and plays audio, but has no `getUserMedia`, `enumerateDevices`, output picker, or RMS metering implementation. |
| `web-ui/client/src/lib/components/call/VoiceVisualizer.svelte` RMS-driven call visualizer | component | event-driven audio visualization | Existing UI has status chips and simple audio controls, but no visualizer component or audio analysis graph. |

## Metadata

**Analog search scope:** `ai-backend/app`, `ai-backend/tests`, `ai-backend/docs`, `web-ui/server/app`, `web-ui/server/tests`, `web-ui/client/src`, `web-ui/client/tests`, `.planning/phases/01-*`, `.planning/phases/02-*`.

**Files scanned:** 55 repository/planning files. Root `AGENTS.md` and `CLAUDE.md` were absent; `.claude/skills/` and `.agents/skills/` were absent.

**Strongest analogs:**
- Exact extension: `ai-backend/app/api/webrtc.py`
- Exact extension: `web-ui/server/app/api/chat.py`
- Exact extension: `web-ui/server/app/domain/thread_service.py`
- Exact extension: `web-ui/server/app/domain/prompt_builder.py`
- Exact extension: `web-ui/server/app/storage/models.py`
- Exact extension: `web-ui/client/src/routes/chat/[threadId]/+page.svelte`
- Exact extension: `web-ui/client/src/lib/components/ChatMessageBubble.svelte`
- Role-match: `web-ui/client/src/routes/voice-lab/+page.svelte`
- Role-match: Phase 02 `PLAYWRIGHT-EVIDENCE.md` and `OMEN-PC-LIVE-EVIDENCE.md`

**Pattern extraction date:** 2026-04-25
