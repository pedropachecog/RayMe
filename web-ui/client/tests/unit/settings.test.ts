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
import enginePickerSource from '../../src/lib/components/voice/TtsEnginePicker.svelte?raw';
import voiceAssignmentSource from '../../src/lib/components/voice/VoiceAssignmentSelect.svelte?raw';
import audioPanelSource from '../../src/lib/components/settings/AudioSettingsPanel.svelte?raw';
import promptPanelSource from '../../src/lib/components/settings/PromptGenerationSettingsPanel.svelte?raw';
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
  prompt_generation: {
    schema_version: 1,
    prompt_contract_version: 'rayme-prompt-contract-v1',
    mode: 'roleplay',
    roleplay: {
      main: "Write only {{char}}'s next reply.",
      auxiliary: 'Private fictional guidance <img src=x onerror=alert(1)>',
      post_history: 'Continue immediately in character.'
    },
    assistant: {
      main: 'You are a helpful assistant.',
      auxiliary: 'Be useful and concise.',
      post_history: 'Respond with no unnecessary preamble.'
    },
    custom: { main: '', auxiliary: '', post_history: '' },
    model_profile: 'auto',
    context_limit: 16384,
    max_tokens: 512,
    temperature: 0.8,
    top_p: 0.95,
    min_p: 0.05,
    top_k: 40,
    repetition_penalty: 1.05,
    presence_penalty: 0,
    frequency_penalty: 0
  },
  ai_backend_status: {
    endpoint_status: 'Connected',
    stt_model: 'distil-large-v3',
    vad_ready: true,
    resident_tts_engine: 'f5',
    available_engines: [
      'f5',
      'xtts_v2',
      {
        id: 'qwen3_1_7b',
        label: 'Qwen3-TTS 1.7B-Base',
        available: true,
        state: 'loading'
      }
    ],
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
    expect(settingsApiSource).toContain('Readonly<SettingsUpdatePayload>');
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

  it('types and renders canonical Qwen model readiness without exposing prompt internals', () => {
    expect(typesSource).toContain("| 'qwen3_1_7b'");
    expect(typesSource).not.toContain("| 'qwen3_0_6b'");
    for (const readinessType of [
      'TtsModelReadinessState',
      'TtsPromptReadinessState',
      'TtsModelReadiness',
      'TtsPromptReadiness',
      'updated_at',
      'error_code'
    ]) {
      expect(typesSource).toContain(readinessType);
    }

    for (const copy of [
      'Qwen3-TTS 1.7B-Base',
      'Loading Qwen3-TTS 1.7B…',
      'Qwen3-TTS 1.7B loaded',
      'Qwen3-TTS 1.7B unavailable'
    ]) {
      expect(`${endpointPanelSource}\n${enginePickerSource}\n${voiceAssignmentSource}`).toContain(copy);
    }

    expect(endpointPanelSource).toContain('role="status"');
    expect(endpointPanelSource).toContain('role="alert"');
    expect(endpointPanelSource).toContain('resident_tts_engine');
    expect(endpointPanelSource).toContain('loading_engine');
    expect(endpointPanelSource).toContain('available_engines');
    expect(endpointPanelSource).not.toMatch(/voice_key|cache key|model path|provider/i);
    expect(enginePickerSource).not.toContain('qwen3_0_6b');
    expect(voiceAssignmentSource).not.toContain('qwen3_0_6b');
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

  it('declares the complete typed prompt profile and sends nested numbers without coercion', async () => {
    for (const contract of [
      'PromptMode',
      'PromptSet',
      'PromptGenerationSettings',
      'ModelProfile',
      'prompt_generation',
      'context_limit',
      'max_tokens',
      'repetition_penalty',
      'frequency_penalty'
    ]) {
      expect(typesSource).toContain(contract);
    }

    const fetchMock = installFetch({ '/api/settings::PATCH': publicSettings });
    await updateSettings({
      prompt_generation: {
        ...publicSettings.prompt_generation,
        mode: 'custom',
        custom: { main: '<script>alert(1)</script>', auxiliary: '', post_history: '' },
        context_limit: 32768,
        temperature: 1.25,
        top_k: 77
      }
    });

    const request = lastRequest(fetchMock);
    const payload = JSON.parse(request.init.body as string);
    expect(payload).not.toHaveProperty('roleplay');
    expect(payload).not.toHaveProperty('seed');
    expect(payload.prompt_generation).toMatchObject({
      mode: 'custom',
      context_limit: 32768,
      temperature: 1.25,
      top_k: 77,
      custom: { main: '<script>alert(1)</script>', auxiliary: '', post_history: '' }
    });
    expect(typeof payload.prompt_generation.context_limit).toBe('number');
    expect(typeof payload.prompt_generation.temperature).toBe('number');
    expect(typeof payload.prompt_generation.top_k).toBe('number');

    await updateSettings({ prompt_generation: { temperature: 1.1 } });
    const partialRequest = lastRequest(fetchMock);
    expect(JSON.parse(partialRequest.init.body as string)).toEqual({
      prompt_generation: { temperature: 1.1 }
    });
  });

  it('renders the exact Roleplay-first mode, prompt, profile, seed, and save copy', () => {
    for (const copy of [
      'LLM behavior',
      'Prompt & Generation',
      'Choose how RayMe composes character requests and tune the bounded generation settings used by text and calls.',
      'Roleplay',
      'Default',
      "Write the selected character's next in-world reply without AI or policy commentary.",
      'Assistant',
      'Use a conventional helpful-assistant prompt.',
      'Custom',
      'Use your own Main, Auxiliary, and late post-history prompts.',
      'Main prompt',
      'Auxiliary prompt',
      'Post-history instruction',
      'Built-in preset',
      'Modified',
      'Reset Roleplay Prompts',
      'Reset Assistant Prompts',
      'Model profile',
      'Auto (recommended)',
      'Qwen / llama-server',
      'Generic OpenAI-compatible',
      'Disable Qwen thinking',
      'Used only when Auto resolves to Qwen or Qwen / llama-server is selected.',
      'Seed: Fresh random value generated for every attempt.',
      'Settings saved.',
      'RayMe could not save settings. Your changes are still here. Try again.'
    ]) {
      expect(`${settingsSource}\n${promptPanelSource}`).toContain(copy);
    }

    expect(settingsSource).toContain('<h1 id="settings-title">Settings</h1>');
    expect(settingsSource).toContain('PromptGenerationSettingsPanel');
    expect(settingsSource).not.toContain('Endpoint settings saved.');
    expect(settingsSource).not.toContain('RayMe could not save endpoint settings.');
    expect(promptPanelSource).not.toMatch(/\bseed\s*=|type="[^\"]*seed|name="seed"/i);
    expect(promptPanelSource).not.toContain('{@html}');
    expect(promptPanelSource).not.toContain('innerHTML');
  });

  it('uses exact numeric defaults, bounds, steps, helper purpose, and validation copy', () => {
    const controls = [
      ['Context limit', '16384', '2048', '131072', '1024', 'Estimated total context capacity configured for the running server.', 'Context limit must be between 2,048 and 131,072, in steps of 1,024.'],
      ['Maximum output tokens', '512', '64', '4096', '64', 'Reserved before prompt/history budgeting.', 'Maximum output tokens must be between 64 and 4,096, in steps of 64.'],
      ['Temperature', '0.8', '0', '2', '0.05', 'Higher values increase variation.', 'Temperature must be between 0.00 and 2.00, in steps of 0.05.'],
      ['Top-p', '0.95', '0.01', '1', '0.01', 'Nucleus sampling probability mass.', 'Top-p must be between 0.01 and 1.00, in steps of 0.01.'],
      ['Min-p', '0.05', '0', '1', '0.01', 'Qwen/llama-server minimum probability filter.', 'Min-p must be between 0.00 and 1.00, in steps of 0.01.'],
      ['Top-k', '40', '0', '200', '1', 'Candidate-token limit; 0 disables it where supported.', 'Top-k must be between 0 and 200, in steps of 1.'],
      ['Repetition penalty', '1.05', '0.5', '2', '0.01', 'Discourages repeated phrasing.', 'Repetition penalty must be between 0.50 and 2.00, in steps of 0.01.'],
      ['Presence penalty', '0', '-2', '2', '0.1', 'Adjusts reuse based on whether a token appeared.', 'Presence penalty must be between -2.00 and 2.00, in steps of 0.10.'],
      ['Frequency penalty', '0', '-2', '2', '0.1', 'Adjusts reuse based on how often a token appeared.', 'Frequency penalty must be between -2.00 and 2.00, in steps of 0.10.']
    ];

    for (const [label, defaultValue, min, max, step, helper, error] of controls) {
      for (const copy of [label, defaultValue, min, max, step, helper, error]) {
        expect(promptPanelSource).toContain(copy);
      }
    }
    expect(promptPanelSource).toContain('type="number"');
    expect(promptPanelSource).toContain('aria-invalid');
    expect(promptPanelSource).toContain('aria-describedby');
  });

  it('keeps field-local required errors, independent drafts, exact reset scope, and accessible focus', () => {
    for (const copy of [
      'Add a Main prompt before saving Roleplay mode.',
      'Add an Auxiliary prompt before saving Roleplay mode.',
      'Add a Post-history instruction before saving Roleplay mode.',
      'Add a Main prompt before saving Assistant mode.',
      'Add an Auxiliary prompt before saving Assistant mode.',
      'Add a Post-history instruction before saving Assistant mode.',
      'Add a Main prompt before saving Custom mode.',
      'Reset Roleplay prompts?',
      "This replaces your Roleplay Main, Auxiliary, and post-history text with RayMe's built-in defaults. Generation settings will not change.",
      'Reset Assistant prompts?',
      "This replaces your Assistant Main, Auxiliary, and post-history text with RayMe's built-in defaults. Generation settings will not change.",
      'Reset Prompts',
      'Keep Changes',
      'Roleplay prompts reset to built-in defaults.',
      'Assistant prompts reset to built-in defaults.'
    ]) {
      expect(promptPanelSource).toContain(copy);
    }

    expect(promptPanelSource).toContain('type="radio"');
    expect(promptPanelSource).toContain('<fieldset');
    expect(promptPanelSource).toContain('<legend');
    expect(promptPanelSource).toContain('<ConfirmDialog');
    expect(promptPanelSource).toContain('.focus()');
    expect(promptPanelSource).toContain('role="status"');
    expect(promptPanelSource).toMatch(/roleplay.*assistant.*custom|custom.*assistant.*roleplay/s);
  });

  it('preserves the existing skeleton and one page-level save transaction', () => {
    expect(settingsSource).toContain("loadState === 'loading'");
    expect(settingsSource).toContain('aria-label="Loading settings"');
    expect(settingsSource).toContain('prompt_generation: promptGeneration');
    expect(settingsSource.match(/<span>Save Settings<\/span>/g)).toHaveLength(1);
    expect(settingsSource).toContain("saveState === 'saving'");
    expect(settingsSource).toContain('!promptGenerationValid');
    expect(settingsSource).not.toContain('Reset all');
  });
});
