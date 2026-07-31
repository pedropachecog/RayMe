import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';

const QWEN_ENGINE_ID = 'qwen3_1_7b';
const QWEN_ENGINE_LABEL = 'Qwen3-TTS 1.7B-Base';
const MOCKED_CONTRACT_ENVIRONMENT = 'environment=mocked_contract';
const referenceTranscript = 'This exact transcript matches the permitted reference recording.';

type Preparation =
  | ReturnType<typeof loadingPreparation>
  | ReturnType<typeof readyPreparation>
  | ReturnType<typeof failedPreparation>;

test.describe('Phase 09 Qwen readiness browser contract', () => {
  test.beforeEach(async ({}, testInfo) => {
    testInfo.annotations.push({
      type: 'environment',
      description: MOCKED_CONTRACT_ENVIRONMENT
    });
  });

  test('maps dynamic Qwen engine metadata through loading, resident, and unavailable Settings states', async ({
    page
  }) => {
    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    let qwenState: 'loading' | 'resident' | 'unavailable' = 'loading';

    await page.route('**/api/settings', async (route) => {
      await fulfillJson(route, settingsPayload(qwenState));
    });

    await page.goto('/settings');
    const residency = page.locator('dl[aria-label="AI backend residency status"]');
    await expect(residency).toContainText(QWEN_ENGINE_LABEL);
    await expect(residency.getByRole('status', { name: '' })).toContainText(
      'Loading Qwen3-TTS 1.7B…'
    );
    await expect(page.getByText(QWEN_ENGINE_ID, { exact: true })).toHaveCount(0);

    qwenState = 'resident';
    await page.reload();
    await expect(residency.getByRole('status')).toHaveText('Qwen3-TTS 1.7B loaded');
    await expect(residency.getByText('None', { exact: true })).toBeVisible();

    qwenState = 'unavailable';
    await page.reload();
    await expect(residency.getByRole('alert')).toHaveText('Qwen3-TTS 1.7B unavailable');
    await expect(page.getByText(/traceback|cuda cache|private-reference|worker exception/i)).toHaveCount(0);
    assertNoBrowserErrors();
  });

  test('preserves Qwen authorization and form state through failed preparation, switching, and retry', async ({
    page
  }) => {
    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    let preparation: Preparation = loadingPreparation();
    let previewAttempt = 0;
    let resolveFirstPreview: () => void = () => {};
    let resolveRetryPreview: () => void = () => {};
    const firstPreviewGate = new Promise<void>((resolve) => {
      resolveFirstPreview = resolve;
    });
    const retryPreviewGate = new Promise<void>((resolve) => {
      resolveRetryPreview = resolve;
    });

    await installVoiceLabRoutes(page, {
      getPreparation: () => preparation,
      preview: async (route) => {
        previewAttempt += 1;
        const payload = route.request().postDataJSON() as Record<string, unknown>;
        expect(payload).toMatchObject({
          default_engine: QWEN_ENGINE_ID,
          reference_transcript: referenceTranscript,
          voice_data_steward: 'speaker-steward-17',
          authorization_basis: 'Direct permission for this LAN test',
          use_scope: 'rayme_lan_call_testing'
        });
        if (previewAttempt === 1) {
          await firstPreviewGate;
          await fulfillJson(route, {
            status: 'tts_failed',
            error: { code: 'qwen3_prompt_failed', message: 'C:\\private\\reference.wav' }
          });
          return;
        }
        await retryPreviewGate;
        await fulfillJson(route, {
          engine_id: QWEN_ENGINE_ID,
          content_type: 'audio/wav',
          audio_base64: makeTinyWav().toString('base64'),
          duration_ms: 420
        });
      }
    });

    await page.goto('/voice-lab');
    await uploadAndTranscribeReference(page);
    await page.getByRole('radio', { name: new RegExp(QWEN_ENGINE_LABEL) }).check();

    await expect(page.getByRole('heading', { name: 'Reference authorization' })).toBeVisible();
    const referenceSource = page.getByLabel('Reference source');
    const authorizationBasis = page.getByLabel('Authorization basis');
    const useScope = page.getByLabel('Use scope');
    for (const control of [referenceSource, authorizationBasis, useScope]) {
      await expect(control).toHaveAttribute('required', '');
    }
    await expect(referenceSource).toHaveValue('');
    await expect(authorizationBasis).toHaveValue('');
    await expect(useScope).toHaveValue('');
    await expect(page.getByRole('button', { name: 'Preview Voice' })).toBeDisabled();

    await referenceSource.fill('speaker-steward-17');
    await authorizationBasis.fill('Direct permission for this LAN test');
    await useScope.selectOption('rayme_lan_call_testing');
    await page.getByLabel('Voice name').fill('Persistent Qwen Voice');
    await page.getByLabel('Preview text').fill('Keep every field while preparation runs.');

    const previewButton = page.getByRole('button', { name: 'Preview Voice' });
    await previewButton.click();
    await expect(page.getByRole('button', { name: 'Preparing voice…' })).toBeFocused();
    await expect(page.getByRole('status', { name: '' }).filter({ hasText: 'Loading Qwen3-TTS 1.7B…' })).toHaveCount(1);
    await expect(page.getByRole('status', { name: '' }).filter({ hasText: 'Preparing saved voice…' })).toHaveCount(1);

    preparation = failedPreparation();
    await expect(page.getByRole('alert').filter({ hasText: 'Voice preparation failed' })).toBeVisible();
    resolveFirstPreview();
    await expect(page.getByRole('alert').filter({ hasText: /Retry preparation/ })).toBeVisible();
    await expect(page.getByText(/C:\\private|worker exception|traceback/i)).toHaveCount(0);
    await expect(referenceSource).toHaveValue('speaker-steward-17');
    await expect(authorizationBasis).toHaveValue('Direct permission for this LAN test');
    await expect(useScope).toHaveValue('rayme_lan_call_testing');
    await expect(page.getByLabel('Voice name')).toHaveValue('Persistent Qwen Voice');
    await expect(page.getByRole('textbox', { name: 'Reference transcript' })).toHaveValue(
      referenceTranscript
    );
    await expect(page.getByLabel('Preview text')).toHaveValue(
      'Keep every field while preparation runs.'
    );

    await page.getByRole('radio', { name: /F5-TTS/ }).check();
    await expect(page.getByRole('heading', { name: 'Reference authorization' })).toHaveCount(0);
    await page.getByRole('radio', { name: new RegExp(QWEN_ENGINE_LABEL) }).check();
    await expect(referenceSource).toHaveValue('speaker-steward-17');
    await expect(authorizationBasis).toHaveValue('Direct permission for this LAN test');
    await expect(useScope).toHaveValue('rayme_lan_call_testing');

    preparation = loadingPreparation();
    await page.getByRole('button', { name: 'Preview Voice' }).click();
    preparation = readyPreparation();
    await expect(page.getByRole('button', { name: 'Synthesizing…' })).toBeVisible();
    resolveRetryPreview();
    await expect(page.getByText('Preview ready.')).toBeVisible();
    assertNoBrowserErrors();
  });

  test('keeps Qwen Voice Library preparation row-local and retries a fixed sanitized failure', async ({
    page
  }) => {
    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    let preparation: Preparation = loadingPreparation();
    let requestCount = 0;
    let resolveFirstTestPlay: () => void = () => {};
    const firstTestPlayGate = new Promise<void>((resolve) => {
      resolveFirstTestPlay = resolve;
    });

    await installVoiceLibraryRoutes(page, {
      getPreparation: () => preparation,
      testPlay: async (route) => {
        requestCount += 1;
        if (requestCount === 1) {
          await firstTestPlayGate;
          await fulfillJson(route, successfulTestPlay());
          return;
        }
        if (requestCount === 2) {
          await fulfillJson(route, {
            status: 'tts_failed',
            error: { code: 'qwen3_worker_timeout', message: '/private/model-cache' }
          });
          return;
        }
        await fulfillJson(route, successfulTestPlay());
      }
    });

    await page.goto('/voice-lab');
    const qwenRow = page.getByRole('listitem', { name: /Qwen Saved Voice/ });
    const otherRow = page.getByRole('listitem', { name: /Unrelated Saved Voice/ });
    await expect(qwenRow).toContainText(QWEN_ENGINE_LABEL);

    await qwenRow.getByPlaceholder('Type a test phrase').fill('Test the saved Qwen voice.');
    await qwenRow.getByRole('button', { name: 'Test Voice' }).click();
    await expect(qwenRow.getByRole('button', { name: 'Preparing voice…' })).toBeFocused();
    await expect(qwenRow.getByRole('status')).toHaveText('Preparing saved voice…');
    await expect(otherRow.getByRole('button', { name: 'Test Voice' })).toBeEnabled();
    await expect(otherRow.getByRole('button', { name: 'Rename Voice' })).toBeEnabled();
    await expect(otherRow.getByRole('button', { name: 'Delete Voice' })).toBeEnabled();

    preparation = readyPreparation();
    await expect(qwenRow.getByRole('button', { name: 'Testing voice…' })).toBeVisible();
    resolveFirstTestPlay();
    await expect(qwenRow.getByLabel('Qwen Saved Voice generated test audio')).toBeVisible();

    preparation = failedPreparation('qwen3_worker_timeout');
    await qwenRow.getByRole('button', { name: 'Test Voice' }).click();
    await expect(qwenRow.getByRole('alert')).toHaveText(
      'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.'
    );
    await expect(page.getByText(/private\/model-cache|traceback|worker exception/i)).toHaveCount(0);
    await expect(qwenRow.getByRole('button', { name: 'Retry Preparation' })).toBeFocused();

    preparation = readyPreparation();
    await qwenRow.getByRole('button', { name: 'Retry Preparation' }).click();
    await expect(qwenRow.getByLabel('Qwen Saved Voice generated test audio')).toBeVisible();
    expect(requestCount).toBe(3);
    assertNoBrowserErrors();
  });

  test('keeps Qwen readiness usable at 320px with static reduced-motion progress and 44px targets', async ({
    page
  }) => {
    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    let preparation: Preparation = loadingPreparation();
    await page.setViewportSize({ width: 320, height: 720 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await installVoiceLibraryRoutes(page, {
      getPreparation: () => preparation,
      testPlay: async () => new Promise(() => {})
    });

    await page.goto('/voice-lab');
    const qwenRow = page.getByRole('listitem', { name: /Qwen Saved Voice/ });
    await qwenRow.getByRole('button', { name: 'Test Voice' }).click();
    await expect(qwenRow.getByRole('button', { name: 'Preparing voice…' })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);

    for (const name of ['Preparing voice…', 'Rename Voice', 'Delete Voice']) {
      const box = await qwenRow.getByRole('button', { name }).boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    await expect(qwenRow.locator('.preparing-icon')).toHaveCSS('animation-name', 'none');
    preparation = readyPreparation();
    assertNoBrowserErrors();
  });
});

function settingsPayload(qwenState: 'loading' | 'resident' | 'unavailable') {
  return {
    web_url: 'http://127.0.0.1:4173',
    ai_backend_url: 'http://127.0.0.1:9443',
    llm_base_url: '',
    llm_model: '',
    llm_disable_thinking: true,
    llm_api_key_configured: false,
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
      resident_tts_engine: qwenState === 'resident' ? QWEN_ENGINE_ID : 'f5',
      loading_engine: qwenState === 'loading' ? QWEN_ENGINE_ID : null,
      available_engines: [
        { id: 'f5', label: 'F5-TTS', available: true, state: qwenState === 'resident' ? 'idle' : 'resident' },
        {
          id: QWEN_ENGINE_ID,
          label: QWEN_ENGINE_LABEL,
          available: qwenState !== 'unavailable',
          state: qwenState,
          unavailable_reason: qwenState === 'unavailable' ? 'qwen_runtime_unavailable' : null
        }
      ],
      vram_used_mb: 5604,
      vram_headroom_mb: 5372
    }
  };
}

async function installVoiceLabRoutes(
  page: Page,
  options: {
    getPreparation: () => Preparation;
    preview: (route: Route) => Promise<void>;
  }
) {
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, settingsPayload('resident'));
  });
  await page.route('**/api/voices/preparation-status', async (route) => {
    await fulfillJson(route, options.getPreparation());
  });
  await page.route('**/api/voices/preview', options.preview);
  await installVoiceAssetRoutes(page);
  await page.route('**/api/voices', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [] });
      return;
    }
    await fulfillJson(route, { voice_id: 'voice-created' }, 201);
  });
}

async function installVoiceLibraryRoutes(
  page: Page,
  options: {
    getPreparation: () => Preparation;
    testPlay: (route: Route) => Promise<void>;
  }
) {
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, settingsPayload('resident'));
  });
  await page.route('**/api/voices/preparation-status', async (route) => {
    await fulfillJson(route, options.getPreparation());
  });
  await page.route('**/api/voices/voice-qwen/test-play', options.testPlay);
  await page.route('**/api/voices', async (route) => {
    await fulfillJson(route, {
      items: [
        {
          voice_id: 'voice-qwen',
          name: 'Qwen Saved Voice',
          default_engine: QWEN_ENGINE_ID,
          reference_transcript: referenceTranscript,
          status: 'available',
          created_at: '2026-07-31T18:00:00Z',
          updated_at: '2026-07-31T18:05:00Z',
          metadata: { assignment_status: 'Assigned to 1 character', speech_speed: 1 }
        },
        {
          voice_id: 'voice-other',
          name: 'Unrelated Saved Voice',
          default_engine: 'f5',
          reference_transcript: 'Unrelated reference transcript.',
          status: 'available',
          created_at: '2026-07-31T18:10:00Z',
          updated_at: '2026-07-31T18:10:00Z',
          metadata: { assignment_status: 'No assignments', speech_speed: 1 }
        }
      ]
    });
  });
}

async function installVoiceAssetRoutes(page: Page) {
  await page.route('**/api/voices/assets', async (route) => {
    await fulfillJson(route, {
      asset_id: 'asset-qwen',
      filename: 'qwen-reference.wav',
      duration_seconds: 8,
      content_type: 'audio/wav',
      warnings: []
    }, 201);
  });
  await page.route('**/api/voices/assets/asset-qwen/sample', async (route) => {
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: makeTinyWav() });
  });
  await page.route('**/api/voices/assets/asset-qwen/transcribe', async (route) => {
    await fulfillJson(route, {
      asset_id: 'asset-qwen',
      reference_transcript: referenceTranscript,
      reference_transcript_editable: true,
      language: 'en'
    });
  });
}

async function uploadAndTranscribeReference(page: Page) {
  await page.getByLabel('Upload Sample').setInputFiles({
    name: 'qwen-reference.wav',
    mimeType: 'audio/wav',
    buffer: makeTinyWav()
  });
  await page.getByRole('button', { name: 'Transcribe Sample' }).click();
  await expect(page.getByRole('textbox', { name: 'Reference transcript' })).toHaveValue(
    referenceTranscript
  );
}

function loadingPreparation() {
  return {
    model: { state: 'loading' as const, engine_id: QWEN_ENGINE_ID },
    prompt: { state: 'prewarming' as const, voice_key: 'opaque-qwen-key', error_code: null }
  };
}

function readyPreparation() {
  return {
    model: { state: 'resident' as const, engine_id: QWEN_ENGINE_ID },
    prompt: { state: 'ready' as const, voice_key: 'opaque-qwen-key', error_code: null }
  };
}

function failedPreparation(errorCode = 'qwen3_prompt_failed') {
  return {
    model: { state: 'resident' as const, engine_id: QWEN_ENGINE_ID },
    prompt: { state: 'failed' as const, voice_key: 'opaque-qwen-key', error_code: errorCode }
  };
}

function successfulTestPlay() {
  return {
    voice_id: 'voice-qwen',
    engine_id: QWEN_ENGINE_ID,
    content_type: 'audio/wav',
    audio_base64: makeTinyWav().toString('base64'),
    duration_ms: 420
  };
}

function makeTinyWav() {
  return Buffer.from([
    0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
    0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00
  ]);
}
