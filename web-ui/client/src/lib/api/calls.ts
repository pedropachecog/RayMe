import { apiFetch, toApiPath } from './client';
import type {
  CallErrorCode,
  CallEvent,
  CallOfferResponse,
  CallStartRequest,
  CallStartResponse,
  CallTurnRequest,
  CallTurnStreamEvent,
  GenerationFailure,
  GenerationFailureCode
} from './types';
import { decodeGenerationFailure, isGenerationFailureCode } from './types';

export function generationFailureFromCallTerminal(
  event: Extract<CallTurnStreamEvent, { type: 'error' }>
): GenerationFailure;
export function generationFailureFromCallTerminal(
  event: CallTurnStreamEvent
): GenerationFailure | null;
export function generationFailureFromCallTerminal(
  event: CallTurnStreamEvent
): GenerationFailure | null {
  if (event.type !== 'error') {
    return null;
  }

  return decodeGenerationFailure({ code: event.code });
}

export interface CallReconnectAudioBackfillRequest {
  session_id: string;
  pcm_b64: string;
  sample_rate: number;
  channels: number;
  backfill_id?: string;
  audio_input_epoch?: number;
  reason?: string;
  attempt?: number;
  duration_ms?: number;
  batch_index?: number;
  final?: boolean;
}

export class CallApiError extends Error {
  code?: CallErrorCode | GenerationFailureCode;
  status: number;
  generationFailure?: GenerationFailure;

  constructor(
    message: string,
    status: number,
    code?: CallErrorCode | GenerationFailureCode,
    generationFailure?: GenerationFailure
  ) {
    super(message);
    this.name = 'CallApiError';
    this.status = status;
    this.code = code;
    this.generationFailure = generationFailure;
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
    const code = typeof detail.code === 'string' ? detail.code : undefined;
    const generationFailure = isGenerationFailureCode(code)
      ? decodeGenerationFailure(detail)
      : undefined;
    throw new CallApiError(
      fallbackMessage,
      response.status,
      (code as CallErrorCode | GenerationFailureCode | undefined),
      generationFailure
    );
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
  sessionId?: string | null,
  options: { signal?: AbortSignal } = {}
): Promise<CallOfferResponse> {
  const response = await fetch(toApiPath(`/calls/${encodeURIComponent(callId)}/offer`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
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

export interface CallPeerPromotionResponse {
  call_id: string;
  session_id: string;
  generation: number;
  status: 'committed' | 'rejected' | 'failed' | 'in_progress';
}

export async function promoteCallPeer(
  callId: string,
  sessionId: string,
  generation: number,
  action: 'commit' | 'reject',
  options: { signal?: AbortSignal } = {}
): Promise<CallPeerPromotionResponse> {
  const response = await fetch(
    toApiPath(`/calls/${encodeURIComponent(callId)}/peer-promotion`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: options.signal,
      body: JSON.stringify({ session_id: sessionId, generation, action })
    }
  );
  return parseCallApiResponse(response, 'RayMe could not reconcile replacement call media.');
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
  payload: CallReconnectAudioBackfillRequest,
  options: { signal?: AbortSignal } = {}
): Promise<{
  call_id: string;
  session_id: string;
  status: string;
  frames?: number;
  duration_ms?: number;
  event?: CallEvent;
}> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/reconnect-audio`, {
    method: 'POST',
    signal: options.signal,
    body: JSON.stringify(payload)
  });
}

export function recoverCallEvents(
  callId: string,
  sessionId: string,
  options: { signal?: AbortSignal } = {}
): Promise<{
  call_id: string;
  session_id: string;
  events: CallEvent[];
}> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/events/recover`, {
    method: 'POST',
    signal: options.signal,
    body: JSON.stringify({ session_id: sessionId })
  });
}

export function setCallMuted(
  callId: string,
  sessionId: string,
  muted: boolean,
  options: { signal?: AbortSignal } = {}
): Promise<{
  call_id: string;
  session_id: string;
  muted: boolean;
  audio_input_epoch: number;
  mute_revision: number;
}> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/mute`, {
    method: 'POST',
    signal: options.signal,
    body: JSON.stringify({ session_id: sessionId, muted })
  });
}

export function interruptCall(
  callId: string,
  sessionId: string,
  options: { signal?: AbortSignal } = {}
): Promise<{
  call_id: string;
  session_id: string;
  interrupted: boolean;
  cancelled_turn_id?: string | null;
  receiver_drain_ms?: number | null;
}> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/interrupt`, {
    method: 'POST',
    signal: options.signal,
    body: JSON.stringify({ session_id: sessionId, reason: 'interrupt' })
  });
}

export function endCall(
  callId: string,
  sessionId: string,
  reason = 'hangup',
  options: { signal?: AbortSignal } = {}
): Promise<{ call_id: string; session_id: string; reason: string }> {
  return apiFetch(`/calls/${encodeURIComponent(callId)}/end`, {
    method: 'POST',
    signal: options.signal,
    body: JSON.stringify({ session_id: sessionId, reason })
  });
}
