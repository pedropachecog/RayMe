import { apiFetch } from './client';
import type {
  CallOfferResponse,
  CallStartRequest,
  CallStartResponse,
  CallTurnRequest
} from './types';

export function startCall(payload: CallStartRequest): Promise<CallStartResponse> {
  return apiFetch<CallStartResponse>('/calls/start', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function sendCallOffer(
  callId: string,
  offer: RTCSessionDescriptionInit,
  sessionId?: string | null
): Promise<CallOfferResponse> {
  return apiFetch<CallOfferResponse>(`/calls/${encodeURIComponent(callId)}/offer`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId ?? undefined,
      offer: {
        type: offer.type,
        sdp: offer.sdp
      }
    })
  });
}

export function submitCallTurn(callId: string, payload: CallTurnRequest): Promise<Response> {
  return fetch(`/api/calls/${encodeURIComponent(callId)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function setCallMuted(
  callId: string,
  sessionId: string,
  muted: boolean
): Promise<{ call_id: string; session_id: string; muted: boolean }> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/mute`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, muted })
  });
}

export function interruptCall(
  callId: string,
  sessionId: string
): Promise<{ call_id: string; session_id: string; interrupted: boolean }> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/interrupt`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, reason: 'interrupt' })
  });
}

export function endCall(
  callId: string,
  sessionId: string,
  reason = 'hangup'
): Promise<{ call_id: string; session_id: string; reason: string }> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/end`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, reason })
  });
}
