import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard, installCallDebugEventRoute, installMockCallMedia } from './helpers/acceptance';
import { makeCharacter, makeThreadDetail } from './helpers/fixtures';

const characterId = 'call-start-character';
const threadId = 'call-start-thread';
const MEDIA_RECONNECT_MAX_ATTEMPTS = 2;
const MIC_BACKFILL_ROLLING_MS = 180000;
const TERMINAL_CONNECTION_DROPPED_COPY =
  'The call ended because the connection dropped. Your transcript so far was saved.';

type ReconnectRouteCounters = {
  offerCount: number;
  backfillCount: number;
  recoverCount: number;
  turnCount: number;
  endCount: number;
  muteCount: number;
  peerPromotionCount: number;
  backendActivePeerId: number | null;
  backendActivePeerGeneration: number | null;
  backendOldPeerRetirementCount: number;
  abortedPeerCommitResponses: number;
  peerPromotionInProgressCount: number;
  backendVoiceId: string;
  backendEngineId: string;
  backendPromptLeaseOwner: string | null;
  backendPromptLeaseReleaseCount: number;
  offers: Array<{ peerId: number | null; sdp: string }>;
  backfills: Array<Record<string, unknown>>;
  recoveredEvents: Array<Record<string, unknown>>;
  turns: Array<Record<string, unknown>>;
  muteRequests: Array<Record<string, unknown>>;
  peerPromotions: Array<{
    session_id: string;
    generation: number;
    action: 'commit' | 'reject';
  }>;
  requestOrder: string[];
  debugEvents: Array<{ event: string; detail: Record<string, unknown>; session_id?: string }>;
};

type ReconnectRouteOptions = {
  backfillDelayMs?: number;
  firstBackfillGate?: Promise<void>;
  finalBackfillGate?: Promise<void>;
  firstMuteGate?: Promise<void>;
  muteGate?: Promise<void>;
  abortMuteNumbers?: number[];
  authoritativeMuteEpoch?: number;
  failBackfill?: boolean;
  hangBackfillFrom?: number;
  recoverEvents?: Array<Record<string, unknown>>;
  offerDelayMs?: number;
  failOfferNumbers?: number[];
  failOfferFrom?: number;
  turnStreamGate?: Promise<void>;
  turnStreamEvents?: Array<Record<string, unknown>>;
  abortFirstPeerCommitResponse?: boolean;
  reconcileCommittedAsConflict?: boolean;
  selectionChangingPeerCommitDelayMs?: number;
  selectionChangingPeerCommitGate?: Promise<void>;
};

type StartupRouteCounters = {
  startCount: number;
  offerCount: number;
  endCount: number;
  requestOrder: string[];
};

type CallStartRouteOptions = {
  failOffer?: boolean;
  offerGate?: Promise<void>;
  qwenPreparation?: boolean;
  qwenPromptState?: 'ready' | 'failed';
};

type MockCallMediaSnapshot = {
  peers: Array<{
    id: number;
    connectionState: RTCPeerConnectionState;
    iceConnectionState: RTCIceConnectionState;
    createdOfferCount: number;
    closed: boolean;
    closeCount: number;
    localDescriptionType: string | null;
    remoteDescriptionType: string | null;
    dataChannelIds: number[];
    remoteStreamId: string | null;
  }>;
  channels: Array<{
    id: number;
    label: string;
    ownerPeerId: number;
    readyState: RTCDataChannelState;
    closeCount: number;
    sentMessages: string[];
  }>;
  remoteStreams: Array<{ id: string; audioTracks: number }>;
  audioPlayback: {
    activeStreamId: string | null;
    playedStreamIds: string[];
    pausedStreamIds: string[];
  };
};

test('starts a call from the thread header Start call control', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installCallStartRoutes(page);

  await page.goto(`/chat/${threadId}`);

  await expect(page.getByRole('heading', { name: 'Call Start Aster' })).toBeVisible();
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'End Call' })).toBeVisible();
  assertNoBrowserErrors();
});

test('keeps startup in Connecting until microphone access and WebRTC offer complete', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  let resolveOffer: () => void = () => {};
  const offerGate = new Promise<void>((resolve) => {
    resolveOffer = resolve;
  });
  const counters = await installCallStartRoutes(page, { offerGate });

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect.poll(() => counters.startCount).toBe(1);
  await expect.poll(() => counters.offerCount).toBe(1);
  expect(counters.requestOrder).toEqual(['start', 'offer']);
  await expect(page.getByRole('status').getByText('Connecting')).toBeVisible();
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);

  resolveOffer();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('keeps a Qwen call in Preparing voice until model and saved prompt are authoritative', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  let resolveOffer: () => void = () => {};
  const offerGate = new Promise<void>((resolve) => {
    resolveOffer = resolve;
  });
  const counters = await installCallStartRoutes(page, { qwenPreparation: true, offerGate });

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect.poll(() => counters.offerCount).toBe(1);
  const preparationPanel = page.getByRole('status').filter({ hasText: 'Preparing voice' });
  await expect(preparationPanel.getByRole('heading', { name: 'Preparing voice' })).toBeVisible();
  await expect(preparationPanel).toContainText('Loading Qwen3-TTS 1.7B…');
  await expect(preparationPanel).toContainText('Preparing Call Start Voice…');
  await expect(page.getByText('Listening', { exact: true })).toHaveCount(0);
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'End Call' })).toHaveCount(0);

  resolveOffer();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('focuses a fixed Qwen preparation failure without exposing backend detail', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installCallStartRoutes(page, {
    qwenPreparation: true,
    qwenPromptState: 'failed'
  });

  await page.goto(`/call/${threadId}`);
  await expect.poll(() => counters.offerCount).toBe(1);

  const failure = page.getByRole('alert');
  await expect(failure.getByRole('heading', { name: 'Voice preparation failed' })).toBeFocused();
  await expect(failure).toContainText(
    'RayMe could not prepare this voice for the call. Retry preparation, choose another voice, or check Settings.'
  );
  await expect(failure.getByRole('button', { name: 'Retry Preparation' })).toBeVisible();
  await expect(page.getByText(/private|traceback|worker|cache path/i)).toHaveCount(0);
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);
  assertNoBrowserErrors();
});

test('ends startup and shows sanitized failure when backend offer forwarding fails', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  await installMockCallMedia(page);
  await installCallStartRoutes(page, { failOffer: true });

  await page.goto(`/chat/${threadId}`);
  const failedOffer = page.waitForResponse(
    (response) => response.url().includes('/api/calls/') && response.url().endsWith('/offer')
  );
  await page.getByRole('button', { name: 'Start call' }).click();
  await expect((await failedOffer).status()).toBe(502);

  await expect(page.getByText('WebRTC offer could not be accepted')).toBeVisible();
  await expect(page.getByRole('alert').getByRole('button', { name: 'Return to Thread' })).toBeVisible();
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);
  assertNoBrowserErrors();
});

test('starts a call from a character card Start Call control', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installCallStartRoutes(page);

  await page.goto('/gallery');

  const card = page.getByTestId(`character-card-${characterId}`);
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Start Call' }).click();

  await expect(page).toHaveURL(new RegExp(`/call/${threadId}`));
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('streams two user to AI cycles in one call and reaches the ended state', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installMultiTurnCallRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByText('First user turn.')).toBeVisible();
  await expect(page.getByText('First AI answer.')).toBeVisible();
  await expect(page.getByText('Second user turn.')).toBeVisible();
  await expect(page.getByText('Second AI answer.')).toBeVisible();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();

  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('status').getByRole('button', { name: 'Return to Thread' })).toBeVisible();
  assertNoBrowserErrors();
});

test('does not revive an ended call when a late data channel state event arrives', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installCallStartRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();

  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('status').getByText('Call ended')).toBeVisible();
  await expect.poll(() => counters.endCount).toBe(1);

  await emitLatestMockDataChannelEvent(page, {
    type: 'state',
    session_id: 'rtc-call-start-01',
    state: 'listening'
  });

  await expect(page.getByRole('status').getByText('Call ended')).toBeVisible();
  await expect(page.getByRole('button', { name: 'End Call' })).toHaveCount(0);
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);
  assertNoBrowserErrors();
});

test('re-offers with a new peer instead of ending when browser peer connection fails', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  const beforeFailure = await getMockCallMediaSnapshot(page);
  expect(beforeFailure.peers).toHaveLength(1);
  expect(beforeFailure.channels).toHaveLength(1);
  expect(beforeFailure.remoteStreams).toHaveLength(1);

  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'pc.setRemoteDescription.done')).toBe(2);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();

  const afterReconnect = await getMockCallMediaSnapshot(page);
  expect(afterReconnect.peers).toHaveLength(2);
  expect(counters.offers.map((offer) => offer.peerId)).toEqual([
    afterReconnect.peers[0].id,
    afterReconnect.peers[1].id
  ]);
  expect(afterReconnect.peers[0]).toMatchObject({
    closed: true,
    createdOfferCount: 1
  });
  expect(afterReconnect.peers[1]).toMatchObject({
    closed: false,
    createdOfferCount: 1,
    localDescriptionType: 'offer',
    remoteDescriptionType: 'answer'
  });
  expect(afterReconnect.channels).toHaveLength(2);
  expect(afterReconnect.channels[0]).toMatchObject({
    ownerPeerId: afterReconnect.peers[0].id,
    readyState: 'closed',
    closeCount: 1
  });
  expect(afterReconnect.channels[1]).toMatchObject({
    ownerPeerId: afterReconnect.peers[1].id,
    readyState: 'open',
    closeCount: 0
  });
  expect(afterReconnect.remoteStreams).toHaveLength(2);
  expect(debugEventCount(counters, 'datachannel.attach')).toBe(2);
  // Closing the retired owner's channel must not publish current-owner diagnostics.
  expect(debugEventCount(counters, 'datachannel.close')).toBe(0);
  expect(debugEventCount(counters, 'remote_audio.attach')).toBe(2);
  await expect.poll(
    () =>
      counters.debugEvents.filter(
        (entry) => entry.event === 'mic.reconnect_diag' && entry.detail.phase === 'ok'
      ).length
  ).toBeGreaterThan(0);
  const micReconnectDiagPhases = counters.debugEvents
    .filter((entry) => entry.event === 'mic.reconnect_diag')
    .map((entry) => entry.detail.phase);
  expect(micReconnectDiagPhases).toContain('scheduled');
  expect(micReconnectDiagPhases).toContain('start');
  expect(micReconnectDiagPhases).toContain('ok');
  assertNoBrowserErrors();
});

test('keeps old audio live while a slow replacement stream stages, then promotes atomically', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page, { deferReplacementConnection: true });
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  const initial = await getMockCallMediaSnapshot(page);
  const initialStreamId = initial.peers[0].remoteStreamId;
  expect(initialStreamId).not.toBeNull();
  expect(initial.audioPlayback.activeStreamId).toBe(initialStreamId);

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'remote_audio.candidate.staged')).toBe(1);

  const staged = await getMockCallMediaSnapshot(page);
  const candidateStreamId = staged.peers[1].remoteStreamId;
  expect(candidateStreamId).not.toBeNull();
  expect(staged.peers[0].closed).toBe(false);
  expect(staged.peers[1]).toMatchObject({
    connectionState: 'new',
    iceConnectionState: 'new',
    closed: false
  });
  expect(staged.audioPlayback.activeStreamId).toBe(initialStreamId);
  expect(staged.audioPlayback.pausedStreamIds).not.toContain(initialStreamId);
  expect(debugEventCount(counters, 'remote_audio.attach')).toBe(1);
  expect(counters.backendActivePeerId).toBe(staged.peers[0].id);
  expect(counters.peerPromotions).toEqual([]);

  await completeCurrentMockPeerConnection(page);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);

  const promoted = await getMockCallMediaSnapshot(page);
  expect(promoted.peers[0].closed).toBe(true);
  expect(promoted.peers[1]).toMatchObject({
    connectionState: 'connected',
    iceConnectionState: 'connected',
    closed: false
  });
  expect(promoted.audioPlayback.activeStreamId).toBe(candidateStreamId);
  expect(promoted.audioPlayback.pausedStreamIds).toContain(initialStreamId);
  expect(debugEventCount(counters, 'remote_audio.attach')).toBe(2);
  expect(debugEventCount(counters, 'remote_audio.candidate.promoted')).toBe(1);
  expect(counters.backendActivePeerId).toBe(promoted.peers[1].id);
  expect(counters.peerPromotions).toEqual([
    {
      session_id: 'rtc-call-reconnect-01',
      generation: 1,
      action: 'commit'
    }
  ]);
  assertNoBrowserErrors();
});

for (const reconciliation of [
  { label: 'duplicate committed response', asConflict: false },
  { label: 'structured already_committed response', asConflict: true }
] as const) {
  test(`reconciles a lost peer commit acknowledgement through a ${reconciliation.label}`, async ({
    page
  }) => {
    const assertNoBrowserErrors = installBrowserErrorGuard(page, {
      allowConsoleErrors: [
        /Failed to load resource: net::ERR_FAILED/,
        /Failed to load resource: the server responded with a status of 502/
      ]
    });
    await installMockCallMedia(page);
    const counters = await installReconnectCallRoutes(page, {
      abortFirstPeerCommitResponse: true,
      reconcileCommittedAsConflict: reconciliation.asConflict
    });

    await startReconnectCall(page, counters);
    const initial = await getMockCallMediaSnapshot(page);
    const initialStreamId = initial.peers[0].remoteStreamId;
    expect(initialStreamId).not.toBeNull();

    await setCurrentMockPeerState(page, 'failed', 'disconnected');
    await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
    await expect.poll(() => debugEventCount(counters, 'remote_audio.candidate.commit_reconciled'))
      .toBe(1);

    const reconciled = await getMockCallMediaSnapshot(page);
    const candidateStreamId = reconciled.peers[1].remoteStreamId;
    expect(candidateStreamId).not.toBeNull();
    expect(counters.peerPromotions).toEqual([
      {
        session_id: 'rtc-call-reconnect-01',
        generation: 1,
        action: 'commit'
      },
      {
        session_id: 'rtc-call-reconnect-01',
        generation: 1,
        action: 'commit'
      }
    ]);
    expect(counters.abortedPeerCommitResponses).toBe(1);
    expect(counters.backendActivePeerGeneration).toBe(1);
    expect(counters.backendActivePeerId).toBe(reconciled.peers[1].id);
    expect(counters.backendOldPeerRetirementCount).toBe(1);
    expect(reconciled.peers[0]).toMatchObject({ closed: true, closeCount: 1 });
    expect(reconciled.peers[1]).toMatchObject({
      connectionState: 'connected',
      iceConnectionState: 'connected',
      closed: false,
      closeCount: 0
    });
    expect(reconciled.audioPlayback.activeStreamId).toBe(candidateStreamId);
    expect(reconciled.audioPlayback.pausedStreamIds).toContain(initialStreamId);
    expect(debugEventCount(counters, 'remote_audio.candidate.promoted')).toBe(1);
    expect(debugEventCount(counters, 'remote_audio.candidate.discarded')).toBe(0);
    expect(debugEventCount(counters, 'pc.media_reconnect.failed')).toBe(0);
    expect(debugEventCount(counters, 'pc.media_reconnect.give_up')).toBe(0);
    expect(counters.endCount).toBe(0);
    await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
    assertNoBrowserErrors();
  });
}

test('reconciles a lost response while a selection-changing peer switch is still in progress', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: net::ERR_FAILED/]
  });
  await installMockCallMedia(page);
  let releaseSelectionSwitch: () => void = () => {};
  const selectionSwitchGate = new Promise<void>((resolve) => {
    releaseSelectionSwitch = resolve;
  });
  const counters = await installReconnectCallRoutes(page, {
    selectionChangingPeerCommitGate: selectionSwitchGate
  });

  await startReconnectCall(page, counters);
  const initial = await getMockCallMediaSnapshot(page);
  const initialStreamId = initial.peers[0].remoteStreamId;
  expect(initialStreamId).not.toBeNull();

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.peerPromotionInProgressCount).toBeGreaterThan(0);

  const switching = await getMockCallMediaSnapshot(page);
  expect(counters.backendVoiceId).toBe('voice-before');
  expect(counters.backendEngineId).toBe('qwen3_1_7b');
  expect(counters.backendPromptLeaseOwner).toBe('rtc-call-reconnect-01');
  expect(counters.backendOldPeerRetirementCount).toBe(0);
  expect(switching.peers[0]).toMatchObject({ closed: false, closeCount: 0 });
  expect(switching.peers[1]).toMatchObject({ closed: false, closeCount: 0 });
  expect(switching.audioPlayback.activeStreamId).toBe(initialStreamId);
  expect(switching.audioPlayback.pausedStreamIds).not.toContain(initialStreamId);

  releaseSelectionSwitch();
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  const reconciled = await getMockCallMediaSnapshot(page);
  const candidateStreamId = reconciled.peers[1].remoteStreamId;
  expect(candidateStreamId).not.toBeNull();
  expect(counters.peerPromotions.length).toBeGreaterThan(2);
  expect(counters.peerPromotions.every((promotion) =>
    promotion.session_id === 'rtc-call-reconnect-01' &&
    promotion.generation === 1 &&
    promotion.action === 'commit'
  )).toBe(true);
  expect(counters.abortedPeerCommitResponses).toBe(1);
  expect(counters.backendActivePeerGeneration).toBe(1);
  expect(counters.backendActivePeerId).toBe(reconciled.peers[1].id);
  expect(counters.backendOldPeerRetirementCount).toBe(1);
  expect(counters.backendVoiceId).toBe('voice-after');
  expect(counters.backendEngineId).toBe('f5');
  expect(counters.backendPromptLeaseOwner).toBeNull();
  expect(counters.backendPromptLeaseReleaseCount).toBe(1);
  expect(reconciled.peers[0]).toMatchObject({ closed: true, closeCount: 1 });
  expect(reconciled.peers[1]).toMatchObject({ closed: false, closeCount: 0 });
  expect(reconciled.audioPlayback.activeStreamId).toBe(candidateStreamId);
  expect(reconciled.audioPlayback.pausedStreamIds).toContain(initialStreamId);
  expect(debugEventCount(counters, 'remote_audio.candidate.promoted')).toBe(1);
  expect(debugEventCount(counters, 'remote_audio.candidate.discarded')).toBe(0);
  expect(debugEventCount(counters, 'pc.media_reconnect.failed')).toBe(0);
  expect(debugEventCount(counters, 'pc.media_reconnect.give_up')).toBe(0);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('discards a failed replacement candidate without touching old audible audio', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page, { failReplacementConnection: true });
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  const initial = await getMockCallMediaSnapshot(page);
  const initialStreamId = initial.peers[0].remoteStreamId;
  expect(initialStreamId).not.toBeNull();
  await page.clock.install();

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await page.clock.fastForward(0);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.failed')).toBe(1);
  await expect.poll(() => debugEventCount(counters, 'remote_audio.candidate.discarded')).toBe(1);

  const rolledBack = await getMockCallMediaSnapshot(page);
  expect(counters.offerCount).toBe(2);
  expect(rolledBack.peers).toHaveLength(2);
  expect(rolledBack.peers[0].closed).toBe(false);
  expect(rolledBack.peers[1].closed).toBe(true);
  expect(rolledBack.audioPlayback.activeStreamId).toBe(initialStreamId);
  expect(rolledBack.audioPlayback.pausedStreamIds).not.toContain(initialStreamId);
  expect(debugEventCount(counters, 'remote_audio.attach')).toBe(1);
  expect(debugEventCount(counters, 'remote_audio.candidate.promoted')).toBe(0);
  expect(counters.backendActivePeerId).toBe(rolledBack.peers[0].id);
  expect(counters.peerPromotions).toEqual([
    {
      session_id: 'rtc-call-reconnect-01',
      generation: 1,
      action: 'reject'
    }
  ]);
  assertNoBrowserErrors();
});

test('keeps old backend and browser media authoritative when connected replacement has no track for seven seconds', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page, { suppressReplacementTrack: true });
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  const initial = await getMockCallMediaSnapshot(page);
  const initialStreamId = initial.peers[0].remoteStreamId;
  expect(initialStreamId).not.toBeNull();
  await page.clock.install();

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(async () => (await getMockCallMediaSnapshot(page)).peers[1]?.connectionState)
    .toBe('connected');
  const connectedWithoutTrack = await getMockCallMediaSnapshot(page);
  expect(connectedWithoutTrack.peers[1].remoteStreamId).toBeNull();
  expect(counters.backendActivePeerId).toBe(connectedWithoutTrack.peers[0].id);
  expect(counters.peerPromotions).toEqual([]);
  expect(connectedWithoutTrack.audioPlayback.activeStreamId).toBe(initialStreamId);

  await page.clock.fastForward(7000);
  await expect.poll(() => debugEventCount(counters, 'remote_audio.candidate.timeout')).toBe(1);
  await expect.poll(() => counters.peerPromotionCount).toBe(1);
  await expect.poll(async () => (await getMockCallMediaSnapshot(page)).peers[1]?.closed)
    .toBe(true);

  const timedOut = await getMockCallMediaSnapshot(page);
  expect(timedOut.peers[0].closed).toBe(false);
  expect(timedOut.peers[1].closed).toBe(true);
  expect(timedOut.audioPlayback.activeStreamId).toBe(initialStreamId);
  expect(timedOut.audioPlayback.pausedStreamIds).not.toContain(initialStreamId);
  expect(counters.backendActivePeerId).toBe(timedOut.peers[0].id);
  expect(counters.peerPromotions).toEqual([
    {
      session_id: 'rtc-call-reconnect-01',
      generation: 1,
      action: 'reject'
    }
  ]);
  expect(debugEventCount(counters, 'remote_audio.candidate.promoted')).toBe(0);
  assertNoBrowserErrors();
});

test('reconnect backfill after mute contains only post-unmute capture epoch PCM', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  await emitMockPcm(page, 1111);

  const muteResponse = page.waitForResponse((response) =>
    response.url().includes('/mute')
  );
  await page.getByRole('button', { name: 'Mute' }).click();
  await muteResponse;
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible();
  await emitMockPcm(page, 2222);

  const unmuteResponse = page.waitForResponse((response) =>
    response.url().includes('/mute')
  );
  await page.getByRole('button', { name: 'Unmute' }).click();
  await unmuteResponse;
  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await emitMockPcm(page, 3333);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.backfillCount).toBeGreaterThan(0);
  expect(counters.backfills.every((entry) => entry.audio_input_epoch === 1)).toBe(true);
  const selectedValues = new Set(
    counters.backfills.flatMap((entry) => decodePcmValues(String(entry.pcm_b64 ?? '')))
  );
  expect(selectedValues.has(3333)).toBe(true);
  expect(selectedValues.has(1111)).toBe(false);
  expect(selectedValues.has(2222)).toBe(false);
  assertNoBrowserErrors();
});

test('retired reconnect generation cannot resume after mute and a newer reconnect', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseRetiredBatch = () => undefined;
  const retiredBatchGate = new Promise<void>((resolve) => {
    releaseRetiredBatch = resolve;
  });
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page, {
    firstBackfillGate: retiredBatchGate
  });

  await startReconnectCall(page, counters);
  await emitMockPcm(page, 1111, 400_000);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.backfillCount).toBe(1);
  const retiredBaseId = String(counters.backfills[0].backfill_id).replace(/-batch-1$/, '');

  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible();
  await page.getByRole('button', { name: 'Unmute' }).click();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await emitMockPcm(page, 3333);

  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  await page.waitForTimeout(100);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.backfillCount).toBeGreaterThan(1);
  const currentBaseId = String(counters.backfills[1].backfill_id).replace(/-batch-1$/, '');
  expect(currentBaseId).not.toBe(retiredBaseId);

  releaseRetiredBatch();
  await page.waitForTimeout(250);

  const retiredBatches = counters.backfills.filter((entry) =>
    String(entry.backfill_id).startsWith(retiredBaseId)
  );
  const currentBatches = counters.backfills.filter((entry) =>
    String(entry.backfill_id).startsWith(currentBaseId)
  );
  expect(retiredBatches).toHaveLength(1);
  expect(retiredBatches[0]).toMatchObject({ batch_index: 1, audio_input_epoch: 0 });
  expect(currentBatches.length).toBeGreaterThan(0);
  expect(currentBatches.every((entry) => entry.audio_input_epoch === 1)).toBe(true);
  expect(
    counters.debugEvents.filter(
      (entry) =>
        entry.event === 'mic.reconnect_backfill.sent' &&
        entry.detail.baseBackfillId === retiredBaseId
    )
  ).toHaveLength(0);
  assertNoBrowserErrors();
});

test('ignores recovery callbacks from the old authoritative peer while replacement commit is pending', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseBackfill: () => void = () => {};
  const backfillGate = new Promise<void>((resolve) => {
    releaseBackfill = resolve;
  });
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page, {
    firstBackfillGate: backfillGate
  });

  await startReconnectCall(page, counters);
  await emitMockPcm(page, 1111, 400_000);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => counters.backfillCount).toBe(1);
  await expect(page.getByTestId('voice-visualizer').getByText('Understanding')).toBeVisible();

  await setMockPeerState(page, 0, 'connected', 'connected');
  await page.waitForTimeout(100);

  await expect(page.getByTestId('voice-visualizer').getByText('Understanding')).toBeVisible();
  expect(
    counters.debugEvents.some(
      (entry) =>
        entry.event === 'pc.media_reconnect.guard_skip' &&
        entry.detail.phase === 'recover' &&
        entry.detail.isCurrentPeer === true &&
        Array.isArray(entry.detail.guardSkips) &&
        entry.detail.guardSkips.includes('replacement_pending')
    )
  ).toBe(true);
  expect(debugEventCount(counters, 'datachannel.recreate')).toBe(0);

  releaseBackfill();
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  assertNoBrowserErrors();
});

test('serializes delayed double-click mute so responses cannot reverse or backfill pending audio', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseMute = () => undefined;
  const muteGate = new Promise<void>((resolve) => {
    releaseMute = resolve;
  });
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page, {
    firstMuteGate: muteGate,
    authoritativeMuteEpoch: 7
  });

  await startReconnectCall(page, counters);
  await emitMockPcm(page, 1111);
  await page.getByRole('button', { name: 'Mute' }).click();
  const pendingControl = page.getByRole('button', { name: 'Unmute' });
  await expect(pendingControl).toBeDisabled();
  await page.evaluate(() => {
    const button = document.querySelector<HTMLButtonElement>('button[aria-label="Unmute"]');
    button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
  await emitMockPcm(page, 2222);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await page.waitForTimeout(200);
  expect(counters.muteCount).toBe(1);
  expect(counters.backfillCount).toBe(0);

  releaseMute();
  await expect(pendingControl).toBeEnabled();
  await pendingControl.click();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeEnabled();
  await emitMockPcm(page, 3333);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.backfillCount).toBeGreaterThan(0);

  expect(counters.muteCount).toBe(2);
  expect(counters.muteRequests.map((entry) => entry.muted)).toEqual([true, false]);
  expect(counters.backfills.every((entry) => entry.audio_input_epoch === 7)).toBe(true);
  const values = new Set(
    counters.backfills.flatMap((entry) => decodePcmValues(String(entry.pcm_b64 ?? '')))
  );
  expect(values.has(3333)).toBe(true);
  expect(values.has(1111)).toBe(false);
  expect(values.has(2222)).toBe(false);
  assertNoBrowserErrors();
});

test('matching mute data acknowledgement settles ownership and aborts the pending HTTP wait', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseMute: () => void = () => {};
  const muteGate = new Promise<void>((resolve) => {
    releaseMute = resolve;
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { firstMuteGate: muteGate });

  await startReconnectCall(page, counters);
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect.poll(() => counters.muteCount).toBe(1);
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);

  await emitLatestMockDataChannelEvent(page, {
    type: 'muted',
    session_id: 'rtc-call-reconnect-01',
    muted: true,
    audio_input_epoch: 1,
    mute_revision: 1
  });

  await expect(page.getByRole('button', { name: 'Unmute' })).toBeEnabled();
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);
  expect(
    counters.debugEvents.some(
      (entry) =>
        entry.event === 'call.mute.acknowledged' &&
        entry.detail.source === 'data-channel'
    )
  ).toBe(true);
  releaseMute();
  assertNoBrowserErrors();
});

test('no mute acknowledgement times out into visible retry and end recovery controls', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseMute: () => void = () => {};
  const muteGate = new Promise<void>((resolve) => {
    releaseMute = resolve;
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { muteGate });

  await startReconnectCall(page, counters);
  await page.getByRole('button', { name: 'Mute' }).click();

  const recovery = page.getByRole('alert');
  await expect(recovery).toContainText('Your microphone is physically off.');
  await expect(recovery.getByRole('button', { name: 'Retry microphone sync' })).toBeEnabled({
    timeout: 5000
  });
  await expect(recovery.getByRole('button', { name: 'End call now' })).toBeEnabled();
  expect(counters.muteCount).toBe(2);
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);
  releaseMute();
  await recovery.getByRole('button', { name: 'Retry microphone sync' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);
  assertNoBrowserErrors();
});

test('lost unmute acknowledgements leave the actual outgoing microphone track disabled', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource/]
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, {
    abortMuteNumbers: [2, 3, 4]
  });

  await startReconnectCall(page, counters);
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeEnabled();
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);

  await page.getByRole('button', { name: 'Unmute' }).click();
  await expect(page.getByRole('alert')).toContainText('Your microphone is physically off.');
  await emitLatestMockDataChannelEvent(page, {
    type: 'state',
    session_id: 'rtc-call-reconnect-01',
    state: 'listening'
  });

  expect(counters.muteRequests.map((entry) => entry.muted)).toEqual([
    true,
    false,
    false,
    true
  ]);
  expect(await getMockLocalAudioTrackStates(page)).toEqual([false]);
  await expect(page.getByRole('button', { name: 'Retry microphone sync' })).toBeEnabled();
  assertNoBrowserErrors();
});

test('recovers an applied mute when its first HTTP response is lost', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource/]
  });
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page, {
    abortMuteNumbers: [1]
  });

  await startReconnectCall(page, counters);
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect.poll(() => counters.muteCount).toBe(2);
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeEnabled();
  expect(counters.muteRequests.map((entry) => entry.muted)).toEqual([true, true]);

  await page.getByRole('button', { name: 'Unmute' }).click();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeEnabled();
  await emitMockPcm(page, 3333);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.backfillCount).toBeGreaterThan(0);

  expect(counters.muteRequests.map((entry) => entry.muted)).toEqual([true, true, false]);
  expect(counters.backfills.every((entry) => entry.audio_input_epoch === 1)).toBe(true);
  assertNoBrowserErrors();
});

test('rejects a stale mute event after a newer unmute revision commits', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeEnabled();
  await page.getByRole('button', { name: 'Unmute' }).click();
  await expect(page.getByRole('button', { name: 'Mute' })).toBeEnabled();

  await emitLatestMockDataChannelEvent(page, {
    type: 'muted',
    session_id: 'rtc-call-reconnect-01',
    muted: true,
    audio_input_epoch: 1,
    mute_revision: 1
  });

  await expect(page.getByRole('button', { name: 'Mute' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Unmute' })).toHaveCount(0);
  expect(counters.muteRequests.map((entry) => entry.muted)).toEqual([true, false]);
  assertNoBrowserErrors();
});

test('retries when the first replacement offer fails during media reconnect', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { failOfferNumbers: [2] });

  await startReconnectCall(page, counters);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.failed')).toBe(1);
  await expect.poll(() => counters.offerCount, { timeout: 5000 }).toBe(3);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('sends reconnect backfill tail without omitting the 35256-69467ms missing-chunks span before setRemoteDescription', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { backfillDelayMs: 400 });

  await startReconnectCall(page, counters);
  await page.waitForTimeout(700);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => counters.backfillCount).toBeGreaterThanOrEqual(2);

  expect(counters.backfills[0]).toMatchObject({ batch_index: 1, final: false });
  expect(counters.backfills[1]).toMatchObject({ batch_index: 2, final: true });
  expect(Number(counters.backfills[1].duration_ms ?? 0)).toBeGreaterThan(0);
  expect(MIC_BACKFILL_ROLLING_MS).toBe(180000);
  expect(counters.backfills.every((entry) => Number(entry.duration_ms ?? 0) <= 10_000)).toBe(true);

  const selectedOffsets = reconnectBackfillSelections(counters);
  expect(selectedOffsets.length).toBeGreaterThanOrEqual(2);
  for (let index = 1; index < selectedOffsets.length; index += 1) {
    expect(selectedOffsets[index].startMs).toBeLessThanOrEqual(selectedOffsets[index - 1].endMs);
  }

  const finalSendingIndex = counters.debugEvents.findIndex(
    (entry) =>
      entry.event === 'mic.reconnect_backfill.sending' &&
      entry.detail.batchIndex === 2 &&
      entry.detail.final === true
  );
  expect(finalSendingIndex).toBeGreaterThanOrEqual(0);
  const remoteDescriptionIndex = counters.debugEvents.findIndex(
    (entry, index) => index > finalSendingIndex && entry.event === 'pc.setRemoteDescription.done'
  );
  expect(remoteDescriptionIndex).toBeGreaterThanOrEqual(0);
  assertNoBrowserErrors();
});

test('keeps the current reconnect final tail alive when the replacement peer reports connected', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  let releaseFinalBackfill: () => void = () => {};
  const finalBackfillGate = new Promise<void>((resolve) => {
    releaseFinalBackfill = resolve;
  });
  await installMockCallMedia(page, { controllablePcm: true });
  const counters = await installReconnectCallRoutes(page, { finalBackfillGate });

  await startReconnectCall(page, counters);
  await emitMockPcm(page, 1111, 400_000);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.backfills.some((entry) => entry.final === true)).toBe(true);
  const finalBatch = counters.backfills.find((entry) => entry.final === true);
  expect(finalBatch).toBeDefined();
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);

  await setCurrentMockPeerState(page, 'connected', 'connected');
  await expect(page.getByTestId('voice-visualizer').getByText('Understanding')).toBeVisible();
  expect(debugEventCount(counters, 'mic.reconnect_backfill.recovery_drain')).toBeGreaterThan(0);

  releaseFinalBackfill();
  await expect.poll(
    () =>
      counters.debugEvents.filter(
        (entry) =>
          entry.event === 'mic.reconnect_backfill.sent' &&
          entry.detail.final === true
      ).length
  ).toBe(1);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  expect(debugEventCount(counters, 'mic.reconnect_backfill.recovery_drain_timeout')).toBe(0);
  assertNoBrowserErrors();
});

test('drains pending reconnect backfill before ending during reconnect', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { offerDelayMs: 600 });

  await startReconnectCall(page, counters);
  await page.waitForTimeout(700);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.offerCount).toBe(2);
  await page.getByRole('button', { name: 'End Call' }).click();

  await expect.poll(() => counters.backfillCount).toBeGreaterThanOrEqual(1);
  await expect.poll(() => counters.endCount).toBe(1);
  expect(counters.backfills.at(-1)).toMatchObject({ final: true });
  expect(counters.requestOrder.indexOf('backfill')).toBeGreaterThanOrEqual(0);
  expect(counters.requestOrder.indexOf('backfill')).toBeLessThan(
    counters.requestOrder.indexOf('end')
  );
  assertNoBrowserErrors();
});

test('awaits in-flight reconnect backfill before ending without duplicate drain', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { backfillDelayMs: 400 });

  await startReconnectCall(page, counters);
  await page.waitForTimeout(700);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.backfillCount).toBe(1);
  await page.getByRole('button', { name: 'End Call' }).click();

  await expect.poll(() => counters.endCount).toBe(1);
  expect(counters.backfills).toHaveLength(2);
  expect(counters.backfills[0]).toMatchObject({ batch_index: 1, final: false });
  expect(counters.backfills[1]).toMatchObject({ batch_index: 2, final: true });
  expect(counters.requestOrder.lastIndexOf('backfill')).toBeLessThan(
    counters.requestOrder.indexOf('end')
  );
  assertNoBrowserErrors();
});

test('ends when the final reconnect backfill request stalls during hangup', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, { hangBackfillFrom: 2 });

  await startReconnectCall(page, counters);
  await page.waitForTimeout(700);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.backfillCount).toBe(2);
  await page.getByRole('button', { name: 'End Call' }).click();

  expect(counters.backfills[1]).toMatchObject({ final: true });
  await expect.poll(() => counters.endCount, { timeout: 5000 }).toBe(1);
  expect(counters.requestOrder.indexOf('end')).toBeGreaterThan(
    counters.requestOrder.indexOf('backfill')
  );
  assertNoBrowserErrors();
});

test('recovers user final when reconnect backfill response fails after data channel closes', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, {
    failBackfill: true,
    recoverEvents: [
      {
        type: 'user_final',
        session_id: 'rtc-call-reconnect-01',
        turn_id: 'user-turn-recovered',
        text: 'Recovered speech from STT.'
      }
    ]
  });

  await startReconnectCall(page, counters);
  await page.waitForTimeout(700);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.backfillCount).toBeGreaterThanOrEqual(1);
  await expect.poll(() => counters.recoverCount).toBeGreaterThanOrEqual(1);
  await expect.poll(() => counters.turnCount).toBe(1);
  expect(counters.turns[0]).toMatchObject({
    session_id: 'rtc-call-reconnect-01',
    turn_id: 'user-turn-recovered',
    text: 'Recovered speech from STT.',
    source: 'user_final'
  });
  await expect(page.getByText('Recovered speech from STT.')).toBeVisible();
  assertNoBrowserErrors();
});

test('waits out the disconnected grace period before re-offering call media', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  await page.clock.install();
  await setCurrentMockPeerState(page, 'disconnected', 'disconnected');

  await page.clock.fastForward(2_000);
  expect(counters.offerCount).toBe(1);
  expect(counters.endCount).toBe(0);
  expect(debugEventCount(counters, 'pc.media_reconnect.scheduled')).toBe(1);

  await page.clock.fastForward(500);
  await expect.poll(() => counters.offerCount).toBe(2);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('does not re-offer when disconnected media recovers within the grace period', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  await page.clock.install();
  await setCurrentMockPeerState(page, 'disconnected', 'disconnected');

  await page.clock.fastForward(1_000);
  expect(counters.offerCount).toBe(1);
  await setCurrentMockPeerState(page, 'connected', 'connected');
  await page.clock.fastForward(2_000);

  expect(counters.offerCount).toBe(1);
  expect(counters.endCount).toBe(0);
  const snapshot = await getMockCallMediaSnapshot(page);
  expect(snapshot.peers).toHaveLength(1);
  expect(snapshot.peers[0]).toMatchObject({ connectionState: 'connected', closed: false });
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('re-offers when ICE disconnects while aggregate peer state stays connected', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);
  await page.clock.install();
  await setCurrentMockPeerState(page, 'connected', 'connected');
  await setCurrentMockPeerIceState(page, 'disconnected');

  await page.clock.fastForward(2_000);
  expect(counters.offerCount).toBe(1);
  expect(counters.endCount).toBe(0);
  expect(debugEventCount(counters, 'pc.media_reconnect.scheduled')).toBe(1);

  await page.clock.fastForward(500);
  await expect.poll(() => counters.offerCount).toBe(2);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('bounds three connected peer flaps to two replacement offers before terminal recovery', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page);

  await startReconnectCall(page, counters);

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(3);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(2);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect(page.getByRole('alert').getByText(TERMINAL_CONNECTION_DROPPED_COPY)).toBeVisible();
  expect(counters.offerCount).toBe(1 + MEDIA_RECONNECT_MAX_ATTEMPTS);
  await expect.poll(() => counters.recoverCount).toBeGreaterThanOrEqual(1);
  await expect.poll(() => counters.endCount).toBe(1);
  expect(debugEventCount(counters, 'pc.media_reconnect.give_up')).toBe(1);
  expect(
    counters.debugEvents
      .filter((entry) => entry.event === 'pc.media_reconnect.start')
      .map((entry) => entry.detail.attempt)
  ).toEqual([1, 2]);
  expect(counters.requestOrder.indexOf('recover')).toBeGreaterThanOrEqual(0);
  expect(counters.requestOrder.indexOf('recover')).toBeLessThan(
    counters.requestOrder.indexOf('end')
  );
  await expect(page.getByTestId('voice-visualizer')).toHaveCount(0);
  assertNoBrowserErrors();
});

test('recovers queued turn and ends when terminal media reconnect fails', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  await installMockCallMedia(page);
  const counters = await installReconnectCallRoutes(page, {
    failOfferFrom: 3,
    recoverEvents: [
      {
        type: 'user_final',
        session_id: 'rtc-call-reconnect-01',
        turn_id: 'user-turn-terminal-recover',
        text: 'Recovered terminal reconnect speech.'
      }
    ]
  });

  await startReconnectCall(page, counters);

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);
  await setCurrentMockPeerState(page, 'failed', 'disconnected');

  await expect.poll(() => counters.offerCount).toBe(3);
  await expect.poll(() => counters.recoverCount).toBeGreaterThanOrEqual(1);
  await expect.poll(() => counters.turnCount).toBe(1);
  await expect.poll(() => counters.endCount).toBe(1);
  expect(counters.turns[0]).toMatchObject({
    session_id: 'rtc-call-reconnect-01',
    turn_id: 'user-turn-terminal-recover',
    text: 'Recovered terminal reconnect speech.',
    source: 'user_final'
  });
  expect(counters.requestOrder.indexOf('recover')).toBeLessThan(
    counters.requestOrder.indexOf('end')
  );
  assertNoBrowserErrors();
});

test('keeps recovered turn response live when terminal reconnect offer fails before audio starts', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 502/]
  });
  await installMockCallMedia(page);
  let deliverLiveResponse = () => {};
  const turnStreamGate = new Promise<void>((resolve) => {
    deliverLiveResponse = resolve;
  });
  const counters = await installReconnectCallRoutes(page, {
    failOfferFrom: 3,
    turnStreamGate,
    turnStreamEvents: [
      {
        type: 'ai_audio_started',
        session_id: 'rtc-call-reconnect-01',
        turn_id: 'user-turn-active-response',
        audio: { duration_ms: 1200, samples: 19200 }
      },
      {
        type: 'ai_token',
        turn_id: 'user-turn-active-response',
        text: 'Live response after recovery.'
      },
      {
        type: 'ai_done',
        turn_id: 'user-turn-active-response'
      }
    ]
  });

  await startReconnectCall(page, counters);

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(2);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.ok')).toBe(1);

  await emitLatestMockDataChannelEvent(page, {
    type: 'user_final',
    session_id: 'rtc-call-reconnect-01',
    turn_id: 'user-turn-active-response',
    text: 'Recovered long-turn speech.'
  });
  await expect.poll(() => counters.turnCount).toBe(1);
  await expect(page.getByText('Recovered long-turn speech.')).toBeVisible();

  await setCurrentMockPeerState(page, 'failed', 'disconnected');
  await expect.poll(() => counters.offerCount).toBe(3);
  await expect.poll(() => debugEventCount(counters, 'pc.media_reconnect.failed')).toBe(1);
  await page.waitForTimeout(100);

  const heldResponseMedia = await getMockCallMediaSnapshot(page);
  expect(
    heldResponseMedia.peers.some(
      (peer) => peer.remoteDescriptionType === 'answer' && !peer.closed
    )
  ).toBe(true);
  expect(counters.endCount).toBe(0);
  await expect(page.getByRole('alert')).toHaveCount(0);

  deliverLiveResponse();
  await expect(page.getByText('Live response after recovery.')).toBeVisible();
  await expect.poll(() => debugEventCount(counters, 'call.ai_audio_started')).toBe(1);
  const responseIndex = counters.requestOrder.indexOf('turn_response');
  expect(responseIndex).toBeGreaterThan(counters.requestOrder.indexOf('turn'));
  const endIndex = counters.requestOrder.indexOf('end');
  if (endIndex >= 0) {
    expect(endIndex).toBeGreaterThan(responseIndex);
  }
  assertNoBrowserErrors();
});

test('shows a call notice in the transcript when /turns returns a type=error SSE event', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installTurnErrorCallRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  // User transcript entry appears (user_final delivered via start events)
  await expect(page.getByText('Hello there.')).toBeVisible();

  // Error notice appears in the transcript — not a blocking panel
  await expect(page.getByText('Speech playback failed: voice audio unavailable.')).toBeVisible();

  // Call state returns to listening — toolbar is still visible (not failed)
  await expect(page.getByRole('button', { name: 'End Call' })).toBeVisible();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('rejoins a running duplicate and restores its canonical assistant transcript', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installDuplicateTurnCallRoutes(page, [
    {
      type: 'turn_existing',
      turn_id: 'turn-existing-running',
      state: 'running',
      recoverable: false
    },
    {
      type: 'ai_done',
      turn_id: 'turn-existing-running',
      existing: true,
      message: duplicateAssistantMessage(
        'message-existing-running',
        'The running turn rejoined its durable answer.'
      )
    }
  ], 'turn-existing-running');

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByText('The running turn rejoined its durable answer.')).toBeVisible();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  expect(counters.turnCount).toBe(1);
  assertNoBrowserErrors();
});

test('restores a completed duplicate response and returns the call to Listening', async ({
  page
}) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  const counters = await installDuplicateTurnCallRoutes(page, [
    {
      type: 'ai_done',
      turn_id: 'turn-existing-completed',
      existing: true,
      message: duplicateAssistantMessage(
        'message-existing-completed',
        'The completed retry restored this exact answer.'
      )
    }
  ], 'turn-existing-completed');

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByText('The completed retry restored this exact answer.')).toBeVisible();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  expect(counters.turnCount).toBe(1);
  assertNoBrowserErrors();
});

test('shows a recoverable notice for a cancelled duplicate turn', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installDuplicateTurnCallRoutes(page, [
    {
      type: 'turn_existing',
      turn_id: 'turn-existing-cancelled',
      state: 'cancelled',
      recoverable: true
    }
  ], 'turn-existing-cancelled');

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(
    page.getByText('That turn was cancelled. RayMe is listening for you to try again.')
  ).toBeVisible();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

async function startReconnectCall(page: Page, counters: ReconnectRouteCounters) {
  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  await expect.poll(() => counters.offerCount).toBe(1);
  await expect.poll(async () => (await getMockCallMediaSnapshot(page)).peers.length).toBe(1);
}

async function setCurrentMockPeerState(
  page: Page,
  connectionState: RTCPeerConnectionState,
  iceConnectionState: RTCIceConnectionState = connectionState as RTCIceConnectionState
) {
  await setMockPeerState(page, -1, connectionState, iceConnectionState);
}

async function completeCurrentMockPeerConnection(page: Page) {
  await page.evaluate(() => {
    const target = window as Window & {
      __raymeMockPeerConnections?: Array<{
        completeMockConnection: () => void;
      }>;
    };
    const peer = target.__raymeMockPeerConnections?.at(-1);
    if (!peer) {
      throw new Error('No mock peer connection is available');
    }
    peer.completeMockConnection();
  });
}

async function setMockPeerState(
  page: Page,
  peerIndex: number,
  connectionState: RTCPeerConnectionState,
  iceConnectionState: RTCIceConnectionState = connectionState as RTCIceConnectionState
) {
  await page.evaluate(
    ({ peerIndex, connectionState, iceConnectionState }) => {
      const target = window as Window & {
        __raymeMockPeerConnections?: Array<{
          setMockConnectionState: (
            connectionState: RTCPeerConnectionState,
            iceConnectionState?: RTCIceConnectionState
          ) => void;
        }>;
      };
      const peer = target.__raymeMockPeerConnections?.at(peerIndex);
      if (!peer) {
        throw new Error('No mock peer connection is available');
      }
      peer.setMockConnectionState(connectionState, iceConnectionState);
    },
    { peerIndex, connectionState, iceConnectionState }
  );
}

async function setCurrentMockPeerIceState(page: Page, iceConnectionState: RTCIceConnectionState) {
  await page.evaluate(
    ({ iceConnectionState }) => {
      const target = window as Window & {
        __raymeMockPeerConnections?: Array<{
          setMockIceConnectionState: (iceConnectionState: RTCIceConnectionState) => void;
        }>;
      };
      const peer = target.__raymeMockPeerConnections?.at(-1);
      if (!peer) {
        throw new Error('No mock peer connection is available');
      }
      peer.setMockIceConnectionState(iceConnectionState);
    },
    { iceConnectionState }
  );
}

async function emitLatestMockDataChannelEvent(page: Page, event: Record<string, unknown>) {
  await page.evaluate((event) => {
    const target = window as Window & {
      __raymeMockDataChannels?: Array<{
        emitMockMessage?: (data: string) => void;
      }>;
    };
    target.__raymeMockDataChannels?.at(-1)?.emitMockMessage?.(JSON.stringify(event));
  }, event);
}

async function emitMockPcm(page: Page, sample: number, sampleCount = 320) {
  await page.evaluate(({ sample, sampleCount }) => {
    const target = window as Window & {
      __raymeEmitMockPcm?: (sample: number, sampleCount?: number) => void;
    };
    if (!target.__raymeEmitMockPcm) {
      throw new Error('Controllable mock PCM recorder is unavailable');
    }
    target.__raymeEmitMockPcm(sample, sampleCount);
  }, { sample, sampleCount });
}

async function getMockLocalAudioTrackStates(page: Page): Promise<boolean[]> {
  return page.evaluate(() => {
    const stream = (
      window as Window & { __raymeMockLocalMediaStream?: MediaStream }
    ).__raymeMockLocalMediaStream;
    return (stream?.getAudioTracks() ?? []).map((track) => track.enabled);
  });
}

function decodePcmValues(pcmBase64: string) {
  const bytes = Buffer.from(pcmBase64, 'base64');
  const values: number[] = [];
  for (let offset = 0; offset + 1 < bytes.length; offset += 2) {
    values.push(bytes.readInt16LE(offset));
  }
  return values;
}

async function getMockCallMediaSnapshot(page: Page): Promise<MockCallMediaSnapshot> {
  return page.evaluate(() => {
    const target = window as Window & {
      __raymeMockPeerConnections?: Array<{
        id: number;
        connectionState: RTCPeerConnectionState;
        iceConnectionState: RTCIceConnectionState;
        createdOfferCount: number;
        closed: boolean;
        closeCount: number;
        localDescription: RTCSessionDescriptionInit | null;
        remoteDescription: RTCSessionDescriptionInit | null;
        dataChannels: Array<{ id: number }>;
        remoteStream: MediaStream | null;
      }>;
      __raymeMockDataChannels?: Array<{
        id: number;
        label: string;
        ownerPeerId: number;
        readyState: RTCDataChannelState;
        closeCount: number;
        sentMessages: string[];
      }>;
      __raymeMockRemoteAudioStreams?: MediaStream[];
      __raymeMockAudioPlayback?: {
        activeStreamId: string | null;
        playedStreamIds: string[];
        pausedStreamIds: string[];
      };
    };

    return {
      peers: (target.__raymeMockPeerConnections ?? []).map((peer) => ({
        id: peer.id,
        connectionState: peer.connectionState,
        iceConnectionState: peer.iceConnectionState,
        createdOfferCount: peer.createdOfferCount,
        closed: peer.closed,
        closeCount: peer.closeCount,
        localDescriptionType: peer.localDescription?.type ?? null,
        remoteDescriptionType: peer.remoteDescription?.type ?? null,
        dataChannelIds: peer.dataChannels.map((channel) => channel.id),
        remoteStreamId: peer.remoteStream?.id ?? null
      })),
      channels: (target.__raymeMockDataChannels ?? []).map((channel) => ({
        id: channel.id,
        label: channel.label,
        ownerPeerId: channel.ownerPeerId,
        readyState: channel.readyState,
        closeCount: channel.closeCount,
        sentMessages: [...channel.sentMessages]
      })),
      remoteStreams: (target.__raymeMockRemoteAudioStreams ?? []).map((stream) => ({
        id: stream.id,
        audioTracks: stream.getAudioTracks().length
      })),
      audioPlayback: {
        activeStreamId: target.__raymeMockAudioPlayback?.activeStreamId ?? null,
        playedStreamIds: [...(target.__raymeMockAudioPlayback?.playedStreamIds ?? [])],
        pausedStreamIds: [...(target.__raymeMockAudioPlayback?.pausedStreamIds ?? [])]
      }
    };
  });
}

function debugEventCount(counters: ReconnectRouteCounters, event: string) {
  return counters.debugEvents.filter((entry) => entry.event === event).length;
}

function reconnectBackfillSelections(counters: ReconnectRouteCounters) {
  return counters.debugEvents
    .filter((entry) => entry.event === 'mic.reconnect_backfill.sending')
    .map((entry) => ({
      startMs: Number(entry.detail.selectedStartOffsetMs),
      endMs: Number(entry.detail.selectedEndOffsetMs)
    }))
    .filter((entry) => Number.isFinite(entry.startMs) && Number.isFinite(entry.endMs));
}

function readMockPeerIdFromSdp(sdp: string) {
  const match = /^a=x-rayme-mock-peer-id:(\d+)$/m.exec(sdp);
  return match ? Number(match[1]) : null;
}

async function installTurnErrorCallRoutes(page: Page) {
  await installCallDebugEventRoute(page);
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });

  await page.route('**/api/threads/*', async (route) => {
    await fulfillJson(route, thread);
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-error-01',
      session_id: 'rtc-call-error-01',
      thread_id: threadId,
      state: 'listening',
      events: [
        {
          type: 'user_final',
          session_id: 'rtc-call-error-01',
          turn_id: 'turn-err-1',
          text: 'Hello there.'
        }
      ]
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-error-01',
      session_id: 'rtc-call-error-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
  await page.route('**/api/calls/*/turns', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({
          type: 'error',
          turn_id: 'turn-err-1',
          code: 'call_tts_failed',
          message: 'Speech playback failed: voice audio unavailable.'
        })}`,
        '',
        ''
      ].join('\n')
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    await fulfillJson(route, { state: 'ended' });
  });
}

async function installDuplicateTurnCallRoutes(
  page: Page,
  streamEvents: Array<Record<string, unknown>>,
  turnId: string
) {
  await installCallDebugEventRoute(page);
  const counters = { turnCount: 0 };
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });

  await page.route('**/api/threads/*', async (route) => {
    await fulfillJson(route, thread);
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-existing-01',
      session_id: 'rtc-call-existing-01',
      thread_id: threadId,
      state: 'listening',
      events: [
        {
          type: 'user_final',
          session_id: 'rtc-call-existing-01',
          turn_id: turnId,
          text: 'Retry my existing turn.'
        }
      ]
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-existing-01',
      session_id: 'rtc-call-existing-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
  await page.route('**/api/calls/*/turns', async (route) => {
    counters.turnCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: streamEvents.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    await fulfillJson(route, { state: 'ended' });
  });
  return counters;
}

function duplicateAssistantMessage(id: string, contentText: string) {
  return {
    id,
    thread_id: threadId,
    message_kind: 'ai_speech',
    role: 'assistant',
    sequence: 2,
    content_text: contentText,
    created_at: null,
    updated_at: null
  };
}

async function installReconnectCallRoutes(
  page: Page,
  options: ReconnectRouteOptions = {}
) {
  const hangingBackfillResolvers: Array<() => void> = [];
  const counters: ReconnectRouteCounters = {
    offerCount: 0,
    backfillCount: 0,
    recoverCount: 0,
    turnCount: 0,
    endCount: 0,
    muteCount: 0,
    peerPromotionCount: 0,
    backendActivePeerId: null,
    backendActivePeerGeneration: null,
    backendOldPeerRetirementCount: 0,
    abortedPeerCommitResponses: 0,
    peerPromotionInProgressCount: 0,
    backendVoiceId: 'voice-before',
    backendEngineId: 'qwen3_1_7b',
    backendPromptLeaseOwner: 'rtc-call-reconnect-01',
    backendPromptLeaseReleaseCount: 0,
    offers: [],
    backfills: [],
    recoveredEvents: [],
    turns: [],
    muteRequests: [],
    peerPromotions: [],
    requestOrder: [],
    debugEvents: []
  };
  let authoritativeMuted = false;
  let authoritativeAudioInputEpoch = 0;
  let authoritativeMuteRevision = 0;
  let switchingPeerGeneration: number | null = null;
  const pendingPeerIds = new Map<number, number | null>();
  const commitBackendPeer = (generation: number, peerId: number | null) => {
    if (counters.backendActivePeerId !== peerId) {
      counters.backendOldPeerRetirementCount += 1;
    }
    counters.backendActivePeerId = peerId;
    counters.backendActivePeerGeneration = generation;
    pendingPeerIds.delete(generation);
    switchingPeerGeneration = null;
    if (
      options.selectionChangingPeerCommitDelayMs ||
      options.selectionChangingPeerCommitGate
    ) {
      counters.backendVoiceId = 'voice-after';
      counters.backendEngineId = 'f5';
      if (counters.backendPromptLeaseOwner !== null) {
        counters.backendPromptLeaseReleaseCount += 1;
        counters.backendPromptLeaseOwner = null;
      }
    }
  };
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });

  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, thread);
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/*/_debug/event', async (route) => {
    const payload = route.request().postDataJSON() as {
      event?: string;
      detail?: Record<string, unknown>;
      session_id?: string;
    };
    counters.debugEvents.push({
      event: payload.event ?? '',
      detail: payload.detail ?? {},
      session_id: payload.session_id
    });
    await fulfillJson(route, { status: 'ok' });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: 'rtc-call-reconnect-01',
      thread_id: threadId,
      state: 'listening'
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    counters.offerCount += 1;
    counters.requestOrder.push('offer');
    const payload = route.request().postDataJSON() as { offer?: { sdp?: string } };
    const sdp = payload.offer?.sdp ?? '';
    const peerId = readMockPeerIdFromSdp(sdp);
    counters.offers.push({
      peerId,
      sdp
    });
    if (options.offerDelayMs && counters.offerCount > 1) {
      await new Promise((resolve) => setTimeout(resolve, options.offerDelayMs));
    }
    if (
      options.failOfferNumbers?.includes(counters.offerCount) ||
      (options.failOfferFrom && counters.offerCount >= options.failOfferFrom)
    ) {
      await fulfillJson(route, {
        detail: {
          code: 'webrtc_offer_failed',
          message: 'WebRTC offer could not be accepted'
        }
      }, 502);
      return;
    }
    const peerGeneration = counters.offerCount > 1 ? counters.offerCount - 1 : null;
    if (peerGeneration === null) {
      counters.backendActivePeerId = peerId;
    } else {
      pendingPeerIds.set(peerGeneration, peerId);
    }
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: 'rtc-call-reconnect-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events',
      peer_generation: peerGeneration,
      peer_commit_timeout_ms: 8000
    });
  });
  await page.route('**/api/calls/*/peer-promotion', async (route) => {
    const payload = route.request().postDataJSON() as {
      session_id: string;
      generation: number;
      action: 'commit' | 'reject';
    };
    counters.peerPromotionCount += 1;
    counters.peerPromotions.push(payload);
    counters.requestOrder.push(`peer_${payload.action}`);
    const pendingPeerId = pendingPeerIds.get(payload.generation);
    if (counters.backendActivePeerGeneration === payload.generation) {
      if (options.reconcileCommittedAsConflict || payload.action === 'reject') {
        await fulfillJson(route, {
          detail: {
            code: 'webrtc_peer_already_committed',
            message: 'Replacement peer generation was already committed'
          }
        }, 502);
        return;
      }
      await fulfillJson(route, {
        call_id: 'call-reconnect-01',
        session_id: payload.session_id,
        generation: payload.generation,
        status: 'committed'
      });
      return;
    }
    if (switchingPeerGeneration === payload.generation) {
      counters.peerPromotionInProgressCount += 1;
      await fulfillJson(route, {
        call_id: 'call-reconnect-01',
        session_id: payload.session_id,
        generation: payload.generation,
        status: 'in_progress'
      });
      return;
    }
    if (pendingPeerId === undefined) {
      await fulfillJson(route, {
        detail: {
          code: 'webrtc_peer_generation_stale',
          message: 'Replacement peer generation is no longer pending'
        }
      }, 409);
      return;
    }
    if (
      payload.action === 'commit' &&
      (options.selectionChangingPeerCommitDelayMs ||
        options.selectionChangingPeerCommitGate)
    ) {
      switchingPeerGeneration = payload.generation;
      pendingPeerIds.delete(payload.generation);
      if (options.selectionChangingPeerCommitGate) {
        await options.selectionChangingPeerCommitGate;
      } else {
        await new Promise((resolve) =>
          setTimeout(resolve, options.selectionChangingPeerCommitDelayMs)
        );
      }
      commitBackendPeer(payload.generation, pendingPeerId);
      counters.abortedPeerCommitResponses += 1;
      await route.abort('failed').catch(() => undefined);
      return;
    }
    if (payload.action === 'commit') {
      commitBackendPeer(payload.generation, pendingPeerId);
    }
    if (payload.action === 'reject') {
      pendingPeerIds.delete(payload.generation);
    }
    if (
      payload.action === 'commit' &&
      options.abortFirstPeerCommitResponse &&
      counters.abortedPeerCommitResponses === 0
    ) {
      counters.abortedPeerCommitResponses += 1;
      await route.abort('failed');
      return;
    }
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: payload.session_id,
      generation: payload.generation,
      status: payload.action === 'commit' ? 'committed' : 'rejected'
    });
  });
  await page.route('**/api/calls/*/reconnect-audio', async (route) => {
    counters.backfillCount += 1;
    counters.requestOrder.push('backfill');
    const backfillPayload = route.request().postDataJSON() as Record<string, unknown>;
    counters.backfills.push(backfillPayload);
    if (options.firstBackfillGate && counters.backfillCount === 1) {
      await options.firstBackfillGate;
    }
    if (options.finalBackfillGate && backfillPayload.final === true) {
      await options.finalBackfillGate;
    }
    if (options.backfillDelayMs && counters.backfillCount === 1) {
      await new Promise((resolve) => setTimeout(resolve, options.backfillDelayMs));
    }
    if (options.hangBackfillFrom && counters.backfillCount >= options.hangBackfillFrom) {
      await new Promise<void>((resolve) => {
        hangingBackfillResolvers.push(resolve);
      });
    }
    if (options.failBackfill) {
      await fulfillJson(route, {
        detail: {
          code: 'call_reconnect_audio_failed',
          message: 'Call control request failed'
        }
      }, 502);
      return;
    }
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: 'rtc-call-reconnect-01',
      status: 'accepted',
      frames: 1,
      duration_ms: 20
    });
  });
  await page.route('**/api/calls/*/events/recover', async (route) => {
    counters.recoverCount += 1;
    counters.requestOrder.push('recover');
    const events = counters.recoverCount === 1 ? options.recoverEvents ?? [] : [];
    counters.recoveredEvents.push(...events);
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: 'rtc-call-reconnect-01',
      events
    });
  });
  await page.route('**/api/calls/*/mute', async (route) => {
    const payload = route.request().postDataJSON() as { muted?: boolean };
    counters.muteCount += 1;
    counters.muteRequests.push(payload as Record<string, unknown>);
    const requestedMuted = payload.muted === true;
    if (requestedMuted && !authoritativeMuted) {
      authoritativeAudioInputEpoch =
        options.authoritativeMuteEpoch ?? authoritativeAudioInputEpoch + 1;
    }
    authoritativeMuted = requestedMuted;
    authoritativeMuteRevision += 1;
    if (options.firstMuteGate && counters.muteCount === 1) {
      await options.firstMuteGate;
    }
    if (options.muteGate) {
      await options.muteGate;
    }
    if (options.abortMuteNumbers?.includes(counters.muteCount)) {
      await route.abort('failed');
      return;
    }
    await fulfillJson(route, {
      muted: authoritativeMuted,
      audio_input_epoch: authoritativeAudioInputEpoch,
      mute_revision: authoritativeMuteRevision
    });
  });
  await page.route('**/api/calls/*/turns', async (route) => {
    counters.turnCount += 1;
    counters.requestOrder.push('turn');
    counters.turns.push(route.request().postDataJSON() as Record<string, unknown>);
    if (options.turnStreamGate) {
      await options.turnStreamGate;
    }
    counters.requestOrder.push('turn_response');
    const streamEvents = options.turnStreamEvents ?? [{ type: 'ai_done' }];
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: streamEvents.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    counters.endCount += 1;
    counters.requestOrder.push('end');
    while (hangingBackfillResolvers.length > 0) {
      hangingBackfillResolvers.shift()?.();
    }
    await fulfillJson(route, { call_id: 'call-reconnect-01', session_id: 'rtc-call-reconnect-01', reason: 'hangup' });
  });

  return counters;
}

async function installCallStartRoutes(page: Page, options: CallStartRouteOptions = {}) {
  const counters: StartupRouteCounters = {
    startCount: 0,
    offerCount: 0,
    endCount: 0,
    requestOrder: []
  };
  await installCallDebugEventRoute(page);
  const character = makeCharacter({
    id: characterId,
    name: 'Call Start Aster',
    default_voice_state: 'assigned',
    default_voice_label: 'Assigned voice',
    default_voice: {
      id: 'voice-call-start',
      name: 'Call Start Voice',
      default_engine: options.qwenPreparation ? 'qwen3_1_7b' : 'f5',
      reference_transcript: 'Reference text.',
      sample_asset_id: 'asset-call-start',
      preview_audio_url: null,
      metadata: {},
      deleted_at: null,
      created_at: null,
      updated_at: null
    }
  });
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });

  await page.route('**/api/characters', async (route) => {
    await fulfillJson(route, { items: [character] });
  });
  await page.route('**/api/threads', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { thread_id: threadId }, 201);
      return;
    }
    await fulfillJson(route, { items: [] });
  });
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, thread);
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  if (options.qwenPreparation) {
    await page.route('**/api/voices/voice-call-start', async (route) => {
      await fulfillJson(route, character.default_voice);
    });
    await page.route('**/api/voices/preparation-status', async (route) => {
      await fulfillJson(route, {
        model: { state: 'loading', engine_id: 'qwen3_1_7b' },
        prompt: { state: 'prewarming', voice_key: 'opaque-call-voice' }
      });
    });
  }
  await page.route('**/api/calls/start', async (route: Route) => {
    expect(route.request().method()).toBe('POST');
    counters.startCount += 1;
    counters.requestOrder.push('start');
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      thread_id: threadId,
      voice_id: options.qwenPreparation ? 'voice-call-start' : null,
      engine_id: options.qwenPreparation ? 'qwen3_1_7b' : 'f5',
      state: 'listening'
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    counters.offerCount += 1;
    counters.requestOrder.push('offer');
    if (options.offerGate) {
      await options.offerGate;
    }
    if (options.failOffer) {
      await fulfillJson(
        route,
        { detail: { code: 'webrtc_offer_failed', message: 'WebRTC offer could not be accepted' } },
        502
      );
      return;
    }
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events',
      ...(options.qwenPreparation
        ? {
            preparation: {
              model: { state: 'resident', engine_id: 'qwen3_1_7b' },
              prompt: {
                state: options.qwenPromptState ?? 'ready',
                voice_key: 'opaque-call-voice',
                error_code:
                  options.qwenPromptState === 'failed' ? 'qwen3_prompt_failed' : null
              }
            }
          }
        : {})
    });
  });
  await page.route('**/api/calls/*/events/recover', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      events: []
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    counters.endCount += 1;
    counters.requestOrder.push('end');
    await fulfillJson(route, { call_id: 'call-start-01', session_id: 'rtc-call-start-01', reason: 'setup_failed' });
  });
  return counters;
}

async function installMultiTurnCallRoutes(page: Page) {
  await installCallDebugEventRoute(page);
  let ended = false;
  let turnCount = 0;
  const thread = makeThreadDetail({
    id: threadId,
    character_id: characterId,
    title: 'Call Start Aster',
    character_name: 'Call Start Aster',
    messages: []
  });
  const finalRows = [
    callRow('call-start-row', 'call_start', 0, 'Call started'),
    callRow('user-speech-1', 'user_speech', 1, 'First user turn.'),
    callRow('ai-speech-1', 'ai_speech', 2, 'First AI answer.'),
    callRow('user-speech-2', 'user_speech', 3, 'Second user turn.'),
    callRow('ai-speech-2', 'ai_speech', 4, 'Second AI answer.'),
    callRow('call-end-row', 'call_end', 5, 'Call ended')
  ];

  await page.route('**/api/threads/*', async (route) => {
    await fulfillJson(route, { ...thread, messages: ended ? finalRows : [] });
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      thread_id: threadId,
      state: 'listening',
      events: [
        {
          type: 'user_final',
          session_id: 'rtc-call-start-01',
          turn_id: 'turn-1',
          text: 'First user turn.'
        },
        {
          type: 'user_final',
          session_id: 'rtc-call-start-01',
          turn_id: 'turn-2',
          text: 'Second user turn.'
        }
      ]
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
  await page.route('**/api/calls/*/turns', async (route) => {
    turnCount += 1;
    const text = turnCount === 1 ? 'First AI answer.' : 'Second AI answer.';
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({ type: 'ai_token', turn_id: `turn-${turnCount}`, text })}`,
        '',
        `data: ${JSON.stringify({ type: 'ai_done', turn_id: `turn-${turnCount}` })}`,
        '',
        ''
      ].join('\n')
    });
  });
  await page.route('**/api/calls/*/events/recover', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      events: []
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    ended = true;
    await fulfillJson(route, { state: 'ended', duration_ms: 18_000 });
  });
  await page.route('**/api/calls/*/interrupt', async (route) => {
    await fulfillJson(route, { state: 'listening' });
  });
  await page.route('**/api/calls/*/mute', async (route) => {
    await fulfillJson(route, { muted: true, audio_input_epoch: 1, mute_revision: 1 });
  });
}

function callRow(id: string, message_kind: string, sequence: number, content_text: string) {
  return {
    id,
    thread_id: threadId,
    message_kind,
    role: message_kind === 'user_speech' ? 'user' : message_kind === 'ai_speech' ? 'assistant' : 'event',
    sequence,
    content_text,
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}
