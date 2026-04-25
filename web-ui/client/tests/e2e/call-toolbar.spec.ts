import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-toolbar-thread';
const inputPickerCopy =
  'Input selection is not available in this browser. RayMe will use the current microphone.';
const outputPickerCopy =
  'Output selection is not available in this browser. RayMe will use the browser default output.';

test('call toolbar exposes mute, interrupt, device picker fallback, and end controls', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installActiveCallRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByRole('button', { name: 'Mute' })).toBeVisible();
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByRole('button', { name: 'Unmute' })).toBeVisible();

  await expect(page.getByTestId('voice-visualizer').getByText('Thinking')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Interrupt' })).toBeVisible();
  await page.getByRole('button', { name: 'Interrupt' }).click();
  await expect(page.getByTestId('voice-visualizer').getByText('Listening')).toBeVisible();

  await expect(page.getByText(inputPickerCopy)).toBeVisible();
  await expect(page.getByText(outputPickerCopy)).toBeVisible();
  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('button', { name: 'Return to Thread' })).toBeVisible();
  assertNoBrowserErrors();
});

async function installActiveCallRoutes(page: Page) {
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
    await fulfillJson(route, { state: 'listening' });
  });
  await page.route('**/api/calls/*/end', async (route) => {
    await fulfillJson(route, {
      state: 'ended',
      duration_ms: 12_000
    });
  });
  await page.route('**/webrtc/offer', async (route) => {
    await fulfillJson(route, { type: 'answer', sdp: 'v=0\r\n' });
  });
}
