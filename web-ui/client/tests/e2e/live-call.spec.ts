import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

import { expect, test, type APIRequestContext, type Page, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';
const canonicalLiveWebRtcStatusUrl = 'https://192.168.1.199:9443/webrtc/status';
const qwenEngineId = 'qwen3_1_7b';
const qwenLanScope = 'rayme_lan_call_testing';
const generatedNonPersonBasis = 'generated_non_person_fixture';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;
const liveReferenceAudioFile = process.env.RAYME_LIVE_REFERENCE_AUDIO_FILE;
const liveFakeAudioFile = process.env.RAYME_LIVE_FAKE_AUDIO_FILE;
const liveReferenceTranscriptFile = process.env.RAYME_LIVE_REFERENCE_TRANSCRIPT_FILE;
const liveReferenceProvenanceFile = process.env.RAYME_LIVE_REFERENCE_PROVENANCE_FILE;
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
      `--use-file-for-fake-audio-capture=${liveFakeAudioFile ?? ''}`
    ]
  }
});

// The live suite mutates one OMEN runtime and exercises one GPU-backed call path.
test.describe.configure({ mode: 'serial' });

test('Qwen live fixture provenance fails closed and permits only hash-bound LAN scope', () => {
  const referenceAudio = Buffer.from('deterministic non-person reference audio');
  const transcriptBytes = Buffer.from('Deterministic non-person transcript.');
  const permitted = {
    voice_data_steward: 'rayme_sapi_fixture_steward',
    authorization_basis: generatedNonPersonBasis,
    use_scope: qwenLanScope,
    reference_sha256: sha256(referenceAudio),
    transcript_sha256: sha256(transcriptBytes)
  };

  expect(validateLiveReferenceProvenance(permitted, referenceAudio, transcriptBytes)).toEqual(
    permitted
  );
  expect(() => validateLiveReferenceProvenance(null, referenceAudio, transcriptBytes)).toThrow(
    'must be an object'
  );
  expect(() =>
    validateLiveReferenceProvenance(
      { ...permitted, reference_sha256: '0'.repeat(64) },
      referenceAudio,
      transcriptBytes
    )
  ).toThrow('audio hash does not match');
  expect(() =>
    validateLiveReferenceProvenance(
      { ...permitted, transcript_sha256: '0'.repeat(64) },
      referenceAudio,
      transcriptBytes
    )
  ).toThrow('transcript hash does not match');
  expect(() =>
    validateLiveReferenceProvenance(
      { ...permitted, use_scope: 'public_impersonation' },
      referenceAudio,
      transcriptBytes
    )
  ).toThrow('use scope is not permitted');
  expect(() =>
    validateLiveReferenceProvenance(
      { ...permitted, authorization_basis: 'product_owner_listening' },
      referenceAudio,
      transcriptBytes
    )
  ).toThrow('is not speaker authorization');
  expect(() =>
    validateLiveReferenceProvenance(
      { ...permitted, permission_confirmed: true },
      referenceAudio,
      transcriptBytes
    )
  ).toThrow('must not fabricate permission_confirmed');
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
        !liveReferenceProvenanceFile ||
        !liveExpectedCommit,
      'Set RAYME_ENABLE_LIVE_E2E=1 plus canonical web/health URLs, expected commit, permitted reference/fake-mic files, and explicit transcript/provenance files to run live call acceptance.'
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

    await page.goto(`${canonicalLiveWebUrl}/call/${encodeURIComponent(fixture.threadId)}`);
    await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible({
      timeout: 60_000
    });
    const startPayload = (await startResponsePromise).json();
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
    const returnToThreadButton = page.locator('button', { hasText: 'Return to Thread' });
    await expect(returnToThreadButton).toBeVisible({ timeout: 60_000 });
    await returnToThreadButton.click();
    await expect(page).toHaveURL(new RegExp(`/chat/${escapeRegExp(fixture.threadId)}$`), { timeout: 60_000 });
    await expect.poll(() => threadRowCount(page, 'call_start'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => threadRowCount(page, 'user_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
    await expect.poll(() => threadRowCount(page, 'ai_speech'), { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
    await expect.poll(() => threadRowCount(page, 'call_end'), { timeout: 60_000 }).toBeGreaterThanOrEqual(1);

    const started = await startPayload;
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
    ...(liveTtsEngine === qwenEngineId
      ? {
          voice_data_steward: fixture.provenance.voice_data_steward,
          authorization_basis: fixture.provenance.authorization_basis,
          use_scope: fixture.provenance.use_scope
        }
      : {}),
    metadata
  };
  expect(Object.prototype.hasOwnProperty.call(voicePayload, 'permission_confirmed')).toBe(false);
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

type LiveReferenceProvenance = {
  voice_data_steward: string;
  authorization_basis: string;
  use_scope: typeof qwenLanScope;
  reference_sha256: string;
  transcript_sha256: string;
};

function loadLiveReferenceFixture(): {
  referenceAudio: Buffer;
  referenceTranscript: string;
  provenance: LiveReferenceProvenance;
} {
  expect(liveReferenceAudioFile, 'live reference audio fixture').toBeTruthy();
  expect(liveReferenceTranscriptFile, 'live reference transcript fixture').toBeTruthy();
  expect(liveReferenceProvenanceFile, 'live reference provenance fixture').toBeTruthy();

  const referenceAudio = readFileSync(liveReferenceAudioFile!);
  const transcriptBytes = readFileSync(liveReferenceTranscriptFile!);
  const referenceTranscript = transcriptBytes.toString('utf8');
  if (!referenceTranscript.trim()) {
    throw new Error('Live reference transcript fixture must be nonblank');
  }

  let rawProvenance: unknown;
  try {
    rawProvenance = JSON.parse(readFileSync(liveReferenceProvenanceFile!, 'utf8'));
  } catch {
    throw new Error('Live reference provenance fixture must be valid JSON');
  }
  const provenance = validateLiveReferenceProvenance(
    rawProvenance,
    referenceAudio,
    transcriptBytes
  );

  return {
    referenceAudio,
    referenceTranscript,
    provenance
  };
}

function validateLiveReferenceProvenance(
  rawProvenance: unknown,
  referenceAudio: Buffer,
  transcriptBytes: Buffer
): LiveReferenceProvenance {
  if (!rawProvenance || typeof rawProvenance !== 'object' || Array.isArray(rawProvenance)) {
    throw new Error('Live reference provenance fixture must be an object');
  }
  const record = rawProvenance as Record<string, unknown>;
  if (Object.prototype.hasOwnProperty.call(record, 'permission_confirmed')) {
    throw new Error('Live reference provenance must not fabricate permission_confirmed');
  }

  const voiceDataSteward = requiredProvenanceText(record, 'voice_data_steward');
  const authorizationBasis = requiredProvenanceText(record, 'authorization_basis');
  const useScope = requiredProvenanceText(record, 'use_scope');
  const referenceSha256 = requiredProvenanceText(record, 'reference_sha256');
  const transcriptSha256 = requiredProvenanceText(record, 'transcript_sha256');
  if (useScope !== qwenLanScope) {
    throw new Error('Live reference provenance use scope is not permitted');
  }
  if (
    ['product_owner_direction', 'product_owner_listening'].includes(
      authorizationBasis.toLowerCase()
    )
  ) {
    throw new Error('Product-owner direction or listening is not speaker authorization');
  }
  if (authorizationBasis === generatedNonPersonBasis && !voiceDataSteward) {
    throw new Error('Generated non-person fixture must name its local data steward');
  }
  if (referenceSha256 !== sha256(referenceAudio)) {
    throw new Error('Live reference provenance audio hash does not match fixture');
  }
  if (transcriptSha256 !== sha256(transcriptBytes)) {
    throw new Error('Live reference provenance transcript hash does not match fixture');
  }

  return {
    voice_data_steward: voiceDataSteward,
    authorization_basis: authorizationBasis,
    use_scope: qwenLanScope,
    reference_sha256: referenceSha256,
    transcript_sha256: transcriptSha256
  };
}

function requiredProvenanceText(record: Record<string, unknown>, field: string): string {
  const value = record[field];
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`Live reference provenance requires ${field}`);
  }
  return value.trim();
}

function sha256(value: Buffer): string {
  return createHash('sha256').update(value).digest('hex');
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
