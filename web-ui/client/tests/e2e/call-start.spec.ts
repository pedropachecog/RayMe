import { expect, test, type Page, type Route } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard, installCallDebugEventRoute, installMockCallMedia } from './helpers/acceptance';
import { makeCharacter, makeThreadDetail } from './helpers/fixtures';

const characterId = 'call-start-character';
const threadId = 'call-start-thread';

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
  await expect(page.getByRole('button', { name: 'Return to Thread' })).toBeVisible();
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

async function installCallStartRoutes(page: Page, options: { failOffer?: boolean } = {}) {
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
    await fulfillJson(route, {
      call_id: 'call-start-01',
      session_id: 'rtc-call-start-01',
      thread_id: threadId,
      state: 'listening'
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
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
  await page.route('**/api/calls/*/end', async (route) => {
    await fulfillJson(route, { call_id: 'call-start-01', session_id: 'rtc-call-start-01', reason: 'setup_failed' });
  });
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
