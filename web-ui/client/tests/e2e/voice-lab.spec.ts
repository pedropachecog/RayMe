import { expect, test, type Page, type Request } from '@playwright/test';

import {
  expectRayMeApiRequest,
  fulfillJson,
  installBrowserErrorGuard
} from './helpers/acceptance';

const engineLabels = [
  'F5-TTS',
  'XTTS v2',
  'Qwen3-TTS 0.6B-Base',
  'LuxTTS',
  'Chatterbox Turbo',
  'TADA 1B'
];

const sampleTranscript = 'This is the editable voice lab transcript.';
const editedTranscript = 'This is the edited reference transcript.';
const previewText = 'Preview this RayMe voice.';

test('Voice Lab saves after preview returns HTTP 502 and stays on RayMe APIs', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLabApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  for (const stepLabel of ['1 Upload', '2 Transcript', '3 Engine', '4 Preview', '5 Save']) {
    await expect(page.getByText(stepLabel)).toBeVisible();
  }

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'sample.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByLabel('Reference transcript')).toHaveValue(sampleTranscript);
  await page.getByLabel('Reference transcript').fill(editedTranscript);

  for (const engine of engineLabels) {
    await expect(page.getByRole('radio', { name: new RegExp(escapeRegExp(engine)) })).toBeVisible();
  }

  await page.getByLabel('Voice name').fill('RayMe Browser Voice');
  await page.getByRole('radio', { name: /Chatterbox Turbo/ }).check();
  await page.getByLabel('Use default engine').uncheck();
  await page.getByLabel('Preview text').fill(previewText);
  await page.getByRole('button', { name: 'Preview Voice' }).click();
  await expect(page.getByText(/preview failed/i)).toBeVisible();
  await expect(page.getByLabel('Voice name')).toHaveValue('RayMe Browser Voice');
  await expect(page.getByLabel('Reference transcript')).toHaveValue(editedTranscript);
  await expect(page.getByRole('radio', { name: /Chatterbox Turbo/ })).toBeChecked();
  await expect(page.getByLabel('Preview text')).toHaveValue(previewText);

  await expect(page.getByRole('button', { name: 'Save Voice' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save Voice' }).click();
  await expect(page.getByText('Voice saved.')).toBeVisible();

  expect(voiceEvents).toEqual(
    expect.arrayContaining([
      'POST /api/voices/assets',
      'POST /api/voices/assets/sample-asset/transcribe',
      'POST /api/voices/preview',
      'POST /api/voices'
    ])
  );
  assertNoBrowserErrors();
});

test('Voice Lab has no horizontal scroll at 320px viewport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await routeVoiceLabApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});

async function routeVoiceLabApis(page: Page) {
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, {
      web_url: 'http://127.0.0.1:4173',
      ai_backend_url: 'http://127.0.0.1:9443',
      llm_base_url: '',
      llm_model: '',
      llm_api_key_configured: false,
      save_ai_audio: true,
      save_mic_audio: false,
      vad_threshold: 0.5,
      vad_end_silence_ms: 700,
      stt_model: 'distil-large-v3',
      tts_default_engine: 'f5',
      ai_backend_status: {
        endpoint_status: 'Connected',
        resident_tts_engine: 'f5',
        loading_engine: null,
        available_engines: [
          { id: 'f5', label: 'F5-TTS', available: true, state: 'resident' },
          { id: 'xtts_v2', label: 'XTTS v2', available: true, state: 'idle' },
          { id: 'qwen3_0_6b', label: 'Qwen3-TTS 0.6B-Base', available: true, state: 'idle' },
          { id: 'luxtts', label: 'LuxTTS', available: true, state: 'idle' },
          { id: 'chatterbox_turbo', label: 'Chatterbox Turbo', available: true, state: 'idle' },
          { id: 'tada_1b', label: 'TADA 1B', available: true, state: 'idle' }
        ]
      }
    });
  });

  await page.route('**/api/voices', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject({
      asset_id: 'sample-asset',
      name: 'RayMe Browser Voice',
      reference_transcript: editedTranscript,
      default_engine: 'chatterbox_turbo'
    });
    await fulfillJson(route, {
      voice_id: 'voice-rayme',
      asset_id: 'sample-asset',
      name: 'RayMe Browser Voice',
      default_engine: 'chatterbox_turbo',
      reference_transcript: editedTranscript,
      status: 'available'
    }, 201);
  });

  await page.route('**/api/voices/assets', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      asset_id: 'sample-asset',
      filename: 'sample.wav',
      duration_seconds: 7.2,
      content_type: 'audio/wav',
      warnings: []
    }, 201);
  });

  await page.route('**/api/voices/assets/sample-asset/transcribe', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      asset_id: 'sample-asset',
      reference_transcript: sampleTranscript,
      reference_transcript_editable: true,
      language: 'en'
    });
  });

  await page.route('**/api/voices/preview', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject({
      asset_id: 'sample-asset',
      reference_transcript: editedTranscript,
      default_engine: 'chatterbox_turbo',
      use_default_engine: false,
      engine: 'chatterbox_turbo',
      preview_text: previewText
    });
    await fulfillJson(route, { error: { message: 'Preview synthesis failed' } }, 502);
  });
}

function recordVoiceApiRequest(request: Request, events: string[]) {
  const url = new URL(request.url());
  if (!url.pathname.startsWith('/api/voices')) {
    return;
  }

  events.push(`${request.method()} ${url.pathname}${url.search}`);
}

function makeTinyWav() {
  return Buffer.from([
    0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
    0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00
  ]);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
