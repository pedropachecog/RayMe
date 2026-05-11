import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

import { expect, test, type APIRequestContext, type Page, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;
const liveReferenceAudioFile = process.env.RAYME_LIVE_REFERENCE_AUDIO_FILE;
const liveFakeAudioFile = process.env.RAYME_LIVE_FAKE_AUDIO_FILE;
const liveReferenceTranscript =
  process.env.RAYME_LIVE_REFERENCE_TRANSCRIPT ??
  'Some call me nature, others call me mother nature.';
const liveStabilityMs = parsePositiveInt(process.env.RAYME_LIVE_STABILITY_MS);

const localLlmUrl = process.env.RAYME_LIVE_LLM_URL ?? 'http://192.168.1.190:8001/v1';
const localLlmModel = process.env.RAYME_LIVE_LLM_MODEL ?? 'unsloth/Qwen3.5-27B';

test.skip(
  !liveEnabled || !liveWebUrl || !liveAiHealthUrl || !liveReferenceAudioFile || !liveFakeAudioFile,
  'Set RAYME_ENABLE_LIVE_E2E=1, RAYME_LIVE_WEB_URL, RAYME_LIVE_AI_HEALTH_URL, RAYME_LIVE_REFERENCE_AUDIO_FILE, and RAYME_LIVE_FAKE_AUDIO_FILE to run live call acceptance.'
);

test.use({
  ignoreHTTPSErrors: true,
  permissions: ['microphone'],
  launchOptions: {
    args: [
      '--autoplay-policy=no-user-gesture-required',
      '--disable-features=WebRtcHideLocalIpsWithMdns',
      '--force-webrtc-ip-handling-policy=default_public_interface_only',
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
      `--use-file-for-fake-audio-capture=${liveFakeAudioFile ?? ''}`
    ]
  }
});

test('live OMEN-PC browser call completes two user to AI cycles without mocked call media', async ({
  page,
  request: apiRequest
}) => {
  test.setTimeout(600_000 + liveStabilityMs);
  expect(liveWebUrl).toBe(canonicalLiveWebUrl);
  expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);

  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const liveEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordLiveCallRequest(request, liveEvents);
  });

  const healthResponse = await page.goto(canonicalLiveAiHealthUrl);
  expect(healthResponse?.ok(), `AI backend health at ${canonicalLiveAiHealthUrl}`).toBe(true);
  await expect(page.locator('body')).toContainText(/ok|healthy|status/i);

  await configureLiveSettings(apiRequest);
  const fixture = await createLiveCallFixture(apiRequest);

  await page.goto(`${canonicalLiveWebUrl}/`);
  expect(await page.evaluate(() => window.isSecureContext)).toBe(true);

  const startResponsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/api/calls/start' &&
      response.request().method() === 'POST' &&
      response.ok(),
    { timeout: 60_000 }
  );
  const offerResponsePromise = page.waitForResponse(
    (response) =>
      /\/api\/calls\/[^/]+\/offer$/.test(new URL(response.url()).pathname) &&
      response.request().method() === 'POST' &&
      response.ok(),
    { timeout: 90_000 }
  );

  await page.goto(`${canonicalLiveWebUrl}/call/${encodeURIComponent(fixture.threadId)}`);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible({
    timeout: 60_000
  });
  const startPayload = (await startResponsePromise).json();
  await offerResponsePromise;

  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(5_000);
  await page.getByRole('button', { name: 'Unmute' }).click();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible({ timeout: 30_000 });

  await expect.poll(() => transcriptTurnCount(page, 'user_speech'), { timeout: 240_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => transcriptTurnCount(page, 'ai_speech'), { timeout: 300_000 }).toBeGreaterThanOrEqual(2);

  if (liveStabilityMs > 0) {
    const beforeUserTurns = await transcriptTurnCount(page, 'user_speech');
    const beforeAiTurns = await transcriptTurnCount(page, 'ai_speech');
    await page.waitForTimeout(liveStabilityMs);
    const afterUserTurns = await transcriptTurnCount(page, 'user_speech');
    const afterAiTurns = await transcriptTurnCount(page, 'ai_speech');
    console.log(
      `[live-stability] duration_ms=${liveStabilityMs} before_user=${beforeUserTurns} before_ai=${beforeAiTurns} after_user=${afterUserTurns} after_ai=${afterAiTurns}`
    );
    expect(afterUserTurns).toBeGreaterThanOrEqual(beforeUserTurns);
    expect(afterAiTurns).toBeGreaterThanOrEqual(beforeAiTurns);
  }

  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('button', { name: 'Return to Thread' })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Return to Thread' }).click();
  await expect(page).toHaveURL(new RegExp(`/chat/${escapeRegExp(fixture.threadId)}$`), { timeout: 60_000 });
  await expect.poll(() => threadRowCount(page, 'call_start'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
  await expect.poll(() => threadRowCount(page, 'user_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => threadRowCount(page, 'ai_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => threadRowCount(page, 'call_end'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);

  const started = await startPayload;
  expect(started.session_id || started.call_id, 'live call session id').toBeTruthy();
  expect(liveEvents).toEqual(
    expect.arrayContaining([
      'POST /api/calls/start',
      expect.stringMatching(/^POST \/api\/calls\/.+\/offer$/),
      expect.stringMatching(/^POST \/api\/calls\/.+\/mute$/),
      expect.stringMatching(/^POST \/api\/calls\/.+\/turns$/),
      expect.stringMatching(/^POST \/api\/calls\/.+\/end$/)
    ])
  );
  assertNoBrowserErrors();
});

function recordLiveCallRequest(request: Request, events: string[]) {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/calls') || url.pathname.startsWith('/webrtc')) {
    events.push(`${request.method()} ${url.pathname}`);
  }
}

async function configureLiveSettings(apiRequest: APIRequestContext) {
  const response = await apiRequest.patch(`${canonicalLiveWebUrl}/api/settings`, {
    data: {
      web_url: canonicalLiveWebUrl,
      ai_backend_url: 'https://192.168.1.199:9443',
      llm_base_url: localLlmUrl,
      llm_model: localLlmModel,
      llm_api_key: '',
      tts_default_engine: 'f5'
    }
  });
  expect(response.ok(), 'configure live endpoint settings').toBe(true);
}

async function createLiveCallFixture(apiRequest: APIRequestContext) {
  expect(liveReferenceAudioFile, 'live reference audio fixture').toBeTruthy();
  const referenceAudio = readFileSync(liveReferenceAudioFile!);
  const timestamp = Date.now();

  const assetResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/voices/assets`, {
    multipart: {
      file: {
        name: basename(liveReferenceAudioFile!),
        mimeType: 'audio/wav',
        buffer: referenceAudio
      }
    }
  });
  expect(assetResponse.ok(), 'upload live reference voice asset').toBe(true);
  const asset = await assetResponse.json();
  expect(asset.asset_id, 'live reference voice asset id').toBeTruthy();

  const voiceResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/voices`, {
    data: {
      asset_id: asset.asset_id,
      name: `Live Call Voice ${timestamp}`,
      default_engine: 'f5',
      reference_transcript: liveReferenceTranscript,
      metadata: {}
    }
  });
  expect(voiceResponse.ok(), 'save live call voice').toBe(true);
  const voice = await voiceResponse.json();
  expect(voice.voice_id, 'live call voice id').toBeTruthy();

  const characterResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/characters`, {
    data: {
      name: `Live Call Character ${timestamp}`,
      description: 'Live OMEN-PC call acceptance fixture.',
      personality: 'Concise, stable, and direct.',
      scenario: 'A live LAN call acceptance check.',
      first_mes: 'Ready for live call acceptance.',
      mes_example: '<START>\n{{char}}: Ready.',
      system_prompt: 'Reply in one short sentence for live call acceptance.',
      creator_notes: 'Created by live-call.spec.ts.',
      character_notes: 'Live call fixture.',
      tags: ['phase-03', 'live-call'],
      alternate_greetings: [],
      post_history_instructions: 'Keep replies short.',
      creator: 'RayMe',
      character_version: '1.0',
      default_voice_id: voice.voice_id
    }
  });
  expect(characterResponse.ok(), 'create live call character').toBe(true);
  const character = await characterResponse.json();
  expect(character.id, 'live call character id').toBeTruthy();

  const threadResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/threads`, {
    data: {
      character_id: character.id,
      title: `Live Call Thread ${timestamp}`
    }
  });
  expect(threadResponse.ok(), 'create live call thread').toBe(true);
  const thread = await threadResponse.json();
  expect(thread.thread_id, 'live call thread id').toBeTruthy();

  return {
    voiceId: String(voice.voice_id),
    characterId: String(character.id),
    threadId: String(thread.thread_id)
  };
}

async function transcriptTurnCount(page: Page, type: string) {
  return page.locator(`section[aria-label="Call transcript"] article[data-turn-type="${type}"]`).count();
}

async function threadRowCount(page: Page, kind: string) {
  return page.locator(`[data-message-kind="${kind}"]`).count();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function parsePositiveInt(value: string | undefined) {
  const parsed = Number.parseInt(value ?? '0', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}
