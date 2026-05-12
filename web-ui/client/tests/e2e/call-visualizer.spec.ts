import { expect, test, type Locator, type Page } from '@playwright/test';

import {
  fulfillJson,
  installBrowserErrorGuard,
  installCallDebugEventRoute,
  installMockCallMedia
} from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-visualizer-thread';

test('voice visualizer reflects Listening, Understanding, Composing, and Speaking call states', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installCallDebugEventRoute(page);
  await installVisualizerRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  const visualizer = page.getByTestId('voice-visualizer');
  await expect(visualizer).toBeVisible();
  await expect(visualizer.getByText('Listening')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'listening');
  await expect.poll(() => readNumericAttribute(visualizer, 'data-listening-rms')).toBeGreaterThan(0);
  expect(await readNumericAttribute(visualizer, 'data-listening-rms')).toBeLessThanOrEqual(1);

  await expect(visualizer.getByText('Understanding')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'understanding');

  await expect(visualizer.getByText('Composing')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'thinking');

  await expect(visualizer.getByText('Speaking')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'speaking');
  await expect.poll(() => readNumericAttribute(visualizer, 'data-speaking-rms')).toBeGreaterThan(0);
  expect(await readNumericAttribute(visualizer, 'data-speaking-rms')).toBeLessThanOrEqual(1);
  assertNoBrowserErrors();
});

async function readNumericAttribute(
  locator: Locator,
  attributeName: string
) {
  return Number(await locator.getAttribute(attributeName));
}

async function installVisualizerRoutes(page: Page) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, makeThreadDetail({
      id: threadId,
      title: 'Visualizer Thread',
      character_name: 'Visualizer Aster',
      messages: []
    }));
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-visualizer-01',
      session_id: 'rtc-call-visualizer-01',
      thread_id: threadId,
      state: 'listening',
      events: [
        { type: 'state', state: 'Listening', listeningRms: 0.2 },
        { type: 'state', state: 'Understanding' },
        { type: 'state', state: 'Thinking' },
        { type: 'state', state: 'Speaking', speakingRms: 0.4 }
      ]
    }, 201);
  });
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-visualizer-01',
      session_id: 'rtc-call-visualizer-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
}
