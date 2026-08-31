import { apiFetch } from './client';
import type { PromptPreviewRequest, PromptPreviewResponse } from './types';

export interface PromptPreviewOptions {
  signal?: AbortSignal;
}

export function previewPrompt(
  payload: PromptPreviewRequest,
  options: PromptPreviewOptions = {}
): Promise<PromptPreviewResponse> {
  return apiFetch<PromptPreviewResponse>('/prompt-preview', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal: options.signal
  });
}
