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
const testPhrase = 'Testing this saved RayMe voice.';

test('Voice Lab upload transcript save library and unavailable voice flow stays on RayMe APIs', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const requests: string[] = [];
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    requests.push(request.url());
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLabApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();
  await expect(page.getByText('No voices yet')).toBeVisible();

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

  await page.getByRole('button', { name: 'Save Voice' }).click();
  await expect(page.getByRole('row', { name: /RayMe Browser Voice/ })).toBeVisible();

  const voiceRow = page.getByRole('row', { name: /RayMe Browser Voice/ });
  await voiceRow.getByRole('button', { name: 'Rename Voice' }).click();
  await page.getByLabel('Voice name').fill('RayMe Browser Voice Renamed');
  await page.getByRole('button', { name: 'Save Voice' }).click();
  await expect(page.getByRole('row', { name: /RayMe Browser Voice Renamed/ })).toBeVisible();

  await page.getByLabel('Test voice text').fill(testPhrase);
  await page.getByRole('button', { name: 'Test Voice' }).click();
  await expect(page.getByText(/test voice ready/i)).toBeVisible();

  await page.goto('/gallery');
  await expect(page.getByTestId('character-card-no-voice')).toContainText('No voice');
  await expect(page.getByTestId('character-card-assigned-voice')).toContainText(
    'RayMe Browser Voice Renamed'
  );

  await page.goto('/voice-lab');
  await page.getByRole('row', { name: /RayMe Browser Voice Renamed/ }).getByRole('button', {
    name: 'Delete Voice'
  }).click();
  await page.getByRole('button', { name: 'Delete Voice' }).click();
  await expect(page.getByText('Voice unavailable')).toBeVisible();

  await page.goto('/gallery');
  await expect(page.getByTestId('character-card-unavailable-voice')).toContainText('Voice unavailable');

  expect(voiceEvents).toEqual(
    expect.arrayContaining([
      'POST /api/voices/assets',
      'POST /api/voices/assets/sample-asset/transcribe',
      'POST /api/voices/preview',
      'POST /api/voices',
      'PATCH /api/voices/voice-rayme',
      'POST /api/voices/voice-rayme/test-play',
      'DELETE /api/voices/voice-rayme?force=true'
    ])
  );
  expect(requests.some((url) => url.includes('/api/voices'))).toBe(true);
  assertNoBrowserErrors();
});

async function routeVoiceLabApis(page: Page) {
  await page.route('**/api/voices', async (route) => {
    const request = route.request();

    if (request.method() === 'GET') {
      await fulfillJson(route, {
        items: []
      });
      return;
    }

    expect(request.method()).toBe('POST');
    expect(request.postDataJSON()).toMatchObject({
      name: 'RayMe Browser Voice',
      transcript: editedTranscript,
      default_engine: 'chatterbox_turbo',
      preview_id: null
    });
    await fulfillJson(route, {
      id: 'voice-rayme',
      name: 'RayMe Browser Voice',
      default_engine: 'chatterbox_turbo',
      transcript: editedTranscript,
      assignment_status: 'unused'
    });
  });

  await page.route('**/api/voices/assets', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      asset_id: 'sample-asset',
      filename: 'sample.wav',
      duration_seconds: 7.2,
      content_type: 'audio/wav'
    });
  });

  await page.route('**/api/voices/assets/sample-asset/transcribe', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      transcript: sampleTranscript,
      language: 'en'
    });
  });

  await page.route('**/api/voices/preview', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject({
      asset_id: 'sample-asset',
      transcript: editedTranscript,
      engine: 'chatterbox_turbo',
      text: previewText
    });
    await fulfillJson(route, { error: 'preview failed' }, 503);
  });

  await page.route('**/api/voices/voice-rayme', async (route) => {
    expect(route.request().method()).toBe('PATCH');
    await fulfillJson(route, {
      id: 'voice-rayme',
      name: 'RayMe Browser Voice Renamed',
      default_engine: 'chatterbox_turbo',
      transcript: editedTranscript
    });
  });

  await page.route('**/api/voices/voice-rayme/test-play', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject({
      text: testPhrase,
      use_default_engine: true
    });
    await fulfillJson(route, {
      audio_url: '/api/voices/voice-rayme/test-play/latest.wav',
      status: 'ready'
    });
  });

  await page.route('**/api/voices/voice-rayme?force=true', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    await fulfillJson(route, {
      voice_id: 'voice-rayme',
      deleted: true,
      affected_characters: [{ id: 'character-unavailable', name: 'Unavailable Character' }]
    });
  });

  await page.route('**/api/characters', async (route) => {
    await fulfillJson(route, {
      items: [
        { id: 'character-no-voice', name: 'No Voice Character', default_voice: null },
        {
          id: 'character-assigned-voice',
          name: 'Assigned Voice Character',
          default_voice: { id: 'voice-rayme', name: 'RayMe Browser Voice Renamed' }
        },
        {
          id: 'character-unavailable-voice',
          name: 'Unavailable Voice Character',
          default_voice: { id: 'voice-rayme', name: 'Voice unavailable', unavailable: true }
        }
      ]
    });
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
