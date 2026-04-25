import { expect, test, type Page } from '@playwright/test';

import {
  expectRayMeApiRequest,
  fulfillJson,
  installBrowserErrorGuard
} from './helpers/acceptance';
import { PHASE1_LOCAL_LLM_MODEL, PHASE1_LOCAL_LLM_URL } from './helpers/fixtures';

type SettingsState = {
  web_url: string;
  ai_backend_url: string;
  llm_base_url: string;
  llm_model: string;
  llm_api_key_configured: boolean;
  save_ai_audio: boolean;
  save_mic_audio: boolean;
  vad_threshold: number;
  vad_end_silence_ms: number;
  stt_model: string;
  tts_default_engine: string;
  ai_backend_status: {
    endpoint_status: string;
    stt_model: string;
    vad_ready: boolean;
    resident_tts_engine: string | null;
    available_engines: string[];
    loading_engine: string | null;
    vram_used_mb: number | null;
    vram_headroom_mb: number | null;
  };
};

type SettingsPayload = Partial<
  Omit<SettingsState, 'llm_api_key_configured' | 'ai_backend_status'> & {
    llm_api_key: string | null;
  }
>;

type SettingsEvent =
  | {
      method: 'PATCH';
      payload: SettingsPayload;
    }
  | {
      method: 'POST';
      path: string;
    };

const staleSettings: SettingsState = {
  web_url: 'https://127.0.0.1:8443',
  ai_backend_url: 'https://127.0.0.1:9443',
  llm_base_url: 'https://api.openai.com/v1',
  llm_model: 'gpt-stale-default',
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

test('Settings Test Connection saves current form values before probing endpoints', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const events: SettingsEvent[] = [];
  const requestUrls: string[] = [];
  let currentSettings = { ...staleSettings };

  page.on('request', (request) => {
    requestUrls.push(request.url());
    expectRayMeApiRequest(request);
  });

  await page.route('**/api/settings', async (route) => {
    const request = route.request();

    if (request.method() === 'GET') {
      await fulfillJson(route, currentSettings);
      return;
    }

    expect(request.method()).toBe('PATCH');
    const payload = request.postDataJSON() as SettingsPayload;
    events.push({ method: 'PATCH', payload });
    currentSettings = {
      web_url: payload.web_url ?? currentSettings.web_url,
      ai_backend_url: payload.ai_backend_url ?? currentSettings.ai_backend_url,
      llm_base_url: payload.llm_base_url ?? currentSettings.llm_base_url,
      llm_model: payload.llm_model ?? currentSettings.llm_model,
      save_ai_audio: payload.save_ai_audio ?? currentSettings.save_ai_audio,
      save_mic_audio: payload.save_mic_audio ?? currentSettings.save_mic_audio,
      vad_threshold: payload.vad_threshold ?? currentSettings.vad_threshold,
      vad_end_silence_ms: payload.vad_end_silence_ms ?? currentSettings.vad_end_silence_ms,
      stt_model: payload.stt_model ?? currentSettings.stt_model,
      tts_default_engine: payload.tts_default_engine ?? currentSettings.tts_default_engine,
      ai_backend_status: currentSettings.ai_backend_status,
      llm_api_key_configured:
        typeof payload.llm_api_key === 'string' && payload.llm_api_key.trim().length > 0
    };

    await fulfillJson(route, currentSettings);
  });

  await routeSettingsTest(page, '/api/settings/test/web', events);
  await routeSettingsTest(page, '/api/settings/test/ai-backend', events);
  await routeSettingsTest(page, '/api/settings/test/llm', events);

  await page.goto('/settings');

  const webSection = page.locator('section[aria-labelledby="web-ui-title"]');
  const aiBackendSection = page.locator('section[aria-labelledby="ai-backend-title"]');
  const llmSection = page.locator('section[aria-labelledby="llm-title"]');

  await webSection.getByLabel('Web UI URL').fill('https://192.168.1.199:8443');
  await aiBackendSection.getByLabel('AI backend URL').fill('https://192.168.1.199:9443');
  await llmSection.getByLabel('LLM URL').fill(PHASE1_LOCAL_LLM_URL);
  await llmSection.getByLabel('Model').fill(PHASE1_LOCAL_LLM_MODEL);
  await llmSection.getByRole('textbox', { name: /API key/ }).fill('');

  await webSection.getByRole('button', { name: 'Test Connection' }).click();
  await expectLastPost(events, '/api/settings/test/web');
  await expect(page.getByTestId('web-ui-status')).toHaveText('Connected');
  expect(events.slice(-2)).toEqual([
    {
      method: 'PATCH',
      payload: expect.objectContaining({
        web_url: 'https://192.168.1.199:8443',
        save_ai_audio: true,
        save_mic_audio: false,
        vad_threshold: 0.5,
        vad_end_silence_ms: 700,
        stt_model: 'distil-large-v3',
        tts_default_engine: 'f5'
      })
    },
    { method: 'POST', path: '/api/settings/test/web' }
  ]);

  await aiBackendSection.getByRole('button', { name: 'Test Connection' }).click();
  await expectLastPost(events, '/api/settings/test/ai-backend');
  await expect(page.getByTestId('ai-backend-status')).toHaveText('Connected');
  expect(events.slice(-2)).toEqual([
    {
      method: 'PATCH',
      payload: expect.objectContaining({
        ai_backend_url: 'https://192.168.1.199:9443',
        save_ai_audio: true,
        save_mic_audio: false
      })
    },
    { method: 'POST', path: '/api/settings/test/ai-backend' }
  ]);

  await llmSection.getByRole('button', { name: 'Test Connection' }).click();
  await expectLastPost(events, '/api/settings/test/llm');
  await expect(page.getByTestId('llm-status')).toHaveText('Connected');
  expect(events.slice(-2)).toEqual([
    {
      method: 'PATCH',
      payload: expect.objectContaining({
        llm_base_url: PHASE1_LOCAL_LLM_URL,
        llm_model: PHASE1_LOCAL_LLM_MODEL
      })
    },
    { method: 'POST', path: '/api/settings/test/llm' }
  ]);
  const llmPatch = events.at(-2) as Extract<SettingsEvent, { method: 'PATCH' }>;
  const payload = llmPatch.payload;
  expect(payload.llm_base_url).toBe(PHASE1_LOCAL_LLM_URL);
  expect(payload.llm_model).toBe(PHASE1_LOCAL_LLM_MODEL);
  expect(Object.prototype.hasOwnProperty.call(payload, 'llm_api_key')).toBe(false);
  expect(requestUrls.filter((url) => url.includes('192.168.1.190:8001'))).toEqual([]);
  await expect(page.getByText(/sk-|server-secret|sk-browser-supplied/i)).toHaveCount(0);
  await expect(page.getByTestId('web-ui-status')).toHaveText('Connected');
  await expect(page.getByTestId('ai-backend-status')).toHaveText('Connected');
  await expect(page.getByTestId('llm-status')).toHaveText('Connected');
  assertNoBrowserErrors();
});

async function routeSettingsTest(
  page: Page,
  path: string,
  events: SettingsEvent[]
) {
  await page.route(`**${path}`, async (route) => {
    events.push({ method: 'POST', path });
    await fulfillJson(route, { status: 'Connected' });
  });
}

async function expectLastPost(events: SettingsEvent[], path: string) {
  await expect.poll(() => events.at(-1)).toEqual({ method: 'POST', path });
}
