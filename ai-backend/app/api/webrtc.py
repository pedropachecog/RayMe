from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/webrtc", tags=["webrtc"])

_SKELETON_STATUS = {
    "status": "skeleton",
    "phase": "02",
    "live_call_ready": False,
    "media_transport_ready": False,
    "message": "Signaling skeleton only; Phase 3 owns live call media.",
}

_CALL_NOT_READY_DETAIL = {
    "code": "call_not_ready",
    "message": "Live call media is Phase 3 scope.",
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
