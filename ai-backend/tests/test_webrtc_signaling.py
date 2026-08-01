from __future__ import annotations

import base64
import asyncio
import math
import threading
from concurrent.futures import CancelledError as FutureCancelledError
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import soundfile as sf
import httpx
from fastapi.testclient import TestClient

import app.api.webrtc as webrtc_module
from app.api.auth import require_service_auth
from app.main import create_app
from app.config import AiBackendSettings
from app.models.tts_registry import TtsAudioChunk

MUTE_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/mute"
INTERRUPT_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/interrupt"
END_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/end"
SPEAK_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/speak"
RECONNECT_AUDIO_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/reconnect-audio"
EVENTS_DRAIN_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/events/drain"
SERVICE_AUTH_TOKEN = "rayme-test-service-token-0123456789abcdef"
SERVICE_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_AUTH_TOKEN}"}


def _scripted_wav_bytes() -> bytes:
    buffer = BytesIO()
    samples = np.full(2400, 0.25, dtype=np.float32)
    sf.write(buffer, samples, 24000, format="WAV")
    return buffer.getvalue()


SCRIPTED_WAV_BYTES = _scripted_wav_bytes()


class ScriptedTtsAdapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def synthesize_call_text(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        **options: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "turn_id": turn_id,
                "text": text,
                "voice_id": voice_id,
                "engine_id": engine_id,
                **options,
            }
        )
        if self.fail:
            raise RuntimeError(
                "raw model failure Traceback /home/pmpg/.cache/model-cache "
                r"C:\Users\pmpg\rayme\model-cache"
            )
        return {"wav_bytes": SCRIPTED_WAV_BYTES, "sample_rate": 24000, "duration_ms": 100}


class ScriptedStreamingTtsAdapter:
    engine_id = "voxcpm2"

    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[Any] = []

    def synthesize(self, _payload: Any) -> dict[str, Any]:
        raise AssertionError("whole synthesis fallback was used")

    def stream(self, request: Any) -> Any:
        self.calls.append(request)
        if self.fail == "before_first_audio":
            raise RuntimeError("Traceback /home/pmpg/.cache openbmb/VoxCPM2")
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=0,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=100,
            generated_at_ms=25.0,
        )
        if self.fail == "after_first_audio":
            raise RuntimeError("Traceback /home/pmpg/.cache openbmb/VoxCPM2")
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=1,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=100,
            generated_at_ms=60.0,
        )


class ScriptedQwenStreamingTtsAdapter(ScriptedStreamingTtsAdapter):
    engine_id = "qwen3_1_7b"

    def __init__(self) -> None:
        super().__init__()
        self.stream_identities: list[tuple[str, str]] = []

    def stream(
        self,
        request: Any,
        *,
        request_id: str,
        voice_key: str,
    ) -> Any:
        self.stream_identities.append((request_id, voice_key))
        yield from super().stream(request)


class BlockingQwenStreamingTtsAdapter(ScriptedQwenStreamingTtsAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.stream_started = threading.Event()
        self.release_stream = threading.Event()
        self.cancel_calls: list[str] = []

    def stream(
        self,
        request: Any,
        *,
        request_id: str,
        voice_key: str,
    ) -> Any:
        self.stream_identities.append((request_id, voice_key))
        self.stream_started.set()
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=0,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=100,
            generated_at_ms=25.0,
        )
        self.release_stream.wait()

    def cancel(self, request_id: str) -> bool:
        self.cancel_calls.append(request_id)
        self.release_stream.set()
        return True


class ScriptedModelManager:
    def __init__(
        self,
        adapter: Any | None = None,
        *,
        adapters: dict[str, Any] | None = None,
    ) -> None:
        self.switch_calls: list[str] = []
        self.tts_adapters = dict(adapters or {"f5": adapter or ScriptedTtsAdapter()})

    def switch_tts_engine(self, engine_id: str) -> None:
        self.switch_calls.append(engine_id)
        if engine_id not in self.tts_adapters:
            raise ValueError("unknown engine")


class ScriptedPreparingModelManager(ScriptedModelManager):
    def __init__(
        self,
        adapter: Any,
        *,
        ready: bool = False,
        prepare_error: Exception | None = None,
    ) -> None:
        super().__init__(adapters={"qwen3_1_7b": adapter})
        self.ready = ready
        self.prepare_error = prepare_error
        self.prepare_calls: list[dict[str, Any]] = []
        self.released_prompt_leases: list[str] = []

    async def prepare_tts_engine(self, engine_id: str, **kwargs: Any) -> dict[str, Any]:
        self.prepare_calls.append({"engine_id": engine_id, **kwargs})
        if self.prepare_error is not None:
            raise self.prepare_error
        self.ready = True
        return {
            "engine_id": engine_id,
            "model_state": "resident",
            "prompt_state": "ready",
            "voice_key": kwargs["voice_key"],
        }

    def is_tts_prompt_ready(
        self,
        engine_id: str,
        voice_key: str,
        **_kwargs: Any,
    ) -> bool:
        return engine_id == "qwen3_1_7b" and voice_key == "voice-qwen" and self.ready

    async def release_tts_prompt_lease(self, owner: str) -> bool:
        self.released_prompt_leases.append(owner)
        return True

    def health(self) -> dict[str, Any]:
        return {
            "resident_tts_engine": "qwen3_1_7b" if self.ready else None,
            "loading_engine": None,
            "tts_torch_reserved_mib": 5604.0 if self.ready else None,
            "available_engines": [],
            "selected_voice_prompt": {
                "engine_id": "qwen3_1_7b",
                "voice_key": "voice-qwen",
                "state": "ready" if self.ready else "none",
                "error_code": None,
            },
        }


class StubPeerConnection:
    connectionState = "new"

    def __init__(self) -> None:
        self.tracks: list[Any] = []
        self.create_data_channel_calls = 0

    def addTrack(self, track: Any) -> None:
        self.tracks.append(track)

    def createDataChannel(self, label: str) -> Any:
        self.create_data_channel_calls += 1
        return type("StubDataChannel", (), {"label": label, "readyState": "open", "send": lambda self, data: None})()

    def on(self, _event_name: str) -> Any:
        def decorator(handler: Any) -> Any:
            return handler

        return decorator

    async def close(self) -> None:
        return None


@pytest.fixture
def stub_webrtc(monkeypatch: pytest.MonkeyPatch) -> None:
    def create_peer_connection(_offer: Any) -> StubPeerConnection:
        return StubPeerConnection()

    def attach_outbound_audio_track(peer_connection: StubPeerConnection) -> Any:
        track = type("StubAudioTrack", (), {"kind": "audio", "chunks": [], "enqueue": lambda self, chunk: self.chunks.append(chunk)})()
        peer_connection.addTrack(track)
        return track

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)


def _client(*, model_manager: Any | None = None) -> TestClient:
    app = create_app(
        AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN)
    )
    if model_manager is not None:
        app.state.model_manager = model_manager
    return TestClient(app, headers=SERVICE_AUTH_HEADERS)


def _offer_payload(*, session_id: str = "call-session-1") -> dict[str, Any]:
    return {
        "session_id": session_id,
        "thread_id": "thread-1",
        "voice_id": "voice-1",
        "engine_id": "f5",
        "prompt_messages": [
            {"role": "system", "content": "Stay in character."},
            {"role": "user", "content": "Hello before the call."},
        ],
        "offer": {
            "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n",
            "type": "offer",
        },
    }


def test_webrtc_status_exposes_live_call_readiness_and_session_counts() -> None:
    response = _client().get("/webrtc/status")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "status",
        "live_call_ready",
        "media_transport_ready",
        "active_sessions",
    }
    assert isinstance(payload["live_call_ready"], bool)
    assert isinstance(payload["media_transport_ready"], bool)
    assert isinstance(payload["active_sessions"], int)
    assert payload["status"] in {"starting", "ready", "degraded", "unavailable"}


def test_webrtc_status_exposes_deployed_commit_and_separate_qwen_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAYME_DEPLOYED_COMMIT", "a" * 40)
    manager = ScriptedPreparingModelManager(ScriptedStreamingTtsAdapter(), ready=True)

    response = _client(model_manager=manager).get("/webrtc/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployed_commit"] == "a" * 40
    assert payload["tts_model"] == {
        "resident_engine": "qwen3_1_7b",
        "loading_engine": None,
        "torch_reserved_mib": 5604.0,
    }
    assert payload["selected_voice_prompt"] == {
        "engine_id": "qwen3_1_7b",
        "voice_key": "voice-qwen",
        "state": "ready",
        "error_code": None,
    }


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/webrtc/offer", _offer_payload(session_id="auth-probe")),
        (
            "/webrtc/sessions/auth-probe/prepare",
            {
                "voice_id": "voice-1",
                "engine_id": "f5",
                "reference_audio_b64": "cmVmZXJlbmNl",
                "reference_transcript": "Reference transcript.",
            },
        ),
        ("/webrtc/sessions/auth-probe/mute", {"muted": True}),
        ("/webrtc/sessions/auth-probe/interrupt", None),
        ("/webrtc/sessions/auth-probe/turns/turn-1/cancel", None),
        (
            "/webrtc/sessions/auth-probe/speak",
            {
                "turn_id": "turn-1",
                "text": "Protected speech.",
                "voice_id": "voice-1",
                "engine_id": "f5",
            },
        ),
        ("/webrtc/sessions/auth-probe/reconnect-audio", {}),
        ("/webrtc/sessions/auth-probe/events/drain", None),
        ("/webrtc/sessions/auth-probe/end", {"reason": "hangup"}),
    ],
)
def test_webrtc_session_endpoints_reject_missing_service_identity(
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    app = create_app(AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN))
    client = TestClient(app)

    response = client.post(path, json=payload) if payload is not None else client.post(path)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "service_auth_invalid"


def test_webrtc_service_identity_fails_closed_and_rejects_wrong_token() -> None:
    unconfigured = TestClient(create_app(AiBackendSettings()))
    unavailable = unconfigured.post(
        "/webrtc/offer",
        headers=SERVICE_AUTH_HEADERS,
        json=_offer_payload(session_id="auth-unconfigured"),
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "service_auth_not_configured"

    configured = TestClient(
        create_app(AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN))
    )
    rejected = configured.post(
        "/webrtc/offer",
        headers={"Authorization": "Bearer definitely-the-wrong-service-token-000000"},
        json=_offer_payload(session_id="auth-wrong"),
    )
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["code"] == "service_auth_invalid"
    assert configured.get("/webrtc/status").status_code == 200


def test_every_non_public_ai_route_has_shared_service_auth_dependency() -> None:
    app = create_app(AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN))
    public_routes = {("/health", "GET"), ("/webrtc/status", "GET")}

    for route in app.routes:
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", set()):
            if not path.startswith(("/stt", "/tts", "/webrtc")):
                continue
            if (path, method) in public_routes:
                continue
            dependency_calls = {
                dependency.call for dependency in route.dependant.dependencies
            }
            assert require_service_auth in dependency_calls, (method, path)


@pytest.mark.parametrize(
    ("path", "request_kwargs"),
    [
        ("/stt/transcribe", {}),
        (
            "/tts/synthesize",
            {
                "json": {
                    "voice_id": "voice-1",
                    "engine_id": "f5",
                    "text": "Protected synthesis.",
                    "reference_audio_b64": "cmVmZXJlbmNl",
                }
            },
        ),
        (
            "/tts/qwen3/prompts/invalidate",
            {
                "json": {
                    "engine_id": "qwen3_1_7b",
                    "voice_key": "e" * 64,
                }
            },
        ),
    ],
)
def test_stateful_stt_and_tts_routes_reject_missing_service_identity(
    path: str,
    request_kwargs: dict[str, Any],
) -> None:
    client = TestClient(
        create_app(AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN))
    )

    response = client.post(path, **request_kwargs)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "service_auth_invalid"


def test_authorized_service_identity_completes_offer_and_end(
    stub_webrtc: None,
) -> None:
    client = _client()
    session_id = "authorized-end-to-end-call"

    offered = client.post(
        "/webrtc/offer",
        json=_offer_payload(session_id=session_id),
    )
    ended = client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "hangup"},
    )

    assert offered.status_code == 200
    assert ended.status_code == 200
    assert ended.json()["state"] == "ended"


def test_webrtc_prepare_qwen_uses_only_contained_reference_and_exact_transcript(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedStreamingTtsAdapter()
    adapter.engine_id = "qwen3_1_7b"
    manager = ScriptedPreparingModelManager(adapter)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-prepare"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )

    response = client.post(
        f"/webrtc/sessions/{session_id}/prepare",
        json={
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "reference_audio_b64": base64.b64encode(b"contained-reference").decode("ascii"),
            "reference_transcript": "The exact reference transcript.",
            "reference_audio_content_type": "audio/wav",
        },
    )

    assert response.status_code == 200
    assert manager.prepare_calls == [
        {
            "engine_id": "qwen3_1_7b",
            "voice_key": "voice-qwen",
            "reference_audio": b"contained-reference",
            "reference_transcript": "The exact reference transcript.",
            "prompt_lease_owner": session_id,
        }
    ]
    assert response.json()["prompt_state"] == "ready"

    ended = client.post(END_ROUTE_TEMPLATE.format(session_id=session_id), json={})
    assert ended.status_code == 200
    assert manager.released_prompt_leases == [session_id]

    rejected = client.post(
        f"/webrtc/sessions/{session_id}/prepare",
        json={
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "reference_audio_b64": "YQ==",
            "reference_transcript": "The exact reference transcript.",
            "model_path": r"C:\\private\\model",
        },
    )
    assert rejected.status_code == 422
    assert "private" not in rejected.text


@pytest.mark.parametrize("termination", ["hangup", "failure"])
def test_webrtc_slow_prepare_releases_lease_when_session_termination_wins(
    stub_webrtc: None,
    termination: str,
) -> None:
    class SlowLeaseManager(ScriptedPreparingModelManager):
        def __init__(self) -> None:
            super().__init__(ScriptedQwenStreamingTtsAdapter())
            self.prepare_started = asyncio.Event()
            self.release_prepare = asyncio.Event()
            self.owners: set[str] = set()

        async def prepare_tts_engine(
            self,
            engine_id: str,
            **kwargs: Any,
        ) -> dict[str, Any]:
            self.prepare_calls.append({"engine_id": engine_id, **kwargs})
            self.prepare_started.set()
            await self.release_prepare.wait()
            self.owners.add(kwargs["prompt_lease_owner"])
            self.ready = True
            return {
                "engine_id": engine_id,
                "model_state": "resident",
                "prompt_state": "ready",
                "voice_key": kwargs["voice_key"],
            }

        async def release_tts_prompt_lease(self, owner: str) -> bool:
            self.released_prompt_leases.append(owner)
            self.owners.discard(owner)
            return True

    async def scenario() -> tuple[int, set[str], list[str], int]:
        manager = SlowLeaseManager()
        app = create_app(
            AiBackendSettings(service_auth_token=SERVICE_AUTH_TOKEN)
        )
        app.state.model_manager = manager
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=SERVICE_AUTH_HEADERS,
        ) as client:
            session_id = f"call-slow-prepare-{termination}"
            offered = await client.post(
                "/webrtc/offer",
                json={
                    **_offer_payload(session_id=session_id),
                    "voice_id": "voice-qwen",
                    "engine_id": "qwen3_1_7b",
                },
            )
            assert offered.status_code == 200
            prepare = asyncio.create_task(
                client.post(
                    f"/webrtc/sessions/{session_id}/prepare",
                    json={
                        "voice_id": "voice-qwen",
                        "engine_id": "qwen3_1_7b",
                        "reference_audio_b64": "cmVhbC1zYW1wbGU=",
                        "reference_transcript": "The exact reference transcript.",
                    },
                )
            )
            await manager.prepare_started.wait()
            if termination == "hangup":
                terminal = await client.post(
                    END_ROUTE_TEMPLATE.format(session_id=session_id),
                    json={"reason": "hangup"},
                )
                assert terminal.status_code == 200
            else:
                session = app.state.call_session_manager.get_session(session_id)
                assert session is not None
                await session.fail(reason="connection_failed")
            manager.release_prepare.set()
            prepared = await prepare
            assert manager.owners == set()

            recovery_id = f"call-prepare-recovery-{termination}"
            recovered_offer = await client.post(
                "/webrtc/offer",
                json={
                    **_offer_payload(session_id=recovery_id),
                    "voice_id": "voice-other",
                    "engine_id": "qwen3_1_7b",
                },
            )
            assert recovered_offer.status_code == 200
            recovered = await client.post(
                f"/webrtc/sessions/{recovery_id}/prepare",
                json={
                    "voice_id": "voice-other",
                    "engine_id": "qwen3_1_7b",
                    "reference_audio_b64": "cmVhbC1zYW1wbGU=",
                    "reference_transcript": "Another exact transcript.",
                },
            )
            return (
                prepared.status_code,
                set(manager.owners),
                list(manager.released_prompt_leases),
                recovered.status_code,
            )

    prepare_status, owners, released, recovery_status = asyncio.run(scenario())

    assert prepare_status == 409
    assert owners == {f"call-prepare-recovery-{termination}"}
    assert released == [f"call-slow-prepare-{termination}"]
    assert recovery_status == 200


def test_webrtc_prepare_rejects_terminal_session_before_model_acquires_lease(
    stub_webrtc: None,
) -> None:
    manager = ScriptedPreparingModelManager(ScriptedQwenStreamingTtsAdapter())
    client = _client(model_manager=manager)
    session_id = "call-prepare-after-end"
    offered = client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    assert offered.status_code == 200
    assert client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "hangup"},
    ).status_code == 200

    response = client.post(
        f"/webrtc/sessions/{session_id}/prepare",
        json={
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "reference_audio_b64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "The exact reference transcript.",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "call_session_terminal"
    assert manager.prepare_calls == []
    assert manager.released_prompt_leases == []


def test_webrtc_prepare_qwen_maps_alignment_failure_to_actionable_sanitized_code(
    stub_webrtc: None,
) -> None:
    from app.models.tts_qwen3 import Qwen3ValidationError

    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(
        adapter,
        prepare_error=Qwen3ValidationError(
            "Traceback /home/private/.cache full secret transcript",
            code="qwen3_transcript_mismatch",
        ),
    )
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-mismatch"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )

    response = client.post(
        f"/webrtc/sessions/{session_id}/prepare",
        json={
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "reference_audio_b64": base64.b64encode(SCRIPTED_WAV_BYTES).decode("ascii"),
            "reference_transcript": "The exact approved transcript.",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "qwen3_transcript_mismatch",
        "message": "Reference audio and transcript do not match",
        "engine_id": "qwen3_1_7b",
    }
    assert "Traceback" not in response.text
    assert "/home/" not in response.text
    assert "secret transcript" not in response.text


@pytest.mark.parametrize(
    ("error_factory", "expected_status", "expected_code", "should_mark"),
    [
        (
            lambda: __import__(
                "app.models.tts_qwen3", fromlist=["Qwen3ValidationError"]
            ).Qwen3ValidationError(
                "Traceback C:\\private\\voice.wav",
                code="qwen3_transcript_required",
            ),
            422,
            "qwen3_transcript_required",
            False,
        ),
        (
            lambda: __import__(
                "app.models.tts_qwen3", fromlist=["Qwen3WorkerProtocolError"]
            ).Qwen3WorkerProtocolError("Traceback /models/private/cache"),
            502,
            "qwen3_worker_protocol",
            True,
        ),
    ],
)
def test_tts_boundary_maps_qwen_failures_without_poisoning_correctable_voice_errors(
    error_factory: Any,
    expected_status: int,
    expected_code: str,
    should_mark: bool,
) -> None:
    class FailingBoundaryManager:
        def __init__(self) -> None:
            self.tts_adapters = {"qwen3_1_7b": object()}
            self._statuses = {"qwen3_1_7b": object()}
            self.marked: list[tuple[str, str]] = []

        async def prepare_tts_engine(self, _engine_id: str, **_kwargs: Any) -> None:
            raise error_factory()

        def _mark_unavailable(self, engine_id: str, reason: str) -> None:
            self.marked.append((engine_id, reason))

    manager = FailingBoundaryManager()
    client = _client(model_manager=manager)

    response = client.post(
        "/tts/synthesize",
        json={
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "text": "A bounded preview sentence.",
            "reference_audio_b64": base64.b64encode(SCRIPTED_WAV_BYTES).decode("ascii"),
            "reference_transcript": "The exact approved transcript.",
        },
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert bool(manager.marked) is should_mark
    assert "Traceback" not in response.text
    assert "private" not in response.text


def test_webrtc_qwen_speak_requires_matching_prepared_voice(stub_webrtc: None) -> None:
    adapter = ScriptedStreamingTtsAdapter()
    adapter.engine_id = "qwen3_1_7b"
    manager = ScriptedPreparingModelManager(adapter, ready=False)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-not-ready"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-qwen-not-ready",
            "text": "This is one safe target segment.",
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "final_chunk": True,
            "reference_audio_b64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "The exact reference transcript.",
            "model_path": r"C:\\private\\model",
        },
    )
    assert response.status_code == 422
    assert "private" not in response.text

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-qwen-not-ready",
            "text": "This is one safe target segment.",
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "final_chunk": True,
            "reference_audio_b64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "The exact reference transcript.",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "call_tts_not_ready",
        "message": "Selected voice is not ready",
        "engine_id": "qwen3_1_7b",
    }


def test_webrtc_offer_creates_session_answer_and_events_channel(stub_webrtc: None) -> None:
    client = _client()
    response = client.post("/webrtc/offer", json=_offer_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "call-session-1"
    assert payload["answer"]["type"] == "answer"
    assert isinstance(payload["answer"]["sdp"], str)
    assert payload["answer"]["sdp"].startswith("v=0")
    assert payload["data_channel"]["label"] == "rayme-events"
    session = client.app.state.call_session_manager.get_session("call-session-1")
    assert session.peer_connection.create_data_channel_calls == 0
    assert session.outbound_audio_track is not None
    assert session.outbound_audio_track.kind == "audio"


def test_reconnect_offer_rejects_explicitly_ended_session_before_allocating_media(
    monkeypatch: pytest.MonkeyPatch,
    stub_webrtc: None,
) -> None:
    client = _client()
    session_id = "reconnect-after-explicit-hangup"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)
    original_peer = session.peer_connection
    asyncio.run(session.end(reason="hangup"))
    allocation_calls = 0

    def reject_allocation(_offer: Any) -> Any:
        nonlocal allocation_calls
        allocation_calls += 1
        raise AssertionError("terminal offers must not allocate a peer")

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", reject_allocation)

    replacement = client.post(
        "/webrtc/offer",
        json=_offer_payload(session_id=session_id),
    )

    assert replacement.status_code == 409
    assert replacement.json()["detail"] == {
        "code": "call_session_terminal",
        "message": "Call session has ended; start a new call",
    }
    assert allocation_calls == 0
    assert session.peer_connection is original_peer
    assert session.state == "ended"
    assert session.end_reason == "hangup"


def test_concurrent_hangup_wins_before_reconnect_candidate_registration(
    monkeypatch: pytest.MonkeyPatch,
    stub_webrtc: None,
) -> None:
    client = _client()
    session_id = "reconnect-races-explicit-hangup"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)

    registration_reached = threading.Event()
    allow_registration = threading.Event()
    original_register = session.mark_peer_connection_pending
    allocated_peers: list[Any] = []

    class TrackingPeerConnection(StubPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    def create_peer_connection(_offer: Any) -> TrackingPeerConnection:
        peer = TrackingPeerConnection()
        allocated_peers.append(peer)
        return peer

    async def blocked_register(*args: Any, **kwargs: Any) -> int:
        registration_reached.set()
        await asyncio.to_thread(allow_registration.wait)
        return await original_register(*args, **kwargs)

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(session, "mark_peer_connection_pending", blocked_register)
    responses: list[Any] = []

    offer_thread = threading.Thread(
        target=lambda: responses.append(
            client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
        )
    )
    offer_thread.start()
    try:
        assert registration_reached.wait(2)
        asyncio.run(session.end(reason="hangup"))
    finally:
        allow_registration.set()
        offer_thread.join(2)

    assert not offer_thread.is_alive()
    assert responses[0].status_code == 409
    assert responses[0].json()["detail"]["code"] == "call_session_terminal"
    assert session.state == "ended"
    assert session._pending_peer_connections == []
    assert len(allocated_peers) == 1
    assert allocated_peers[0].close_calls == 1


def test_failed_reconnect_offer_preserves_existing_session_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peers: list[Any] = []
    tracks: list[Any] = []

    class TrackingPeerConnection(StubPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    class TrackingAudioTrack:
        kind = "audio"

        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            self.chunks.append(chunk)
            return 0.1

    def create_peer_connection(_offer: Any) -> TrackingPeerConnection:
        peer = TrackingPeerConnection()
        peers.append(peer)
        return peer

    def attach_outbound_audio_track(peer_connection: TrackingPeerConnection) -> TrackingAudioTrack:
        track = TrackingAudioTrack()
        tracks.append(track)
        peer_connection.addTrack(track)
        return track

    negotiate_calls = 0

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        nonlocal negotiate_calls
        negotiate_calls += 1
        if negotiate_calls == 2:
            raise RuntimeError("simulated reconnect negotiation failure")
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)

    client = _client()
    session_id = "reconnect-preserve-session"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)
    original_peer = session.peer_connection
    original_track = session.outbound_audio_track

    failed_payload = {
        **_offer_payload(session_id=session_id),
        "thread_id": "failed-thread",
        "voice_id": "failed-voice",
        "engine_id": "voxcpm2",
        "prompt_messages": [{"role": "system", "content": "Failed prompt."}],
    }
    second = client.post("/webrtc/offer", json=failed_payload)

    assert second.status_code == 502
    assert len(peers) == 2
    assert len(tracks) == 2
    assert session.peer_connection is original_peer
    assert session.outbound_audio_track is original_track
    assert original_peer.close_calls == 0
    assert session.thread_id == "thread-1"
    assert session.voice_id == "voice-1"
    assert session.engine_id == "f5"
    assert session.prompt_messages == [
        {"role": "system", "content": "Stay in character."},
        {"role": "user", "content": "Hello before the call."},
    ]


def test_speak_uses_only_configuration_of_accepted_reoffer(
    stub_webrtc: None,
) -> None:
    manager = ScriptedModelManager(
        adapters={
            "f5": ScriptedTtsAdapter(),
            "voxcpm2": ScriptedStreamingTtsAdapter(),
        }
    )
    client = _client(model_manager=manager)
    session_id = "speak-accepted-config-only"
    assert client.post(
        "/webrtc/offer",
        json=_offer_payload(session_id=session_id),
    ).status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)

    def reoffer(voice_id: str) -> Any:
        return client.post(
            "/webrtc/offer",
            json={
                **_offer_payload(session_id=session_id),
                "voice_id": voice_id,
                "engine_id": "voxcpm2",
            },
        )

    def speak(turn_id: str, voice_id: str, engine_id: str) -> Any:
        payload = {
            "turn_id": turn_id,
            "text": "Only the accepted configuration may speak.",
            "voice_id": voice_id,
            "engine_id": engine_id,
            "final_chunk": True,
        }
        if engine_id == "voxcpm2":
            payload.update(
                {
                    "reference_audio_b64": "cmVhbC1zYW1wbGU=",
                    "reference_transcript": "The exact reference transcript.",
                }
            )
        return client.post(
            SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
            json=payload,
        )

    assert reoffer("pending-voice").status_code == 200
    pending = session._peer_lifecycle.candidate
    assert pending is not None
    pending_mismatch = speak("turn-pending", "pending-voice", "voxcpm2")
    assert pending_mismatch.status_code == 409
    assert pending_mismatch.json()["detail"]["code"] == "call_speech_selection_mismatch"

    asyncio.run(
        session.reject_pending_peer_connection(
            pending.peer_connection,
            generation=pending.generation,
        )
    )
    assert speak("turn-failed", "pending-voice", "voxcpm2").status_code == 409

    assert reoffer("superseded-voice").status_code == 200
    superseded = session._peer_lifecycle.candidate
    assert superseded is not None
    assert reoffer("accepted-voice").status_code == 200
    accepted = session._peer_lifecycle.candidate
    assert accepted is not None and accepted is not superseded
    assert speak("turn-superseded", "superseded-voice", "voxcpm2").status_code == 409
    assert speak("turn-unaccepted", "accepted-voice", "voxcpm2").status_code == 409

    accepted_result, _ = asyncio.run(
        session.accept_pending_peer_connection(
            accepted.peer_connection,
            generation=accepted.generation,
        )
    )
    assert accepted_result is True
    assert speak("turn-old-after-accept", "voice-1", "f5").status_code == 409
    assert speak("turn-accepted", "accepted-voice", "voxcpm2").status_code == 200


def test_cancelled_reconnect_offer_preserves_existing_session_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peers: list[Any] = []
    tracks: list[Any] = []

    class TrackingPeerConnection(StubPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    class TrackingAudioTrack:
        kind = "audio"

        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            self.chunks.append(chunk)
            return 0.1

    def create_peer_connection(_offer: Any) -> TrackingPeerConnection:
        peer = TrackingPeerConnection()
        peers.append(peer)
        return peer

    def attach_outbound_audio_track(peer_connection: TrackingPeerConnection) -> TrackingAudioTrack:
        track = TrackingAudioTrack()
        tracks.append(track)
        peer_connection.addTrack(track)
        return track

    negotiate_calls = 0

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        nonlocal negotiate_calls
        negotiate_calls += 1
        if negotiate_calls == 2:
            raise asyncio.CancelledError()
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)

    client = _client()
    session_id = "reconnect-cancel-preserve-session"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)
    original_peer = session.peer_connection
    original_track = session.outbound_audio_track

    with pytest.raises((asyncio.CancelledError, FutureCancelledError)):
        client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    assert len(peers) == 2
    assert len(tracks) == 2
    assert session.peer_connection is original_peer
    assert session.outbound_audio_track is original_track
    assert original_peer.close_calls == 0
    assert peers[1].close_calls == 1


def test_inflight_reconnect_offer_does_not_steal_active_session_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    peers: list[Any] = []
    tracks: list[Any] = []

    class TrackingPeerConnection(StubPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0
            self.iceConnectionState = "new"
            self.handlers: dict[str, Any] = {}

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        async def close(self) -> None:
            self.close_calls += 1

        async def emit_connected(self) -> None:
            self.connectionState = "connected"
            self.iceConnectionState = "connected"
            handler = self.handlers["connectionstatechange"]
            result = handler()
            if asyncio.iscoroutine(result):
                await result

    class TrackingAudioTrack:
        kind = "audio"

        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            self.chunks.append(chunk)
            return 0.1

    def create_peer_connection(_offer: Any) -> TrackingPeerConnection:
        peer = TrackingPeerConnection()
        peers.append(peer)
        return peer

    def attach_outbound_audio_track(peer_connection: TrackingPeerConnection) -> TrackingAudioTrack:
        track = TrackingAudioTrack()
        tracks.append(track)
        peer_connection.addTrack(track)
        return track

    reconnect_offer_started = threading.Event()
    release_reconnect_offer = threading.Event()
    negotiate_calls = 0

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        nonlocal negotiate_calls
        negotiate_calls += 1
        if negotiate_calls == 2:
            reconnect_offer_started.set()
            await asyncio.to_thread(release_reconnect_offer.wait)
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)

    client = _client()
    session_id = "reconnect-inflight-preserve-session"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)
    original_peer = session.peer_connection
    original_track = session.outbound_audio_track
    responses: list[Any] = []
    errors: list[BaseException] = []
    accepted_payload = {
        **_offer_payload(session_id=session_id),
        "thread_id": "accepted-thread",
        "voice_id": "accepted-voice",
        "engine_id": "voxcpm2",
        "prompt_messages": [{"role": "system", "content": "Accepted prompt."}],
    }

    def post_reconnect_offer() -> None:
        try:
            responses.append(
                client.post("/webrtc/offer", json=accepted_payload)
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=post_reconnect_offer)
    thread.start()
    try:
        assert reconnect_offer_started.wait(2)
        assert len(peers) == 2
        assert len(tracks) == 2
        assert session.peer_connection is original_peer
        assert session.outbound_audio_track is original_track
        assert peers[1] in session._pending_peer_connections
        assert session.thread_id == "thread-1"
        assert session.engine_id == "f5"
    finally:
        release_reconnect_offer.set()
        thread.join(2)

    assert not thread.is_alive()
    assert errors == []
    assert responses[0].status_code == 200
    assert session.peer_connection is original_peer
    assert session.outbound_audio_track is original_track
    assert peers[1] in session._pending_peer_connections
    assert original_peer.close_calls == 0

    asyncio.run(peers[1].emit_connected())

    assert session.peer_connection is peers[1]
    assert session.outbound_audio_track is tracks[1]
    assert original_peer.close_calls == 1
    assert session.thread_id == "accepted-thread"
    assert session.voice_id == "accepted-voice"
    assert session.engine_id == "voxcpm2"
    assert session.prompt_messages == [
        {"role": "system", "content": "Accepted prompt."}
    ]


@pytest.mark.parametrize(
    ("candidate_event", "candidate_state_attribute"),
    [
        ("connectionstatechange", "connectionState"),
        ("iceconnectionstatechange", "iceConnectionState"),
    ],
)
def test_failed_replacement_callback_leaves_active_close_to_reconnect_grace(
    candidate_event: str,
    candidate_state_attribute: str,
) -> None:
    from app.call.session import CallSession

    class CallbackPeer:
        def __init__(self) -> None:
            self.connectionState = "new"
            self.iceConnectionState = "new"
            self.handlers: dict[str, Any] = {}
            self.close_calls = 0

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        async def close(self) -> None:
            self.close_calls += 1

    async def scenario() -> tuple[CallSession, CallbackPeer, CallbackPeer]:
        active_peer = CallbackPeer()
        candidate = CallbackPeer()
        session = CallSession(
            session_id=f"replacement-fails-{candidate_event}",
            peer_connection=active_peer,
        )
        generation = await session.mark_peer_connection_pending(
            candidate,
            timeout_seconds=60.0,
        )
        webrtc_module._attach_peer_handlers(active_peer, session)
        webrtc_module._attach_peer_handlers(
            candidate,
            session,
            pending_generation=generation,
        )

        active_peer.connectionState = "closed"
        await active_peer.handlers["connectionstatechange"]()
        assert session.state == "reconnecting"
        assert session.ended_at is None

        setattr(candidate, candidate_state_attribute, "failed")
        await candidate.handlers[candidate_event]()
        assert candidate.close_calls == 1
        assert active_peer.close_calls == 0
        assert session.state == "reconnecting"

        await session.resolve_deferred_connection_state()
        return session, active_peer, candidate

    session, active_peer, candidate = asyncio.run(scenario())

    assert candidate.close_calls == 1
    assert active_peer.close_calls == 1
    assert session._pending_peer_connections == []
    assert session.state == "ended"
    assert session.end_reason == "connection_closed"


@pytest.mark.parametrize(
    ("recovery_event", "recovery_attribute", "recovery_state"),
    [
        ("connectionstatechange", "connectionState", "connected"),
        ("iceconnectionstatechange", "iceConnectionState", "completed"),
    ],
)
def test_active_peer_self_recovery_cancels_receiver_timeout_grace(
    recovery_event: str,
    recovery_attribute: str,
    recovery_state: str,
) -> None:
    from app.call.session import CallSession

    class CallbackPeer:
        def __init__(self) -> None:
            self.connectionState = "disconnected"
            self.iceConnectionState = "disconnected"
            self.handlers: dict[str, Any] = {}
            self.close_calls = 0

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        async def close(self) -> None:
            self.close_calls += 1

    released_owners: list[str] = []

    async def scenario() -> tuple[CallSession, CallbackPeer, int]:
        peer = CallbackPeer()
        session = CallSession(
            session_id=f"active-self-recovers-{recovery_event}",
            peer_connection=peer,
        )
        await session.install_or_release_tts_prompt_lease(
            lambda owner: released_owners.append(owner)
        )
        webrtc_module._attach_peer_handlers(peer, session)

        await webrtc_module._handle_receiver_peer_terminal(
            session,
            peer,
            pending_generation=None,
            terminal_state="failed",
        )
        reconnect_epoch = session._peer_lifecycle.epoch
        assert session.state == "reconnecting"

        setattr(peer, recovery_attribute, recovery_state)
        await peer.handlers[recovery_event]()

        assert session.state == "listening"
        assert session.ended_at is None
        assert await session.resolve_deferred_connection_state(
            epoch=reconnect_epoch,
            peer_connection=peer,
        ) is False
        return session, peer, reconnect_epoch

    session, peer, _ = asyncio.run(scenario())

    assert peer.close_calls == 0
    assert released_owners == []
    assert session._peer_lifecycle.grace_task is None


def test_webrtc_mute_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        MUTE_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"muted": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] in {"listening", "muted"}
    assert payload["muted"] is True


def test_webrtc_interrupt_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    session = client.app.state.call_session_manager.get_session(session_id)
    session._active_tts_turn_id = "turn-interrupted-01"

    response = client.post(INTERRUPT_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] in {"listening", "interrupted"}
    assert payload["cancelled_turn_id"] == "turn-interrupted-01"
    assert payload["receiver_drain_ms"] == 250


def test_webrtc_reoffer_engine_switch_cancels_exact_active_qwen_request(
    stub_webrtc: None,
) -> None:
    adapter = BlockingQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-engine-switch"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    responses: list[Any] = []

    def speak() -> None:
        responses.append(
            client.post(
                SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
                json={
                    "turn_id": "turn-qwen-engine-switch",
                    "text": "This request must stop before the engine changes.",
                    "voice_id": "voice-qwen",
                    "engine_id": "qwen3_1_7b",
                    "final_chunk": True,
                    "reference_audio_b64": "cmVhbC1zYW1wbGU=",
                    "reference_transcript": "The exact reference transcript.",
                },
            )
        )

    thread = threading.Thread(target=speak)
    thread.start()
    try:
        assert adapter.stream_started.wait(1.0)
        switched = client.post(
            "/webrtc/offer",
            json={
                **_offer_payload(session_id=session_id),
                "voice_id": "voice-f5",
                "engine_id": "f5",
            },
        )
        assert switched.status_code == 200
        session = client.app.state.call_session_manager.get_session(session_id)
        candidate = session._peer_lifecycle.candidate
        assert candidate is not None
        accepted, _ = asyncio.run(
            session.accept_pending_peer_connection(
                candidate.peer_connection,
                generation=candidate.generation,
            )
        )
        assert accepted is True
    finally:
        adapter.release_stream.set()
        thread.join(2.0)

    assert not thread.is_alive()
    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert adapter.stream_identities == [
        (adapter.cancel_calls[0], "voice-qwen")
    ]
    assert responses and responses[0].status_code == 502
    assert responses[0].json()["detail"] == {
        "code": "call_tts_failed",
        "message": "Speech playback cancelled",
        "engine_id": "qwen3_1_7b",
    }


def test_webrtc_speak_synthesizes_with_exact_engine_and_emits_done(stub_webrtc: None) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapter)
    client = _client(model_manager=manager)
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-1",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
            "final_chunk": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["f5"]
    assert adapter.calls == [
        {
            "turn_id": "ai-turn-1",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
        }
    ]
    assert payload["event"]["type"] == "ai_done"
    assert payload["event"]["turn_id"] == "ai-turn-1"


def test_webrtc_speak_accepts_bounded_voxcpm2_options(stub_webrtc: None) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-options"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "Real VoxCPM2 reference text.",
            "reference_audio_content_type": "audio/wav",
            "voxcpm2_cloning_mode": "transcript_guided",
            "voxcpm2_style_prompt": "warm phone call voice",
            "voxcpm2_cfg_value": 2.4,
            "voxcpm2_inference_timesteps": 12,
            "voxcpm2_normalize": True,
            "voxcpm2_denoise": False,
        },
    )

    assert response.status_code == 200
    assert manager.switch_calls == ["voxcpm2"]
    assert adapter.calls == [
        {
            "turn_id": "ai-turn-voxcpm2",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "voxcpm2_cloning_mode": "transcript_guided",
            "voxcpm2_style_prompt": "warm phone call voice",
            "voxcpm2_cfg_value": 2.4,
            "voxcpm2_inference_timesteps": 12,
            "voxcpm2_normalize": True,
            "voxcpm2_denoise": False,
        }
    ]


def test_webrtc_speak_returns_streaming_tts_playback_metrics_for_voxcpm2(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedStreamingTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-streaming"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-streaming",
            "text": "Hello from VoxCPM2 streaming.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "Real VoxCPM2 reference text.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["voxcpm2"]
    assert len(adapter.calls) == 1
    assert payload["event"]["type"] == "ai_done"

    started_event = payload["event"]["ai_audio_started_event"]
    assert started_event["type"] == "ai_audio_started"
    started_playback = started_event["tts_playback"]
    assert started_playback["streaming_used"] is True
    assert started_playback["chunk_count_at_start"] == 2
    assert "buffered_until_complete" not in started_playback
    assert "total_generation_ms" not in started_playback
    assert "total_playback_ms" not in started_playback

    final_playback = payload["event"]["tts_playback_final"]
    assert final_playback["streaming_used"] is True
    assert final_playback["chunk_count"] >= 1
    assert math.isfinite(final_playback["total_generation_ms"])
    assert math.isfinite(final_playback["total_playback_ms"])
    assert isinstance(final_playback["inter_chunk_gaps_ms"], list)


def test_webrtc_prepared_qwen_speak_uses_native_stream_and_truthful_carriers(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-streaming"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-qwen-streaming",
            "text": "Hello from native Qwen streaming.",
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
            "final_chunk": True,
            "reference_audio_b64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "The exact reference transcript.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(adapter.stream_identities) == 1
    assert adapter.stream_identities[0][0].startswith("tts-segment-")
    assert adapter.stream_identities[0][1] == "voice-qwen"
    assert payload["event"]["type"] == "ai_done"
    immediate = payload["event"]["ai_audio_started_event"]["tts_playback"]
    assert immediate["streaming_used"] is True
    assert immediate["whole_wav_fallback_used"] is False
    assert "total_generation_ms" not in immediate
    final = payload["event"]["tts_playback_final"]
    assert final["bridge_queue_capacity"] == 2
    assert final["bridge_queue_high_water"] <= 2
    assert "source_audio_sha256" not in final
    assert adapter.calls[0].qwen3_release_evidence_mode is None
    assert adapter.calls[0].qwen3_release_evidence_seed is None


def test_webrtc_qwen_empty_final_marker_terminalizes_without_repeating_synthesis(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-empty-terminal"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    common = {
        "turn_id": "ai-turn-qwen-empty-terminal",
        "voice_id": "voice-qwen",
        "engine_id": "qwen3_1_7b",
        "reference_audio_b64": "cmVhbC1zYW1wbGU=",
        "reference_transcript": "The exact reference transcript.",
    }

    rejected = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={**common, "text": "", "final_chunk": False},
    )
    assert rejected.status_code == 422

    segment = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            **common,
            "text": "This sentence was already played as an early segment.",
            "final_chunk": False,
        },
    )
    assert segment.status_code == 200
    segment_payload = segment.json()
    assert segment_payload["state"] == "speaking"
    assert segment_payload["event"]["status"] == "queued"
    assert segment_payload["event"]["tts_playback_final"]["playout_wait_completed"] is None
    assert len(adapter.stream_identities) == 1
    assert adapter.stream_identities[0][0].startswith("tts-segment-")
    assert adapter.stream_identities[0][1] == "voice-qwen"

    terminal = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={**common, "text": "", "final_chunk": True},
    )
    assert terminal.status_code == 200
    terminal_payload = terminal.json()
    assert terminal_payload["state"] == "listening"
    terminal_event = terminal_payload["event"]
    assert terminal_event["type"] == "ai_done"
    assert terminal_event["tts_playback_final"]["playout_wait_completed"] is True
    assert terminal_event["tts_playback_final"]["chunk_count"] == segment_payload[
        "event"
    ]["tts_playback_final"]["chunk_count"]
    assert len(adapter.stream_identities) == 1
    assert adapter.stream_identities[0][0].startswith("tts-segment-")
    assert adapter.stream_identities[0][1] == "voice-qwen"


def test_webrtc_qwen_interrupt_cancels_pending_empty_terminal(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "call-session-qwen-interrupt-pending-terminal"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    session = client.app.state.call_session_manager.get_session(session_id)
    emitted_events: list[dict[str, Any]] = []
    session.event_sink = emitted_events.append
    common = {
        "turn_id": "ai-turn-qwen-interrupt-pending-terminal",
        "voice_id": "voice-qwen",
        "engine_id": "qwen3_1_7b",
        "reference_audio_b64": "cmVhbC1zYW1wbGU=",
        "reference_transcript": "The exact reference transcript.",
    }

    segment = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            **common,
            "text": "This early segment finished before the user interrupted.",
            "final_chunk": False,
        },
    )
    assert segment.status_code == 200
    assert segment.json()["state"] == "speaking"

    interrupted = client.post(
        INTERRUPT_ROUTE_TEMPLATE.format(session_id=session_id)
    )
    assert interrupted.status_code == 200
    assert interrupted.json()["state"] == "listening"

    late_terminal = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={**common, "text": "", "final_chunk": True},
    )
    assert late_terminal.status_code == 409
    assert late_terminal.json()["detail"]["code"] == "call_speech_turn_terminal"
    assert not any(event.get("type") == "ai_done" for event in emitted_events)
    assert len(adapter.stream_identities) == 1
    assert adapter.stream_identities[0][0].startswith("tts-segment-")
    assert adapter.stream_identities[0][1] == "voice-qwen"


def test_webrtc_turn_cancel_endpoint_is_idempotent_and_tombstones_turn(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "call-session-turn-cancel"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    common = {
        "turn_id": "ai-turn-web-cancel",
        "voice_id": "voice-qwen",
        "engine_id": "qwen3_1_7b",
        "reference_audio_b64": "cmVhbC1zYW1wbGU=",
        "reference_transcript": "The exact reference transcript.",
    }
    segment = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            **common,
            "text": "This admitted segment is owned by the cancelled web turn.",
            "final_chunk": False,
            "segment_id": "ai-turn-web-cancel:0",
            "segment_ordinal": 0,
        },
    )
    assert segment.status_code == 200

    cancel_path = (
        f"/webrtc/sessions/{session_id}/turns/ai-turn-web-cancel/cancel"
    )
    first = client.post(cancel_path)
    retry = client.post(cancel_path)
    assert first.status_code == 200
    assert retry.json() == first.json()
    assert first.json()["state"] == "listening"

    late = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            **common,
            "text": "",
            "final_chunk": True,
            "segment_id": "ai-turn-web-cancel:1",
            "segment_ordinal": 1,
        },
    )
    assert late.status_code == 409
    assert late.json()["detail"]["code"] == "call_speech_turn_terminal"


def test_webrtc_qwen_release_evidence_seed_requires_explicit_evidence_session_and_propagates(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedQwenStreamingTtsAdapter()
    manager = ScriptedPreparingModelManager(adapter, ready=True)
    client = _client(model_manager=manager)
    session_id = "phase09-evidence-seed-contract"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    base = {
        "turn_id": "evidence-anchor-01",
        "text": "A deterministic release evidence anchor.",
        "voice_id": "voice-qwen",
        "engine_id": "qwen3_1_7b",
        "final_chunk": True,
        "reference_audio_b64": "cmVhbC1zYW1wbGU=",
        "reference_transcript": "The exact reference transcript.",
    }

    accepted = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            **base,
            "release_evidence_mode": "phase09_release_evidence",
            "release_evidence_seed": 91_001,
        },
    )
    assert accepted.status_code == 200
    source_audio_sha256 = accepted.json()["event"]["tts_playback_final"][
        "source_audio_sha256"
    ]
    assert len(source_audio_sha256) == 64
    int(source_audio_sha256, 16)
    assert adapter.calls[-1].qwen3_release_evidence_mode == "phase09_release_evidence"
    assert adapter.calls[-1].qwen3_release_evidence_seed == 91_001

    invalid_payloads = (
        {**base, "release_evidence_mode": "phase09_release_evidence"},
        {**base, "release_evidence_seed": 91_001},
        {
            **base,
            "release_evidence_mode": "ordinary_call",
            "release_evidence_seed": 91_001,
        },
    )
    for payload in invalid_payloads:
        assert client.post(
            SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
            json=payload,
        ).status_code == 422

    ordinary_session = "ordinary-live-call"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=ordinary_session),
            "voice_id": "voice-qwen",
            "engine_id": "qwen3_1_7b",
        },
    )
    rejected = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=ordinary_session),
        json={
            **base,
            "release_evidence_mode": "phase09_release_evidence",
            "release_evidence_seed": 91_001,
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "qwen_release_evidence_scope_invalid"


def test_webrtc_speak_streaming_failure_keeps_fixed_public_error(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedStreamingTtsAdapter(fail="before_first_audio")
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-streaming-fail"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-streaming-fail",
            "text": "Hello from a failing VoxCPM2 stream.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "call_tts_failed",
        "message": "Speech playback failed",
        "engine_id": "voxcpm2",
    }
    assert "Traceback" not in response.text
    assert "/home/" not in response.text
    assert ".cache" not in response.text
    assert "openbmb/VoxCPM2" not in response.text

    late_failure_adapter = ScriptedStreamingTtsAdapter(fail="after_first_audio")
    late_session_id = "call-session-voxcpm2-streaming-late-fail"
    client.post(
        "/webrtc/offer",
        json={**_offer_payload(session_id=late_session_id), "engine_id": "voxcpm2"},
    )
    session = client.app.state.call_session_manager.get_session(late_session_id)
    event = asyncio.run(
        session.speak_text(
            "ai-turn-voxcpm2-streaming-late-fail",
            "Hello from a late failing VoxCPM2 stream.",
            "voice-voxcpm2",
            "voxcpm2",
            final_chunk=True,
            tts_adapter=late_failure_adapter,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
        )
    )

    assert event["type"] == "failed"
    assert event["code"] == "call_tts_failed"
    assert "ai_audio_started_event" not in event
    assert event["tts_playback_final"]["streaming_used"] is True
    assert event["tts_playback_final"]["chunk_count"] == 1


def test_webrtc_speak_rejects_reference_audio_over_web_ui_limit(
    monkeypatch: pytest.MonkeyPatch,
    stub_webrtc: None,
) -> None:
    monkeypatch.setattr(webrtc_module, "MAX_REFERENCE_AUDIO_BYTES", len(b"real-sample") - 1)
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-reference-too-large"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
        },
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-reference-too-large",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "reference_audio_base64": base64.b64encode(b"real-sample").decode("ascii"),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "call_tts_reference_audio_too_large",
        "message": "Reference audio is too large",
    }
    assert adapter.calls == []


def test_webrtc_speak_rejects_unbounded_voxcpm2_options_with_sanitized_422(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-invalid"
    client.post(
        "/webrtc/offer",
        json={
            **_offer_payload(session_id=session_id),
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
        },
    )

    invalid = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-invalid",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "voxcpm2_cloning_mode": "invalid",
            "voxcpm2_style_prompt": (
                "Traceback /home/pmpg/.cache/model-cache "
                r"C:\Users\pmpg\rayme\model-cache "
            )
            * 30,
            "voxcpm2_cfg_value": 99,
            "voxcpm2_inference_timesteps": 500,
        },
    )

    assert invalid.status_code == 422
    assert "Traceback" not in invalid.text
    assert "/home/" not in invalid.text
    assert r"C:\\" not in invalid.text
    assert "model-cache" not in invalid.text


@pytest.mark.parametrize("engine_id", ["voxcpm2", "f5"])
def test_webrtc_speak_failure_returns_fixed_call_tts_failed_code_for_dual_engines(
    stub_webrtc: None,
    engine_id: str,
) -> None:
    if engine_id == "voxcpm2":
        manager = ScriptedModelManager(
            adapters={"voxcpm2": ScriptedStreamingTtsAdapter(fail="before_first_audio")}
        )
        payload = {
            "turn_id": "ai-turn-fail",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": engine_id,
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
        }
    else:
        manager = ScriptedModelManager(ScriptedTtsAdapter(fail=True))
        payload = {
            "turn_id": "ai-turn-fail",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": engine_id,
            "final_chunk": True,
        }

    client = _client(model_manager=manager)
    session_id = "call-session-1"
    client.post(
        "/webrtc/offer",
        json={**_offer_payload(session_id=session_id), "engine_id": engine_id},
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json=payload,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "call_tts_failed",
        "message": "Speech playback failed",
        "engine_id": engine_id,
    }
    assert "raw model failure" not in response.text
    assert "Traceback" not in response.text
    assert "File " not in response.text
    assert "/home/" not in response.text
    assert r"C:\\" not in response.text
    assert "model-cache" not in response.text


def test_webrtc_end_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "hangup"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] == "ended"
    assert payload["reason"] == "hangup"


def test_webrtc_reconnect_audio_backfill_appends_to_call_session(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    pcm = np.full(640, 2000, dtype=np.int16).tobytes()

    response = client.post(
        RECONNECT_AUDIO_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "pcm_b64": base64.b64encode(pcm).decode("ascii"),
            "sample_rate": 16000,
            "channels": 1,
            "backfill_id": "gap-route-1",
            "reason": "failed",
            "attempt": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["status"] == "accepted"
    assert payload["frames"] == 2
    session = client.app.state.call_session_manager.get_session(session_id)
    assert len(session._turn_frames) == 2


def test_webrtc_events_drain_returns_undelivered_user_final(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    session = client.app.state.call_session_manager.get_session(session_id)
    session.data_channel = type(
        "ClosedDataChannel",
        (),
        {"readyState": "closed", "send": lambda self, data: None},
    )()

    import asyncio

    asyncio.run(
        session.emit_event(
            {
                "type": "user_final",
                "session_id": session_id,
                "turn_id": "user-turn-1",
                "text": "Recovered text",
            }
        )
    )

    response = client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["events"] == [
        {
            "type": "user_final",
            "session_id": session_id,
            "turn_id": "user-turn-1",
            "text": "Recovered text",
        }
    ]
    assert client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id)).json()["events"] == []


def test_webrtc_events_drain_returns_late_user_final_after_end(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-late-end"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    session = client.app.state.call_session_manager.get_session(session_id)
    session.data_channel = type(
        "ClosedDataChannel",
        (),
        {"readyState": "closed", "send": lambda self, data: None},
    )()

    end_response = client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "connection_failed"},
    )
    assert end_response.status_code == 200
    assert client.app.state.call_session_manager.stats()["active_sessions"] == 0

    import asyncio

    asyncio.run(
        session.emit_event(
            {
                "type": "user_final",
                "session_id": session_id,
                "turn_id": "user-turn-after-end",
                "text": "Recovered text after end",
            }
        )
    )

    response = client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["events"] == [
        {
            "type": "user_final",
            "session_id": session_id,
            "turn_id": "user-turn-after-end",
            "text": "Recovered text after end",
        }
    ]


def test_webrtc_offer_malformed_payload_returns_sanitized_validation_error() -> None:
    response = _client().post(
        "/webrtc/offer",
        json={
            "session_id": "call-session-1",
            "offer": {"type": "offer"},
        },
    )

    assert response.status_code in {400, 422}
    assert "Traceback" not in response.text
    assert "File " not in response.text


def test_webrtc_offer_rejects_non_media_offer_instead_of_inventing_answer() -> None:
    response = _client().post("/webrtc/offer", json=_offer_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "webrtc_offer_failed",
        "message": "WebRTC offer could not be accepted",
    }
    assert "RayMe test answer" not in response.text


def test_receive_audio_track_media_stream_error_with_live_ice_does_not_fail_session() -> None:
    """MediaStreamError raised while ICE=completed/connected must NOT call session.fail().

    Regression for: Android Chrome stops sending audio frames after the user
    finishes speaking; aiortc raises MediaStreamError; the old fallthrough
    called session.fail() which destroyed the outbound audio track and prevented
    in-flight TTS from being delivered.
    """
    import asyncio

    from app.call.session import CallSessionManager
    from app.call.tracks import QueuedAudioOutputTrack
    from app.config import AiBackendSettings

    class MediaStreamError(Exception):
        pass

    class ScriptedInboundTrack:
        kind = "audio"
        id = "inbound-1"
        calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            # Raise immediately — the error path is what we are testing, not
            # frame processing.  ICE and conn states are still "alive" so the
            # fallthrough must NOT call session.fail().
            raise MediaStreamError("end of stream")

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"
        close_calls: int = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def _run_test() -> tuple[int, str, int]:
        settings = AiBackendSettings()
        manager = CallSessionManager(settings=settings)
        pc = LivePeerConnection()
        outbound_track = QueuedAudioOutputTrack()
        session = await manager.create_session(
            session_id="test-media-stream-error",
            thread_id="thread-1",
            voice_id="voice-1",
            engine_id="f5",
            prompt_messages=[],
            peer_connection=pc,
            vad_adapter=None,
            stt_adapter=None,
            outbound_audio_track=outbound_track,
        )
        track = ScriptedInboundTrack()
        task = asyncio.create_task(webrtc_module._receive_audio_track(session, track))
        await asyncio.sleep(0.25)
        session.state = "ended"
        await task
        return pc.close_calls, session.state, track.calls

    close_calls, state, recv_calls = asyncio.run(_run_test())

    assert close_calls == 0, (
        "peer_connection.close() must NOT be called when MediaStreamError fires "
        "while ICE/conn are still alive (ice=completed conn=connected)"
    )
    assert state not in {"failed"}, (
        f"session.fail() must NOT be called; got state={state!r}"
    )
    assert recv_calls > 1


def test_receive_audio_track_recovers_from_transient_live_ice_recv_errors() -> None:
    """Transient recv errors while ICE is live must not permanently kill input."""
    import asyncio

    from app.call.session import CallSession
    from app.call.tracks import PcmAudioFrame

    class TransientRecvError(Exception):
        pass

    class ResumingInboundTrack:
        kind = "audio"
        id = "inbound-resumes"

        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            if self.calls <= 3:
                raise TransientRecvError("temporary RTP read gap")
            await asyncio.sleep(0.005)
            return PcmAudioFrame(
                pcm=(b"\x00\x20" * 320),
                sample_rate=16000,
                channels=1,
            )

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

    class EndingCallSession(CallSession):
        async def handle_inbound_audio_frame(self, frame: Any) -> Any:
            result = await super().handle_inbound_audio_frame(frame)
            self.state = "ended"
            return result

    async def _run_test() -> tuple[int, int, str]:
        session = EndingCallSession(
            session_id="test-transient-recv-error",
            peer_connection=LivePeerConnection(),
            vad_adapter=None,
            stt_adapter=None,
        )
        track = ResumingInboundTrack()
        await webrtc_module._receive_audio_track(session, track)
        return track.calls, session.incoming_audio_frames, session.state

    recv_calls, incoming_frames, state = asyncio.run(_run_test())

    assert recv_calls >= 4
    assert incoming_frames == 1
    assert state == "ended"


def test_receive_audio_track_connection_state_reconnects_without_connection_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.call.session import CallSession
    from app.call.tracks import PcmAudioFrame

    class TransientDisconnectedError(Exception):
        pass

    class ReconnectingInboundTrack:
        kind = "audio"
        id = "inbound-connection-reconnects"

        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise TransientDisconnectedError("connection temporarily disconnected")
            return PcmAudioFrame(
                pcm=(b"\x00\x20" * 320),
                sample_rate=16000,
                channels=1,
            )

    class ReconnectingPeerConnection:
        connectionState = "disconnected"
        iceConnectionState = "new"
        close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    class EndingCallSession(CallSession):
        async def handle_inbound_audio_frame(self, frame: Any) -> Any:
            result = await super().handle_inbound_audio_frame(frame)
            self.state = "ended"
            return result

    async def fake_sleep(_delay: float) -> None:
        peer.connectionState = "connected"

    peer = ReconnectingPeerConnection()
    monkeypatch.setattr(webrtc_module.asyncio, "sleep", fake_sleep)

    async def _run_test() -> tuple[int, int, str, str | None, int]:
        session = EndingCallSession(
            session_id="test-connection-state-reconnects",
            peer_connection=peer,
            vad_adapter=None,
            stt_adapter=None,
        )
        track = ReconnectingInboundTrack()
        await webrtc_module._receive_audio_track(session, track, peer)
        return (
            track.calls,
            session.incoming_audio_frames,
            session.state,
            session.end_reason,
            peer.close_calls,
        )

    recv_calls, incoming_frames, state, end_reason, close_calls = asyncio.run(_run_test())

    assert recv_calls == 2
    assert incoming_frames == 1
    assert state == "ended"
    assert end_reason is None
    assert close_calls == 0


def test_receive_audio_track_closed_state_uses_bounded_connection_lifecycle() -> None:
    import asyncio

    from app.call.session import CallSession

    class ClosedTrackError(Exception):
        pass

    class ClosedInboundTrack:
        kind = "audio"
        id = "inbound-closed"

        async def recv(self) -> Any:
            raise ClosedTrackError("track closed")

    class ClosedPeerConnection:
        connectionState = "closed"
        iceConnectionState = "closed"
        close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def _run_test() -> tuple[str, str | None, int]:
        peer = ClosedPeerConnection()
        session = CallSession(
            session_id="test-closed-state-connection-failed",
            peer_connection=peer,
            vad_adapter=None,
            stt_adapter=None,
        )
        await webrtc_module._receive_audio_track(session, ClosedInboundTrack(), peer)
        assert session.state == "reconnecting"
        assert peer.close_calls == 0
        await session.resolve_deferred_connection_state()
        return session.state, session.end_reason, peer.close_calls

    state, end_reason, close_calls = asyncio.run(_run_test())

    assert state == "ended"
    assert end_reason == "connection_closed"
    assert close_calls == 1


def test_old_track_error_preserves_call_and_prompt_lease_while_replacement_is_pending() -> None:
    from app.call.session import CallSession

    class ClosedTrackError(Exception):
        pass

    class ClosedInboundTrack:
        kind = "audio"
        id = "old-inbound-closed"

        async def recv(self) -> Any:
            raise ClosedTrackError("old receiver closed")

    class Peer:
        def __init__(self, *, state: str) -> None:
            self.connectionState = state
            self.iceConnectionState = state
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def scenario() -> tuple[CallSession, Peer, Peer, list[str]]:
        active_peer = Peer(state="closed")
        replacement_peer = Peer(state="new")
        released_owners: list[str] = []
        session = CallSession(
            session_id="old-track-error-during-replacement",
            peer_connection=active_peer,
        )
        await session.install_or_release_tts_prompt_lease(
            lambda owner: released_owners.append(owner)
        )
        await session.mark_peer_connection_pending(
            replacement_peer,
            timeout_seconds=60.0,
        )

        await webrtc_module._receive_audio_track(
            session,
            ClosedInboundTrack(),
            active_peer,
        )
        return session, active_peer, replacement_peer, released_owners

    session, active_peer, replacement_peer, released_owners = asyncio.run(scenario())

    assert session.state == "reconnecting"
    assert session.ended_at is None
    assert session.is_peer_connection_pending(replacement_peer) is True
    assert active_peer.close_calls == 0
    assert replacement_peer.close_calls == 0
    assert released_owners == []


def test_receive_audio_track_exits_when_peer_connection_is_superseded() -> None:
    """Old receive loops must stop after a media reconnect installs a new peer."""
    import asyncio

    from app.call.session import CallSession
    from app.call.tracks import PcmAudioFrame

    class EndlessInboundTrack:
        kind = "audio"
        id = "old-inbound"

        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            await asyncio.sleep(0.005)
            return PcmAudioFrame(
                pcm=(b"\x00\x20" * 320),
                sample_rate=16000,
                channels=1,
            )

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

    async def _run_test() -> tuple[int, int, str]:
        old_peer = LivePeerConnection()
        new_peer = LivePeerConnection()
        session = CallSession(
            session_id="test-superseded-peer",
            peer_connection=old_peer,
            vad_adapter=None,
            stt_adapter=None,
        )
        track = EndlessInboundTrack()
        task = asyncio.create_task(webrtc_module._receive_audio_track(session, track, old_peer))
        await asyncio.sleep(0.02)
        session.peer_connection = new_peer
        await asyncio.wait_for(task, timeout=0.5)
        return track.calls, session.incoming_audio_frames, session.state

    recv_calls, incoming_frames, state = asyncio.run(_run_test())

    assert recv_calls >= 1
    assert incoming_frames >= 1
    assert state == "listening"


def test_data_channel_keepalive_starts_when_browser_channel_already_open() -> None:
    """Browser-created channels can arrive at aiortc already open.

    Regression for Android Chrome live calls: if the backend only starts
    keepalive from a future "open" event, this already-open path never sends
    pings during long listening/user-speaking spans.
    """
    import asyncio

    from app.call.session import CallSession

    class ScriptedDataChannel:
        label = webrtc_module.RAYME_EVENTS_CHANNEL

        def __init__(self) -> None:
            self.readyState = "open"
            self.sent: list[str] = []
            self.handlers: dict[str, Any] = {}

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        def send(self, data: str) -> None:
            self.sent.append(data)

        def close(self) -> None:
            self.readyState = "closed"
            close_handler = self.handlers.get("close")
            if close_handler is not None:
                close_handler()

    class ScriptedPeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

    async def _run_test() -> list[str]:
        peer = ScriptedPeerConnection()
        session = CallSession(session_id="test-already-open-datachannel", peer_connection=peer)
        webrtc_module._attach_peer_handlers(peer, session)
        channel = ScriptedDataChannel()

        peer.handlers["datachannel"](channel)
        await asyncio.sleep(0)
        channel.close()
        await asyncio.sleep(0)
        return channel.sent

    sent = asyncio.run(_run_test())

    assert sent[:1] == ['{"type":"ping"}']
