import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installBrowserErrorGuard,
  installCallDebugEventRoute,
  installMockCallMedia
} from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-toolbar-thread';
const inputPickerCopy =
  'Input selection is not available in this browser. RayMe will use the current microphone.';
const outputPickerCopy =
  'Output selection is not available in this browser. RayMe will use the browser default output.';

test('call toolbar exposes mute, interrupt, device picker fallback, and end controls', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const debugEvents: Array<{ event?: string; detail?: Record<string, unknown> }> = [];
  let releaseInterruptResponse = () => undefined;
  const interruptResponseGate = new Promise<void>((resolve) => {
    releaseInterruptResponse = resolve;
  });
  await installMockCallMedia(page);
  await installCallDebugEventRoute(page, (event) => debugEvents.push(event));
  await installActiveCallRoutes(page, interruptResponseGate);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible();

  await emitCallEvent(page, {
    type: 'ai_audio_started',
    session_id: 'rtc-call-toolbar-01',
    turn_id: 'turn-before-interrupt'
  });
  await expect(page.getByTestId('voice-visualizer').getByText('Speaking')).toBeVisible();
  await page.getByRole('button', { name: 'More call options' }).click();
  await expect(page.getByRole('button', { name: 'Interrupt' })).toBeVisible();
  await page.getByRole('button', { name: 'Interrupt' }).click();
  await expect.poll(() => debugEvents.some((event) =>
    event.event === 'remote_audio.audibility' &&
    event.detail?.muted === true &&
    event.detail?.policy === 'interrupt-drain'
  )).toBe(true);
  await emitCallEvent(page, {
    type: 'interrupted',
    session_id: 'rtc-call-toolbar-01',
    cancelled_turn_id: 'turn-before-interrupt',
    receiver_drain_ms: 120
  });
  await expect.poll(() => debugEvents.filter(
    (event) => event.event === 'remote_audio.interrupt_drain.acknowledged' &&
      event.detail?.source === 'data-channel'
  ).length).toBe(1);
  expect(debugEvents.filter(
    (event) => event.event === 'remote_audio.interrupt_drain.started'
  )).toHaveLength(1);

  await emitCallEvent(page, {
    type: 'ai_audio_started',
    session_id: 'rtc-call-toolbar-01',
    turn_id: 'turn-after-interrupt'
  });
  await expect(page.getByTestId('voice-visualizer').getByText('Speaking')).toBeVisible();
  await expect.poll(() => debugEvents.filter(
    (event) => event.event === 'remote_audio.audibility' &&
      event.detail?.muted === false &&
      event.detail?.policy === 'audible'
  ).length).toBe(1);

  await emitCallEvent(page, {
    type: 'interrupted',
    session_id: 'rtc-call-toolbar-01',
    receiver_drain_ms: 120
  });

  releaseInterruptResponse();
  await page.waitForTimeout(350);
  expect(debugEvents.filter(
    (event) => event.event === 'remote_audio.interrupt_drain.started'
  )).toHaveLength(1);
  expect(debugEvents.filter(
    (event) => event.event === 'remote_audio.audibility' && event.detail?.muted === true
  )).toHaveLength(1);
  await expect(page.getByTestId('voice-visualizer').getByText('Speaking')).toBeVisible();

  await page.getByRole('button', { name: 'More call options' }).click();
  await expect(page.getByText(inputPickerCopy)).toBeVisible();
  await expect(page.getByText(outputPickerCopy)).toBeVisible();
  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('button', { name: 'Return to Thread' })).toBeVisible();
  assertNoBrowserErrors();
});

async function emitCallEvent(page: Page, event: Record<string, unknown>) {
  await page.evaluate((payload) => {
    const channels = (
      window as Window & {
        __raymeMockDataChannels?: Array<{ emitMockMessage: (data: string) => void }>;
      }
    ).__raymeMockDataChannels ?? [];
    channels[channels.length - 1]?.emitMockMessage(JSON.stringify(payload));
  }, event);
}

async function installActiveCallRoutes(page: Page, interruptResponseGate: Promise<void>) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, makeThreadDetail({
      id: threadId,
      title: 'Toolbar Thread',
      character_name: 'Toolbar Aster',
      messages: []
    }));
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-toolbar-01',
      session_id: 'rtc-call-toolbar-01',
      thread_id: threadId,
      state: 'thinking'
    }, 201);
  });
  await page.route('**/api/calls/*/mute', async (route) => {
    await fulfillJson(route, { serverMuted: true, state: 'listening' });
  });
  await page.route('**/api/calls/*/interrupt', async (route) => {
    await interruptResponseGate;
    await fulfillJson(route, {
      call_id: 'call-toolbar-01',
      session_id: 'rtc-call-toolbar-01',
      interrupted: true,
      cancelled_turn_id: 'turn-before-interrupt',
      receiver_drain_ms: 120,
      state: 'listening'
    });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    await fulfillJson(route, {
      state: 'ended',
      duration_ms: 12_000
    });
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-toolbar-01',
      session_id: 'rtc-call-toolbar-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
}
