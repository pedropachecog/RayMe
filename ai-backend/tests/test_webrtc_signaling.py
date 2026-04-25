from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


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
    assert payload["live_call_ready"] is False, "live_call_ready false"
    assert payload["media_transport_ready"] is False, "media_transport_ready false"


def test_webrtc_offer_rejects_live_call_media_until_phase_three() -> None:
    client = TestClient(create_app())

    response = client.post("/webrtc/offer", json={"sdp": "ignored", "type": "offer"})

    assert response.status_code == 501
    assert response.json() == {
        "detail": {
            "code": "call_not_ready",
            "message": "Live call media is Phase 3 scope.",
        }
    }


def test_openapi_does_not_expose_call_captions_or_barge_in_routes() -> None:
    client = TestClient(create_app())

    paths = set(client.get("/openapi.json").json()["paths"])

    assert "/webrtc/status" in paths
    assert "/webrtc/offer" in paths
    assert "/call" not in paths
    assert "/captions" not in paths
    assert "/barge-in" not in paths
