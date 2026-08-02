import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, basename, isAbsolute, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type APIRequestContext, type Page, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';
const canonicalLiveWebRtcStatusUrl = 'https://192.168.1.199:9443/webrtc/status';
const qwenEngineId = 'qwen3_1_7b';
const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');

type ActiveLiveCall = {
  callId: string;
  sessionId: string;
};

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveFakeAudioPeriodSeconds = 30;
const liveFakeAudioRepeatCount = 10;
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;
const liveReferenceAudioFile = resolveLiveFixturePath(
  process.env.RAYME_LIVE_REFERENCE_AUDIO_FILE
);
const liveFakeAudioFile = resolveLiveFixturePath(process.env.RAYME_LIVE_FAKE_AUDIO_FILE);
const liveFakeAudioCaptureFile = liveEnabled
  ? prepareRepeatingLiveFakeAudioFixture(liveFakeAudioFile)
  : liveFakeAudioFile;
const liveReferenceTranscriptFile = resolveLiveFixturePath(
  process.env.RAYME_LIVE_REFERENCE_TRANSCRIPT_FILE
);
const liveExpectedCommit = process.env.RAYME_LIVE_EXPECTED_COMMIT;
const liveStabilityMs = parsePositiveInt(process.env.RAYME_LIVE_STABILITY_MS);
const liveTtsEngines = (process.env.RAYME_LIVE_TTS_ENGINES ?? qwenEngineId)
  .split(',')
  .map((engine) => engine.trim())
  .filter(Boolean);

const localLlmUrl = process.env.RAYME_LIVE_LLM_URL ?? 'http://192.168.1.190:8001/v1';
const localLlmModel = process.env.RAYME_LIVE_LLM_MODEL ?? 'unsloth/Qwen3.5-27B';

for (const engine of liveTtsEngines) {
  if (engine !== 'voxcpm2' && engine !== 'f5' && engine !== qwenEngineId) {
    throw new Error(
      `RAYME_LIVE_TTS_ENGINES only supports voxcpm2, f5, or ${qwenEngineId}, got ${engine}`
    );
  }
}
if (liveEnabled && !liveTtsEngines.includes(qwenEngineId)) {
  throw new Error(`RAYME_LIVE_TTS_ENGINES must include ${qwenEngineId} for Phase 09 acceptance`);
}

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
      `--use-file-for-fake-audio-capture=${liveFakeAudioCaptureFile ?? ''}`
    ]
  }
});

// The live suite mutates one OMEN runtime and exercises one GPU-backed call path.
test.describe.configure({ mode: 'serial' });

test('live fixture paths resolve from the repository root', () => {
  const fixture = '.planning/phase-fixtures/reference.wav';
  expect(resolveLiveFixturePath(fixture)).toBe(resolve(repositoryRoot, fixture));
  expect(resolveLiveFixturePath('/tmp/reference.wav')).toBe('/tmp/reference.wav');
  expect(resolveLiveFixturePath(undefined)).toBeUndefined();
});

test('repeating live fake microphone fixture preserves each speech period', () => {
  const sourceData = Buffer.from([1, 0, 2, 0]);
  const source = Buffer.alloc(44 + sourceData.length);
  source.write('RIFF', 0, 'ascii');
  source.writeUInt32LE(source.length - 8, 4);
  source.write('WAVEfmt ', 8, 'ascii');
  source.writeUInt32LE(16, 16);
  source.writeUInt16LE(1, 20);
  source.writeUInt16LE(1, 22);
  source.writeUInt32LE(2, 24);
  source.writeUInt32LE(4, 28);
  source.writeUInt16LE(2, 32);
  source.writeUInt16LE(16, 34);
  source.write('data', 36, 'ascii');
  source.writeUInt32LE(sourceData.length, 40);
  sourceData.copy(source, 44);

  const repeated = repeatLiveFakeAudioWav(source, 2, 2);

  expect(repeated.readUInt32LE(4)).toBe(repeated.length - 8);
  expect(repeated.readUInt32LE(40)).toBe(16);
  expect(repeated.subarray(44)).toEqual(
    Buffer.from([
      1, 0, 2, 0, 0, 0, 0, 0,
      1, 0, 2, 0, 0, 0, 0, 0
    ])
  );
});

for (const liveTtsEngine of liveTtsEngines) {
  test(`live OMEN-PC browser call completes two user to AI cycles with ${liveTtsEngine}`, async ({
    page,
    request: apiRequest
  }) => {
    test.skip(
      !liveEnabled ||
        !liveWebUrl ||
        !liveAiHealthUrl ||
        !liveReferenceAudioFile ||
        !liveFakeAudioFile ||
        !liveReferenceTranscriptFile ||
        !liveExpectedCommit,
      'Set RAYME_ENABLE_LIVE_E2E=1 plus canonical web/health URLs, expected commit, reference/fake-mic files, and an explicit transcript file to run live call acceptance.'
    );
    test.info().annotations.push({ type: 'environment', description: 'environment=deployed_live' });
    test.setTimeout(600_000 + liveStabilityMs);
    expect(liveWebUrl).toBe(canonicalLiveWebUrl);
    expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);
    expect(liveExpectedCommit).toMatch(/^[0-9a-f]{40}$/);

    const assertNoBrowserErrors = installBrowserErrorGuard(page, {
      allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
    });
    const liveEvents: string[] = [];
    const liveSignals = {
      aiAudioStartedTurnIds: new Set<string>(),
      aiDoneEvents: 0
    };

    page.on('request', (request) => {
      expectRayMeApiRequest(request);
      recordLiveCallRequest(request, liveEvents);
      recordLiveCallSignal(request, liveSignals);
    });

    await assertLiveDeployment(apiRequest);

    await configureLiveSettings(apiRequest, liveTtsEngine);
    const fixture = await createLiveCallFixture(apiRequest, liveTtsEngine);

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

    let activeLiveCall: ActiveLiveCall | null = null;
    let callEnded = false;
    let primaryFailure: unknown = null;
    try {
      await page.goto(`${canonicalLiveWebUrl}/call/${encodeURIComponent(fixture.threadId)}`);
      const startPayload = await (await startResponsePromise).json();
      const startedCallId = String(startPayload.call_id ?? '');
      const startedSessionId = String(startPayload.session_id ?? '');
      expect(startedCallId, 'live call id').toBeTruthy();
      expect(startedSessionId, 'live call session id').toBeTruthy();
      activeLiveCall = { callId: startedCallId, sessionId: startedSessionId };
      await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible({
        timeout: 60_000
      });
      const offerPayload = await (await offerResponsePromise).json();
      if (liveTtsEngine === qwenEngineId) {
        expect(offerPayload.preparation).toMatchObject({
          model: { state: 'resident', engine_id: qwenEngineId },
          prompt: { state: 'ready' }
        });
        await expect
          .poll(() => readQwenReadiness(apiRequest), { timeout: 60_000 })
          .toEqual({ residentEngine: qwenEngineId, promptEngine: qwenEngineId, promptState: 'ready' });
      }

      await page.getByRole('button', { name: 'Mute' }).click();
      await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(5_000);
      await page.getByRole('button', { name: 'Unmute' }).click();
      await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible({ timeout: 30_000 });

      // The generated capture file repeats the supplied utterance at bounded
      // intervals. Do not credit a later utterance until the first turn has
      // reached the normal terminal: otherwise a broken TTS final marker or
      // Listening recovery could be hidden by audio arriving while speaking.
      await expect
        .poll(
          async () => ({
            firstUserFinalized: (await transcriptTurnCount(page, 'user_speech')) >= 1,
            firstPlaybackStarted: liveSignals.aiAudioStartedTurnIds.size >= 1,
            firstPlaybackCompleted: liveSignals.aiDoneEvents >= 1
          }),
          { timeout: 180_000 }
        )
        .toEqual({ firstUserFinalized: true, firstPlaybackStarted: true, firstPlaybackCompleted: true });
      await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible({
        timeout: 30_000
      });

      await expect.poll(() => transcriptTurnCount(page, 'user_speech'), { timeout: 240_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(() => transcriptTurnCount(page, 'ai_speech'), { timeout: 300_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(() => liveSignals.aiAudioStartedTurnIds.size, { timeout: 300_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(() => liveSignals.aiDoneEvents, { timeout: 300_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(
        () => persistedThreadRowCount(apiRequest, fixture.threadId, 'ai_speech'),
        { timeout: 300_000 }
      ).toBeGreaterThanOrEqual(2);

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

      const endResponsePromise = page.waitForResponse(
        (response) =>
          /\/api\/calls\/[^/]+\/end$/.test(new URL(response.url()).pathname) &&
          response.request().method() === 'POST' &&
          response.ok(),
        { timeout: 60_000 }
      );
      await page.getByRole('button', { name: 'End Call' }).click();
      await endResponsePromise;
      callEnded = true;
      const returnToThreadButton = page.locator('button', { hasText: 'Return to Thread' });
      await expect(returnToThreadButton).toBeVisible({ timeout: 60_000 });
      await returnToThreadButton.click();
      await expect(page).toHaveURL(new RegExp(`/chat/${escapeRegExp(fixture.threadId)}$`), { timeout: 60_000 });
      await expect.poll(() => threadRowCount(page, 'call_start'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
      await expect.poll(() => threadRowCount(page, 'user_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(() => threadRowCount(page, 'ai_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
      await expect.poll(() => threadRowCount(page, 'call_end'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);

      const started = startPayload;
      expect(started.session_id || started.call_id, 'live call session id').toBeTruthy();
      if (liveTtsEngine === qwenEngineId) {
        expect(started.engine_id).toBe(qwenEngineId);
        expect(started.voice_id).toBe(fixture.voiceId);
      }
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
    } catch (error) {
      primaryFailure = error;
      throw error;
    } finally {
      if (activeLiveCall && !callEnded) {
        try {
          await endLiveCallAfterFailure(apiRequest, activeLiveCall);
        } catch (cleanupError) {
          console.error('[live-call-cleanup] failed to end active call', cleanupError);
          if (!primaryFailure) {
            throw cleanupError;
          }
        }
      }
    }
  });
}

function recordLiveCallRequest(request: Request, events: string[]) {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/calls') || url.pathname.startsWith('/webrtc')) {
    events.push(`${request.method()} ${url.pathname}`);
  }
}

function recordLiveCallSignal(
  request: Request,
  signals: { aiAudioStartedTurnIds: Set<string>; aiDoneEvents: number }
) {
  const url = new URL(request.url());
  if (!url.pathname.endsWith('/_debug/event') || request.method() !== 'POST') {
    return;
  }

  let payload: unknown;
  try {
    payload = request.postDataJSON();
  } catch {
    return;
  }

  if (!payload || typeof payload !== 'object') {
    return;
  }
  const eventPayload = payload as { event?: unknown; detail?: unknown };
  if (eventPayload.event === 'call.ai_audio_started') {
    const detail = eventPayload.detail as { turn_id?: unknown } | null;
    const turnId = typeof detail?.turn_id === 'string' ? detail.turn_id : '';
    if (turnId) {
      signals.aiAudioStartedTurnIds.add(turnId);
    }
    return;
  }

  if (eventPayload.event === 'datachannel.message') {
    const detail = eventPayload.detail as { event_type?: unknown } | null;
    if (detail?.event_type === 'ai_done') {
      signals.aiDoneEvents += 1;
    }
  }
}

async function configureLiveSettings(apiRequest: APIRequestContext, liveTtsEngine: string) {
  const response = await apiRequest.patch(`${canonicalLiveWebUrl}/api/settings`, {
    data: {
      web_url: canonicalLiveWebUrl,
      ai_backend_url: 'https://192.168.1.199:9443',
      llm_base_url: localLlmUrl,
      llm_model: localLlmModel,
      llm_api_key: '',
      tts_default_engine: liveTtsEngine
    }
  });
  expect(response.ok(), 'configure live endpoint settings').toBe(true);
}

async function endLiveCallAfterFailure(
  apiRequest: APIRequestContext,
  activeCall: ActiveLiveCall
) {
  const response = await apiRequest.post(
    `${canonicalLiveWebUrl}/api/calls/${encodeURIComponent(activeCall.callId)}/end`,
    {
      data: { session_id: activeCall.sessionId, reason: 'live_e2e_failure_cleanup' },
      timeout: 30_000
    }
  );
  if (!response.ok()) {
    throw new Error(`live call cleanup returned HTTP ${response.status()}`);
  }
}

async function createLiveCallFixture(apiRequest: APIRequestContext, liveTtsEngine: string) {
  expect(liveReferenceAudioFile, 'live reference audio fixture').toBeTruthy();
  const fixture = loadLiveReferenceFixture();
  const timestamp = Date.now();
  const metadata = liveTtsEngine === 'voxcpm2' ? { engine_settings: { voxcpm2: { cloning_mode: 'reference_only', style_prompt: '', cfg_value: 2.0, inference_timesteps: 10, normalize: false, denoise: false } } } : {};

  const assetResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/voices/assets`, {
    multipart: {
      file: {
        name: basename(liveReferenceAudioFile!),
        mimeType: 'audio/wav',
        buffer: fixture.referenceAudio
      }
    }
  });
  expect(assetResponse.ok(), 'upload live reference voice asset').toBe(true);
  const asset = await assetResponse.json();
  expect(asset.asset_id, 'live reference voice asset id').toBeTruthy();

  const voicePayload = {
    asset_id: asset.asset_id,
    name: `Live Call Voice ${timestamp}`,
    default_engine: liveTtsEngine,
    reference_transcript: fixture.referenceTranscript,
    metadata
  };
  const voiceResponse = await apiRequest.post(`${canonicalLiveWebUrl}/api/voices`, {
    data: voicePayload
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
      tags: ['phase-09', 'live-call', liveTtsEngine],
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

function resolveLiveFixturePath(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  return isAbsolute(value) ? value : resolve(repositoryRoot, value);
}

function prepareRepeatingLiveFakeAudioFixture(sourcePath: string | undefined): string | undefined {
  if (!sourcePath) {
    return undefined;
  }

  const outputDirectory = resolve(repositoryRoot, 'web-ui/client/test-results/.live-call-fixtures');
  const outputPath = resolve(outputDirectory, `${basename(sourcePath, '.wav')}.repeating.wav`);
  const temporaryPath = `${outputPath}.${process.pid}.${Date.now()}.tmp`;
  const repeated = repeatLiveFakeAudioWav(
    readFileSync(sourcePath),
    liveFakeAudioRepeatCount,
    liveFakeAudioPeriodSeconds
  );

  mkdirSync(outputDirectory, { recursive: true });
  writeFileSync(temporaryPath, repeated);
  renameSync(temporaryPath, outputPath);
  return outputPath;
}

function repeatLiveFakeAudioWav(
  wav: Buffer,
  repeatCount: number,
  periodSeconds: number
): Buffer {
  if (!Number.isInteger(repeatCount) || repeatCount < 2) {
    throw new Error('Live fake microphone repeat count must be at least two');
  }
  if (!Number.isFinite(periodSeconds) || periodSeconds <= 0) {
    throw new Error('Live fake microphone period must be positive');
  }
  if (
    wav.length < 12 ||
    wav.toString('ascii', 0, 4) !== 'RIFF' ||
    wav.toString('ascii', 8, 12) !== 'WAVE'
  ) {
    throw new Error('Live fake microphone fixture must be a RIFF/WAVE file');
  }

  let cursor = 12;
  let byteRate: number | undefined;
  let blockAlign: number | undefined;
  let dataOffset: number | undefined;
  let dataLength: number | undefined;
  let dataSizeOffset: number | undefined;

  while (cursor + 8 <= wav.length) {
    const chunkId = wav.toString('ascii', cursor, cursor + 4);
    const chunkLength = wav.readUInt32LE(cursor + 4);
    const chunkOffset = cursor + 8;
    const chunkEnd = chunkOffset + chunkLength;
    if (chunkEnd > wav.length) {
      throw new Error('Live fake microphone fixture has a truncated WAV chunk');
    }
    if (chunkId === 'fmt ') {
      if (chunkLength < 16) {
        throw new Error('Live fake microphone fixture has an invalid WAV format chunk');
      }
      byteRate = wav.readUInt32LE(chunkOffset + 8);
      blockAlign = wav.readUInt16LE(chunkOffset + 12);
    } else if (chunkId === 'data' && dataOffset === undefined) {
      dataOffset = chunkOffset;
      dataLength = chunkLength;
      dataSizeOffset = cursor + 4;
    }
    cursor = chunkEnd + (chunkLength % 2);
  }

  if (
    !byteRate ||
    !blockAlign ||
    dataOffset === undefined ||
    dataLength === undefined ||
    dataSizeOffset === undefined ||
    dataLength === 0 ||
    dataLength % blockAlign !== 0
  ) {
    throw new Error('Live fake microphone fixture must contain aligned PCM audio data');
  }

  const periodBytes = Math.max(
    dataLength,
    Math.ceil((byteRate * periodSeconds) / blockAlign) * blockAlign
  );
  const repeatedData = Buffer.alloc(periodBytes * repeatCount);
  for (let index = 0; index < repeatCount; index += 1) {
    wav.copy(repeatedData, index * periodBytes, dataOffset, dataOffset + dataLength);
  }

  const header = Buffer.from(wav.subarray(0, dataOffset));
  header.writeUInt32LE(repeatedData.length, dataSizeOffset);
  header.writeUInt32LE(header.length + repeatedData.length - 8, 4);
  return Buffer.concat([header, repeatedData]);
}

function loadLiveReferenceFixture(): {
  referenceAudio: Buffer;
  referenceTranscript: string;
} {
  expect(liveReferenceAudioFile, 'live reference audio fixture').toBeTruthy();
  expect(liveReferenceTranscriptFile, 'live reference transcript fixture').toBeTruthy();

  const referenceAudio = readFileSync(liveReferenceAudioFile!);
  const referenceTranscript = readFileSync(liveReferenceTranscriptFile!, 'utf8');
  if (!referenceTranscript.trim()) {
    throw new Error('Live reference transcript fixture must be nonblank');
  }

  return {
    referenceAudio,
    referenceTranscript
  };
}

async function assertLiveDeployment(apiRequest: APIRequestContext) {
  const healthResponse = await apiRequest.get(canonicalLiveAiHealthUrl);
  expect(healthResponse.ok(), `AI backend health at ${canonicalLiveAiHealthUrl}`).toBe(true);
  const health = (await healthResponse.json()) as Record<string, unknown>;
  expect(health).toMatchObject({ phase: expect.any(String) });

  const statusResponse = await apiRequest.get(canonicalLiveWebRtcStatusUrl);
  expect(statusResponse.ok(), `WebRTC status at ${canonicalLiveWebRtcStatusUrl}`).toBe(true);
  const status = (await statusResponse.json()) as Record<string, unknown>;
  expect(status).toMatchObject({
    status: 'ready',
    live_call_ready: true,
    media_transport_ready: true,
    deployed_commit: liveExpectedCommit
  });
  const healthCommit = typeof health.deployed_commit === 'string' ? health.deployed_commit : null;
  if (healthCommit) {
    expect(healthCommit).toBe(liveExpectedCommit);
  }
}

async function readQwenReadiness(apiRequest: APIRequestContext) {
  const response = await apiRequest.get(canonicalLiveWebRtcStatusUrl);
  if (!response.ok()) {
    return { residentEngine: null, promptEngine: null, promptState: 'unavailable' };
  }
  const status = (await response.json()) as {
    tts_model?: { resident_engine?: unknown };
    selected_voice_prompt?: { engine_id?: unknown; state?: unknown };
  };
  return {
    residentEngine: status.tts_model?.resident_engine ?? null,
    promptEngine: status.selected_voice_prompt?.engine_id ?? null,
    promptState: status.selected_voice_prompt?.state ?? null
  };
}

async function transcriptTurnCount(page: Page, type: string) {
  return page.locator(`section[aria-label="Call transcript"] article[data-turn-type="${type}"]`).count();
}

async function threadRowCount(page: Page, kind: string) {
  return page.locator(`[data-message-kind="${kind}"]`).count();
}

async function persistedThreadRowCount(apiRequest: APIRequestContext, threadId: string, kind: string) {
  const response = await apiRequest.get(`${canonicalLiveWebUrl}/api/threads/${encodeURIComponent(threadId)}`);
  if (!response.ok()) {
    return 0;
  }
  const thread = await response.json();
  const messages = Array.isArray(thread.messages) ? thread.messages : [];
  return messages.filter((message: { message_kind?: string }) => message.message_kind === kind).length;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function parsePositiveInt(value: string | undefined) {
  const parsed = Number.parseInt(value ?? '0', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}
