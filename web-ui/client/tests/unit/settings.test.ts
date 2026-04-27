import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getSettings,
  testAiBackendSettings,
  testLlmSettings,
  testWebSettings,
  updateSettings
} from '../../src/lib/api/settings';
import settingsApiSource from '../../src/lib/api/settings.ts?raw';
import typesSource from '../../src/lib/api/types.ts?raw';
import endpointPanelSource from '../../src/lib/components/EndpointSettingsPanel.svelte?raw';
import audioPanelSource from '../../src/lib/components/settings/AudioSettingsPanel.svelte?raw';
import vadPanelSource from '../../src/lib/components/settings/VadSettingsPanel.svelte?raw';
import settingsSource from '../../src/routes/settings/+page.svelte?raw';

const publicSettings = {
  web_url: 'https://192.168.1.199:8443',
  ai_backend_url: 'https://192.168.1.199:9443',
  llm_base_url: 'https://api.openai.com/v1',
  llm_model: 'gpt-4o-mini',
  llm_disable_thinking: true,
  llm_api_key_configured: true,
  save_ai_audio: true,
  save_mic_audio: false,
  vad_threshold: 0.5,
  vad_end_silence_ms: 700,
  stt_model: 'distil-large-v3',
  tts_default_engine: 'f5',
  ai_backend_status: {
    endpoint_status: 'Connected',
    stt_model: 'distil-large-v3',
    vad_ready: true,
    resident_tts_engine: 'f5',
    available_engines: ['f5', 'xtts_v2', 'qwen3_0_6b'],
    loading_engine: null,
    vram_used_mb: 2104,
    vram_headroom_mb: 9896
  }
};

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init
  });
}

function installFetch(payloadByRoute: Record<string, unknown>) {
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init: RequestInit = {}) => {
    const routeKey = `${String(url)}::${init.method ?? 'GET'}`;
    const payload = payloadByRoute[routeKey] ?? payloadByRoute[String(url)];

    if (payload === undefined) {
      throw new Error(`Unhandled request: ${routeKey}`);
    }

    return payload instanceof Response ? payload : jsonResponse(payload);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof installFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url: url as string, init: init as RequestInit };
}

describe('Settings route', () => {
  it('renders Phase 2 endpoint, audio retention, VAD, and model residency controls', () => {
    const requiredCopy = [
      'Web UI status',
      'AI backend URL',
      'LLM URL',
      'API key',
      'Model',
      'LLM status',
      'HTTPS secure-context status',
      'Media-device availability status',
      'Save AI audio',
      'Save mic audio',
      'Off by default; future calls will not store your microphone audio unless enabled.',
      'VAD threshold',
      'End-of-utterance silence',
      'Coming in Call Feel',
      'STT model',
      'VAD ready',
      'Resident TTS engine',
      'Available engines',
      'Loading engine',
      'VRAM headroom',
      'Test Connection',
      'Connected',
      'Unreachable',
      'Unauthorized',
      'Not configured'
    ];

    const settingsSources = `${settingsSource}\n${endpointPanelSource}\n${audioPanelSource}\n${vadPanelSource}`;
    for (const copy of requiredCopy) {
      expect(settingsSources).toContain(copy);
    }

    for (const forbidden of [
      'Billing',
      'Subscription',
      'Wake word',
      'save-audio',
      'clear all data',
      'PWA',
      'Call'
    ]) {
      expect(settingsSource).not.toContain(forbidden);
      expect(endpointPanelSource).not.toContain(forbidden);
    }
  });

  it('declares Phase 2 Settings payload fields and sends them through the API wrapper', async () => {
    for (const field of [
      'save_ai_audio',
      'save_mic_audio',
      'vad_threshold',
      'vad_end_silence_ms',
      'stt_model',
      'tts_default_engine',
      'ai_backend_status'
    ]) {
      expect(typesSource).toContain(field);
    }

    expect(settingsApiSource).toContain('SettingsUpdatePayload');
    expect(settingsApiSource).toContain("apiFetch<SettingsPayload>('/settings'");

    const fetchMock = installFetch({
      '/api/settings::PATCH': publicSettings
    });

    await updateSettings({
      save_ai_audio: true,
      save_mic_audio: false,
      vad_threshold: 0.6,
      vad_end_silence_ms: 900,
      stt_model: 'distil-large-v3',
      tts_default_engine: 'f5'
    });

    const request = lastRequest(fetchMock);
    expect(JSON.parse(request.init.body as string)).toMatchObject({
      save_ai_audio: true,
      save_mic_audio: false,
      vad_threshold: 0.6,
      vad_end_silence_ms: 900,
      stt_model: 'distil-large-v3',
      tts_default_engine: 'f5'
    });
  });

  it('does not expose raw API keys, tracebacks, or backend exception copy in status UI', () => {
    for (const forbidden of [
      'Traceback',
      'stack trace',
      'Exception:',
      'ValueError',
      'RuntimeError',
      'sk-',
      'api key value',
      'raw API key'
    ]) {
      expect(settingsSource).not.toContain(forbidden);
      expect(endpointPanelSource).not.toContain(forbidden);
    }
  });

  it('loads, saves, and tests endpoint settings through real API wrappers', async () => {
    const fetchMock = installFetch({
      '/api/settings::GET': publicSettings,
      '/api/settings::PATCH': publicSettings,
      '/api/settings/test/web::POST': { status: 'Connected' },
      '/api/settings/test/ai-backend::POST': { status: 'Unreachable' },
      '/api/settings/test/llm::POST': { status: 'Unauthorized' }
    });

    const loadedSettings = await getSettings();
    expect(loadedSettings).toEqual(publicSettings);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/settings',
      init: { method: 'GET' }
    });

    await updateSettings({
      web_url: publicSettings.web_url,
      ai_backend_url: publicSettings.ai_backend_url,
      llm_base_url: publicSettings.llm_base_url,
      llm_model: publicSettings.llm_model,
      llm_api_key: 'secret-key'
    });
    let request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('PATCH /api/settings');
    expect(JSON.parse(request.init.body as string)).toMatchObject({
      llm_api_key: 'secret-key',
      llm_model: 'gpt-4o-mini'
    });

    await testWebSettings();
    request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('POST /api/settings/test/web');

    await testAiBackendSettings();
    request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('POST /api/settings/test/ai-backend');

    const llmResult = await testLlmSettings();
    request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('POST /api/settings/test/llm');
    expect(llmResult.status).toBe('Unauthorized');
    expect(settingsSource).toContain('await testLlmSettings()');
  });

  it('masks the API key by default and keeps key values out of status text', () => {
    expect(endpointPanelSource).toContain("type={apiKeyVisible ? 'text' : 'password'}");
    expect(endpointPanelSource).toContain("aria-label={apiKeyVisible ? 'Mask API key' : 'Reveal API key'}");
    expect(endpointPanelSource).toContain('Stored API key is configured.');
    expect(settingsSource).toContain("llmApiKey = ''");
    expect(settingsSource).toContain('apiKeyPlaceholder');

    const statusPill = endpointPanelSource
      .split('\n')
      .find((line) => line.includes('data-testid={`${idPrefix}-status`}'));
    expect(statusPill).toContain('{status}');
    expect(statusPill).not.toContain('apiKeyValue');
    expect(statusPill).not.toContain('llmApiKey');
  });
});
