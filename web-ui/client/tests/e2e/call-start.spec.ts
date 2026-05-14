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
  offers: Array<{ peerId: number | null; sdp: string }>;
  backfills: Array<Record<string, unknown>>;
  recoveredEvents: Array<Record<string, unknown>>;
  turns: Array<Record<string, unknown>>;
  requestOrder: string[];
  debugEvents: Array<{ event: string; detail: Record<string, unknown>; session_id?: string }>;
};

type ReconnectRouteOptions = {
  backfillDelayMs?: number;
  failBackfill?: boolean;
  hangBackfillFrom?: number;
  recoverEvents?: Array<Record<string, unknown>>;
  offerDelayMs?: number;
  failOfferNumbers?: number[];
  failOfferFrom?: number;
  turnStreamGate?: Promise<void>;
  turnStreamEvents?: Array<Record<string, unknown>>;
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
};

type MockCallMediaSnapshot = {
  peers: Array<{
    id: number;
    connectionState: RTCPeerConnectionState;
    iceConnectionState: RTCIceConnectionState;
    createdOfferCount: number;
    closed: boolean;
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
  expect(debugEventCount(counters, 'datachannel.close')).toBe(1);
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

  await page.clock.fastForward(2_400);
  expect(counters.offerCount).toBe(1);
  expect(counters.endCount).toBe(0);
  expect(debugEventCount(counters, 'pc.media_reconnect.scheduled')).toBe(1);

  await page.clock.fastForward(100);
  await expect.poll(() => counters.offerCount).toBe(2);
  expect(counters.endCount).toBe(0);
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();
  assertNoBrowserErrors();
});

test('recovers and ends after the reconnect attempt limit gives up', async ({
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
  await page.evaluate(
    ({ connectionState, iceConnectionState }) => {
      const target = window as Window & {
        __raymeMockPeerConnections?: Array<{
          setMockConnectionState: (
            connectionState: RTCPeerConnectionState,
            iceConnectionState?: RTCIceConnectionState
          ) => void;
        }>;
      };
      const peer = target.__raymeMockPeerConnections?.at(-1);
      if (!peer) {
        throw new Error('No mock peer connection is available');
      }
      peer.setMockConnectionState(connectionState, iceConnectionState);
    },
    { connectionState, iceConnectionState }
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

async function getMockCallMediaSnapshot(page: Page): Promise<MockCallMediaSnapshot> {
  return page.evaluate(() => {
    const target = window as Window & {
      __raymeMockPeerConnections?: Array<{
        id: number;
        connectionState: RTCPeerConnectionState;
        iceConnectionState: RTCIceConnectionState;
        createdOfferCount: number;
        closed: boolean;
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
    };

    return {
      peers: (target.__raymeMockPeerConnections ?? []).map((peer) => ({
        id: peer.id,
        connectionState: peer.connectionState,
        iceConnectionState: peer.iceConnectionState,
        createdOfferCount: peer.createdOfferCount,
        closed: peer.closed,
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
      }))
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
    offers: [],
    backfills: [],
    recoveredEvents: [],
    turns: [],
    requestOrder: [],
    debugEvents: []
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
    counters.offers.push({
      peerId: readMockPeerIdFromSdp(sdp),
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
    await fulfillJson(route, {
      call_id: 'call-reconnect-01',
      session_id: 'rtc-call-reconnect-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
  await page.route('**/api/calls/*/reconnect-audio', async (route) => {
    counters.backfillCount += 1;
    counters.requestOrder.push('backfill');
    counters.backfills.push(route.request().postDataJSON() as Record<string, unknown>);
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
      default_engine: 'f5',
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
  await page.route('**/api/calls/start', async (route: Route) => {
    expect(route.request().method()).toBe('POST');
    counters.startCount += 1;
    counters.requestOrder.push('start');
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      thread_id: threadId,
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
      event_channel: 'rayme-events'
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
    await fulfillJson(route, { muted: true });
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
