import { expect, test, type Locator, type Page, type Request } from '@playwright/test';

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
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLabApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  for (const stepLabel of ['1 Upload', '2 Transcript', '3 Engine', '4 Preview', '5 Save']) {
    await expect(page.getByText(stepLabel, { exact: true })).toBeVisible();
  }

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'sample.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await expect(page.getByLabel('Voice name')).toHaveValue('sample');
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByLabel('Play uploaded sample')).toBeVisible();
  await expect(page.getByLabel('Reference transcript')).toHaveValue(sampleTranscript);
  await page.getByLabel('Reference transcript').fill(editedTranscript);

  for (const engine of engineLabels) {
    await expect(page.getByRole('radio', { name: new RegExp(escapeRegExp(engine)) })).toBeVisible();
  }

  await page.getByLabel('Voice name').fill('RayMe Browser Voice');
  await page.getByLabel('Preview text').fill(previewText);
  await setRangeValue(page.getByLabel('Speech speed'), '0.75');
  await page.getByRole('button', { name: 'Preview Voice' }).click();
  await expect(page.getByText(/preview failed/i)).toBeVisible();
  await expect(page.getByLabel('Voice name')).toHaveValue('RayMe Browser Voice');
  await expect(page.getByLabel('Reference transcript')).toHaveValue(editedTranscript);
  await expect(page.getByRole('radio', { name: /F5-TTS/ })).toBeChecked();
  await expect(page.getByLabel('Preview text')).toHaveValue(previewText);
  await expect(page.getByLabel('Speech speed')).toHaveValue('0.75');

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

test('Voice Lab renders VoxCPM2 controls only for VoxCPM2 and saves settings', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLabApis(page, { includeVoxCpm2: true, expectedEngine: 'voxcpm2' });

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'voxcpm2-sample.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByLabel('Reference transcript')).toHaveValue(sampleTranscript);
  await page.getByLabel('Reference transcript').fill(editedTranscript);

  await expect(page.getByRole('radio', { name: /F5-TTS/ })).toBeChecked();
  await expect(page.getByRole('radio', { name: /Reference only/ })).toHaveCount(0);
  await expect(page.getByRole('radio', { name: /Transcript guided/ })).toHaveCount(0);

  await expect(page.getByRole('radio', { name: /VoxCPM2/ })).toBeVisible();
  await page.getByRole('radio', { name: /VoxCPM2/ }).check();
  await expect(page.getByRole('radio', { name: /Reference only/ })).toBeVisible();
  await expect(page.getByRole('radio', { name: /Transcript guided/ })).toBeVisible();
  await expect(
    page.getByText('Transcript-guided mode may improve VoxCPM2 results')
  ).toBeVisible();
  await expect(page.getByLabel('Style prompt')).toHaveAttribute('maxlength', '300');
  await expect(page.getByLabel('CFG value')).toHaveAttribute('min', '1');
  await expect(page.getByLabel('CFG value')).toHaveAttribute('max', '3');
  await expect(page.getByLabel('Inference timesteps')).toHaveAttribute('min', '4');
  await expect(page.getByLabel('Inference timesteps')).toHaveAttribute('max', '30');

  await page.getByRole('radio', { name: /Transcript guided/ }).check();
  await page.getByLabel('Style prompt').fill('Warm phone-call delivery.');
  await setRangeValue(page.getByLabel('CFG value'), '2.2');
  await setRangeValue(page.getByLabel('Inference timesteps'), '12');
  await page.getByLabel('Normalize').check();
  await setRangeValue(page.getByLabel('Speech speed'), '0.75');
  await page.getByLabel('Voice name').fill('RayMe Browser Voice');
  await page.getByRole('button', { name: 'Save Voice' }).click();
  await expect(page.getByText('Voice saved.')).toBeVisible();

  expect(voiceEvents).toEqual(
    expect.arrayContaining([
      'POST /api/voices/assets',
      'POST /api/voices/assets/sample-asset/transcribe',
      'POST /api/voices'
    ])
  );
  assertNoBrowserErrors();
});

test('Voice Lab unlocks preview and save after failed transcription with manual transcript', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [
      /Failed to load resource: the server responded with a status of 500 \(Internal Server Error\)/
    ]
  });
  const voiceEvents: string[] = [];
  const manualTranscript = 'sjort jist to trst';

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLabApis(page, { transcribeFails: true, expectedTranscript: manualTranscript });

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'android-sample.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await expect(page.getByLabel('Voice name')).toHaveValue('android-sample');
  await expect(page.getByLabel('Play uploaded sample')).toBeVisible();
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByText(/transcription failed/i)).toBeVisible();

  await page.getByLabel('Reference transcript').fill(manualTranscript);
  await expect(page.getByRole('button', { name: 'Preview Voice' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Save Voice' })).toBeEnabled();

  await page.getByRole('button', { name: 'Preview Voice' }).click();
  await expect(page.getByText('Preview ready.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play preview audio' })).toBeEnabled();

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

test('Voice Library test-play keeps another row rename action available', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceLibraryApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  const firstRow = page.getByRole('listitem', { name: /Aster Saved Voice/ });
  const secondRow = page.getByRole('listitem', { name: /Basil Saved Voice/ });
  await expect(firstRow).toContainText('Assigned to 1 character');
  await expect(firstRow.getByRole('button', { name: 'Test Voice' })).toBeEnabled();
  await expect(secondRow.getByRole('button', { name: 'Rename Voice' })).toBeEnabled();

  await firstRow.getByPlaceholder('Type a test phrase').fill('Read this library test phrase.');
  await firstRow.getByLabel('Use default engine').check();
  await setRangeValue(firstRow.getByLabel('Aster Saved Voice speech speed'), '0.75');
  await firstRow.getByRole('button', { name: 'Test Voice' }).click();
  await expect(firstRow.getByText('Testing voice...')).toBeVisible();
  await expect(secondRow.getByRole('button', { name: 'Rename Voice' })).toBeEnabled();
  await expect(firstRow.getByLabel('Aster Saved Voice generated test audio')).toBeVisible();

  expect(voiceEvents).toEqual(
    expect.arrayContaining(['GET /api/voices', 'POST /api/voices/voice-a/test-play'])
  );
  assertNoBrowserErrors();
});

test('Voice Library blocked delete lists character referent before force delete', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 409/]
  });
  const voiceEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceDeleteApis(page);

  await page.goto('/voice-lab');
  await expect(page.getByRole('heading', { name: 'Voice Lab' })).toBeVisible();

  const row = page.getByRole('listitem', { name: /Referenced Saved Voice/ });
  await row.getByRole('button', { name: 'Delete Voice' }).click();

  await expect(page.getByRole('dialog', { name: 'Delete voice: Delete this voice?' })).toBeVisible();
  await expect(page.getByText('Readable referent')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Force Delete Voice' })).toBeVisible();

  await page.getByRole('button', { name: 'Force Delete Voice' }).click();
  await expect(page.getByText('Voice unavailable')).toBeVisible();
  await expect(row).toBeHidden();

  expect(voiceEvents).toEqual(
    expect.arrayContaining([
      'GET /api/voices',
      'DELETE /api/voices/voice-a',
      'DELETE /api/voices/voice-a?force=true'
    ])
  );
  assertNoBrowserErrors();
});

test('Gallery voice badges show assigned, none, and force-deleted unavailable states', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 409/]
  });
  const voiceEvents: string[] = [];
  let voiceForceDeleted = false;

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordVoiceApiRequest(request, voiceEvents);
  });

  await routeVoiceDeleteApis(page, () => {
    voiceForceDeleted = true;
  });
  await routeGalleryVoiceStateApis(page, () => voiceForceDeleted);

  await page.goto('/gallery');
  await expect(page.getByTestId('character-card-assigned-character')).toContainText(
    'Voice: Referenced Saved Voice'
  );
  await expect(page.getByTestId('character-card-no-voice-character')).toContainText('No voice');

  await page.goto('/voice-lab');
  const row = page.getByRole('listitem', { name: /Referenced Saved Voice/ });
  await row.getByRole('button', { name: 'Delete Voice' }).click();
  await page.getByRole('button', { name: 'Force Delete Voice' }).click();
  await expect(page.getByText('Voice unavailable')).toBeVisible();

  await page.goto('/gallery');
  await expect(page.getByTestId('character-card-assigned-character')).toContainText(
    'Voice unavailable'
  );
  await expect(page.getByTestId('character-card-no-voice-character')).toContainText('No voice');
  expect(voiceEvents).toEqual(
    expect.arrayContaining(['DELETE /api/voices/voice-a?force=true'])
  );
  assertNoBrowserErrors();
});

async function routeVoiceLabApis(
  page: Page,
  options: {
    transcribeFails?: boolean;
    expectedTranscript?: string;
    includeVoxCpm2?: boolean;
    expectedEngine?: string;
  } = {}
) {
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
          {
            id: 'xtts_v2',
            label: 'XTTS v2',
            available: false,
            state: 'unavailable',
            unavailable_reason: 'engine synthesis is not implemented in Phase 02'
          },
          {
            id: 'qwen3_0_6b',
            label: 'Qwen3-TTS 0.6B-Base',
            available: false,
            state: 'unavailable',
            unavailable_reason: 'engine synthesis is not implemented in Phase 02'
          },
          {
            id: 'luxtts',
            label: 'LuxTTS',
            available: false,
            state: 'unavailable',
            unavailable_reason: 'engine synthesis is not implemented in Phase 02'
          },
          {
            id: 'chatterbox_turbo',
            label: 'Chatterbox Turbo',
            available: false,
            state: 'unavailable',
            unavailable_reason: 'engine synthesis is not implemented in Phase 02'
          },
          {
            id: 'tada_1b',
            label: 'TADA 1B',
            available: false,
            state: 'unavailable',
            unavailable_reason: 'engine synthesis is not implemented in Phase 02'
          },
          ...(options.includeVoxCpm2
            ? [
                {
                  id: 'voxcpm2',
                  label: 'VoxCPM2',
                  available: true,
                  state: 'idle',
                  caveats: ['Candidate', '48 kHz', 'RTX 3060 gate pending']
                }
              ]
            : [])
        ]
      }
    });
  });

  await page.route('**/api/voices', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [] });
      return;
    }

    expect(route.request().method()).toBe('POST');
    const expectedEngine = options.expectedEngine ?? 'f5';
    const expectedMetadata =
      expectedEngine === 'voxcpm2'
        ? {
            speech_speed: options.transcribeFails ? 0.85 : 0.75,
            engine_settings: {
              voxcpm2: {
                cloning_mode: 'transcript_guided',
                style_prompt: 'Warm phone-call delivery.',
                cfg_value: 2.2,
                inference_timesteps: 12,
                normalize: true,
                denoise: false
              }
            }
          }
        : {
            speech_speed: options.transcribeFails ? 0.85 : 0.75
          };
    expect(route.request().postDataJSON()).toMatchObject({
      asset_id: 'sample-asset',
      name: options.transcribeFails ? 'android-sample' : 'RayMe Browser Voice',
      reference_transcript: options.expectedTranscript ?? editedTranscript,
      default_engine: expectedEngine,
      metadata: expectedMetadata
    });
    await fulfillJson(route, {
      voice_id: 'voice-rayme',
      asset_id: 'sample-asset',
      name: options.transcribeFails ? 'android-sample' : 'RayMe Browser Voice',
      default_engine: expectedEngine,
      reference_transcript: options.expectedTranscript ?? editedTranscript,
      metadata: expectedMetadata,
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

  await page.route('**/api/voices/assets/sample-asset/sample', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: makeTinyWav()
    });
  });

  await page.route('**/api/voices/assets/sample-asset/transcribe', async (route) => {
    expect(route.request().method()).toBe('POST');
    if (options.transcribeFails) {
      await fulfillJson(route, { error: { message: 'Transcription failed' } }, 500);
      return;
    }

    await fulfillJson(route, {
      asset_id: 'sample-asset',
      reference_transcript: sampleTranscript,
      reference_transcript_editable: true,
      language: 'en'
    });
  });

  await page.route('**/api/voices/preview', async (route) => {
    expect(route.request().method()).toBe('POST');
    const expectedPayload = options.transcribeFails
      ? {
          asset_id: 'sample-asset',
          name: 'android-sample',
          reference_transcript: options.expectedTranscript,
          default_engine: 'f5',
          use_default_engine: true,
          preview_text: 'The line is open. This is how the saved RayMe voice will sound.',
          speech_speed: 0.85
        }
      : {
          asset_id: 'sample-asset',
          reference_transcript: editedTranscript,
          default_engine: 'f5',
          use_default_engine: true,
          preview_text: previewText,
          speech_speed: 0.75
        };
    expect(route.request().postDataJSON()).toMatchObject(expectedPayload);
    if (options.transcribeFails) {
      await fulfillJson(route, {
        engine_id: 'f5',
        content_type: 'audio/wav',
        audio_base64: makeTinyWav().toString('base64'),
        duration_ms: 420
      });
      return;
    }

    await fulfillJson(route, { error: { message: 'Preview synthesis failed' } }, 502);
  });
}

async function routeVoiceLibraryApis(page: Page) {
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

  await page.route('**/api/voices/voice-a/test-play', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject({
      text: 'Read this library test phrase.',
      use_default_engine: true,
      speech_speed: 0.75
    });
    await new Promise((resolve) => setTimeout(resolve, 250));
    await fulfillJson(route, {
      voice_id: 'voice-a',
      engine: 'f5',
      audio_url: '/api/voices/voice-a/test-play/audio'
    });
  });

  await page.route('**/api/voices/voice-a/test-play/audio', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: makeTinyWav()
    });
  });

  await page.route('**/api/voices', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, {
      items: [
        {
          voice_id: 'voice-a',
          name: 'Aster Saved Voice',
          default_engine: 'f5',
          reference_transcript: 'Aster reference transcript.',
          status: 'available',
          created_at: '2026-04-25T01:00:00Z',
          updated_at: '2026-04-25T01:15:00Z',
          metadata: { assignment_status: 'Assigned to 1 character', speech_speed: 0.85 }
        },
        {
          voice_id: 'voice-b',
          name: 'Basil Saved Voice',
          default_engine: 'xtts_v2',
          reference_transcript: null,
          status: 'available',
          created_at: '2026-04-25T01:30:00Z',
          updated_at: '2026-04-25T01:30:00Z',
          metadata: { assignment_status: 'No assignments' }
        }
      ]
    });
  });
}

async function routeVoiceDeleteApis(page: Page, onForceDelete: () => void = () => {}) {
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
        available_engines: [{ id: 'f5', label: 'F5-TTS', available: true, state: 'resident' }]
      }
    });
  });

  await page.route('**/api/voices/voice-a**', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    const url = new URL(route.request().url());
    if (url.searchParams.get('force') === 'true') {
      onForceDelete();
      await fulfillJson(route, {
        voice_id: 'voice-a',
        deleted: true,
        strategy: 'soft_delete',
        referents: [{ kind: 'character', id: 'character-1', name: 'Readable referent' }]
      });
      return;
    }

    await fulfillJson(
      route,
      {
        detail: {
          message: 'Voice is referenced',
          referents: [{ kind: 'character', id: 'character-1', name: 'Readable referent' }]
        }
      },
      409
    );
  });

  await page.route('**/api/voices', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, {
      items: [
        {
          voice_id: 'voice-a',
          name: 'Referenced Saved Voice',
          default_engine: 'f5',
          reference_transcript: 'Referenced transcript.',
          status: 'available',
          created_at: '2026-04-25T01:00:00Z',
          updated_at: '2026-04-25T01:15:00Z',
          metadata: { assignment_status: 'Assigned to 1 character' }
        }
      ]
    });
  });
}

async function routeGalleryVoiceStateApis(page: Page, isVoiceForceDeleted: () => boolean) {
  await page.route('**/api/characters', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, {
      items: [
        {
          id: 'assigned-character',
          name: 'Assigned Aster',
          description: 'Assigned voice character.',
          tags: [],
          default_voice_id: 'voice-a',
          default_voice_state: isVoiceForceDeleted() ? 'unavailable' : 'assigned',
          default_voice_label: isVoiceForceDeleted()
            ? 'Voice unavailable'
            : 'Referenced Saved Voice',
          default_voice: isVoiceForceDeleted()
            ? {
                id: 'voice-a',
                deleted_name: 'Referenced Saved Voice',
                status: 'deleted'
              }
            : {
                id: 'voice-a',
                name: 'Referenced Saved Voice',
                default_engine: 'f5',
                status: 'available'
              }
        },
        {
          id: 'no-voice-character',
          name: 'Quiet Basil',
          description: 'No voice character.',
          tags: [],
          default_voice_id: null,
          default_voice_state: 'none',
          default_voice_label: 'No voice',
          default_voice: null
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

async function setRangeValue(locator: Locator, value: string) {
  await locator.evaluate((node, nextValue) => {
    const input = node as HTMLInputElement;
    input.value = nextValue;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
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
