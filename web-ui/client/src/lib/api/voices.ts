import { apiFetch } from './client';
import type {
  ListResponse,
  VoiceAsset,
  VoiceDeleteResult,
  VoiceDetail,
  VoicePreviewPayload,
  VoiceSavePayload,
  VoiceSummary,
  VoiceSynthesisResult,
  VoiceTestPlayPayload
} from './types';

const ABSOLUTE_HTTP_URL = /^https?:\/\//i;

export function uploadVoiceAsset(file: File): Promise<VoiceAsset> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<VoiceAsset>('/voices/assets', {
    method: 'POST',
    body: formData
  });
}

export function transcribeVoiceAsset(assetId: string): Promise<VoiceAsset & {
  reference_transcript?: string | null;
  reference_transcript_editable?: boolean;
  language?: string | null;
  confidence?: number | null;
}> {
  return apiFetch(`/voices/assets/${encodeRouteId(assetId)}/transcribe`, { method: 'POST' });
}

export function previewVoice(payload: VoicePreviewPayload): Promise<VoiceSynthesisResult> {
  return apiFetch<VoiceSynthesisResult>('/voices/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function saveVoice(payload: VoiceSavePayload): Promise<VoiceDetail> {
  return apiFetch<VoiceDetail>('/voices', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function listVoices(): Promise<VoiceSummary[]> {
  const response = await apiFetch<ListResponse<VoiceSummary> | VoiceSummary[]>('/voices', {
    method: 'GET'
  });
  return Array.isArray(response) ? response : response.items;
}

export async function getVoice(voiceId: string): Promise<VoiceDetail> {
  return apiFetch<VoiceDetail>(`/voices/${encodeRouteId(voiceId)}`, { method: 'GET' });
}

export function renameVoice(voiceId: string, name: string): Promise<VoiceDetail> {
  return apiFetch<VoiceDetail>(`/voices/${encodeRouteId(voiceId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ name })
  });
}

export function deleteVoice(voiceId: string, force = false): Promise<VoiceDeleteResult> {
  const query = force ? '?force=true' : '';
  return apiFetch<VoiceDeleteResult>(`/voices/${encodeRouteId(voiceId)}${query}`, {
    method: 'DELETE'
  });
}

export function testPlayVoice(
  voiceId: string,
  payload: VoiceTestPlayPayload
): Promise<VoiceSynthesisResult> {
  return apiFetch<VoiceSynthesisResult>(`/voices/${encodeRouteId(voiceId)}/test-play`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

function encodeRouteId(id: string): string {
  if (ABSOLUTE_HTTP_URL.test(id)) {
    throw new Error('Client API requests must use RayMe backend routes, not absolute provider URLs.');
  }
  return encodeURIComponent(id);
}
