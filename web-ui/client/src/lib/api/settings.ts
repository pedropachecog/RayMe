import { apiFetch } from './client';
import type { EndpointTestResult, SettingsPayload, SettingsUpdatePayload } from './types';

export function getSettings(): Promise<SettingsPayload> {
  return apiFetch<SettingsPayload>('/settings', { method: 'GET' });
}

export function updateSettings(payload: SettingsUpdatePayload): Promise<SettingsPayload> {
  return apiFetch<SettingsPayload>('/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export function testWebSettings(): Promise<EndpointTestResult> {
  return apiFetch<EndpointTestResult>('/settings/test/web', { method: 'POST' });
}

export function testAiBackendSettings(): Promise<EndpointTestResult> {
  return apiFetch<EndpointTestResult>('/settings/test/ai-backend', { method: 'POST' });
}

export function testLlmSettings(): Promise<EndpointTestResult> {
  return apiFetch<EndpointTestResult>('/settings/test/llm', { method: 'POST' });
}
