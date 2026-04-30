import { apiFetch, toApiPath } from './client';
import type {
  CallErrorCode,
  CallOfferResponse,
  CallStartRequest,
  CallStartResponse,
  CallTurnRequest
} from './types';

export interface CallReconnectAudioBackfillRequest {
  session_id: string;
  pcm_b64: string;
  sample_rate: number;
  channels: number;
  backfill_id?: string;
  reason?: string;
  attempt?: number;
  duration_ms?: number;
  batch_index?: number;
  final?: boolean;
}

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
    return parseCallApiResponse(
      await postCallStart('/calls', payload),
      'RayMe could not start this call.'
    );
  }

  return parseCallApiResponse(started, 'RayMe could not start this call.');
}

async function postCallStart(path: string, payload: CallStartRequest): Promise<Response> {
  return fetch(toApiPath(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

async function parseCallApiResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  const payload = await readJsonPayload(response);

  if (!response.ok) {
    const detail = payload.detail && typeof payload.detail === 'object' ? payload.detail : payload;
    const code = typeof detail.code === 'string' ? (detail.code as CallErrorCode) : undefined;
    const message = typeof detail.message === 'string' ? detail.message : fallbackMessage;
    throw new CallApiError(message, response.status, code);
  }

  return payload as T;
}

async function readJsonPayload(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload = await response.json();
    return payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export async function sendCallOffer(
  callId: string,
  offer: RTCSessionDescriptionInit,
  sessionId?: string | null
): Promise<CallOfferResponse> {
  const response = await fetch(toApiPath(`/calls/${encodeURIComponent(callId)}/offer`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId ?? undefined,
      offer: {
        type: offer.type,
        sdp: offer.sdp
      }
    })
  });

  return parseCallApiResponse(response, 'RayMe could not connect this call.');
}

export function submitCallTurn(
  callId: string,
  payload: CallTurnRequest,
  options: { signal?: AbortSignal } = {}
): Promise<Response> {
  return fetch(`/api/calls/${encodeURIComponent(callId)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
    body: JSON.stringify(payload)
  });
}

export function backfillCallReconnectAudio(
  callId: string,
  payload: CallReconnectAudioBackfillRequest
): Promise<{ call_id: string; session_id: string; status: string; frames?: number; duration_ms?: number }> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/reconnect-audio`, {
    method: 'POST',
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
