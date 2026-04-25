import { apiFetch, toApiPath } from './client';
import type {
  CallErrorCode,
  CallOfferResponse,
  CallStartRequest,
  CallStartResponse,
  CallTurnRequest
} from './types';

export class CallApiError extends Error {
  code?: CallErrorCode;
  status: number;

  constructor(message: string, status: number, code?: CallErrorCode) {
    super(message);
    this.name = 'CallApiError';
    this.status = status;
    this.code = code;
  }
}

export async function startCall(payload: CallStartRequest): Promise<CallStartResponse> {
  const started = await postCallStart('/calls/start', payload);
  if (started.status === 404) {
    return parseCallStartResponse(await postCallStart('/calls', payload));
  }

  return parseCallStartResponse(started);
}

async function postCallStart(path: string, payload: CallStartRequest): Promise<Response> {
  return fetch(toApiPath(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

async function parseCallStartResponse(response: Response): Promise<CallStartResponse> {
  const payload = await readJsonPayload(response);

  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === 'object' ? payload.detail : payload;
    const code = typeof detail.code === 'string' ? (detail.code as CallErrorCode) : undefined;
    const message = typeof detail.message === 'string' ? detail.message : 'RayMe could not start this call.';
    throw new CallApiError(message, response.status, code);
  }

  return payload as CallStartResponse;
}

async function readJsonPayload(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload = await response.json();
    return payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  } catch {
    return {};
  }
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
