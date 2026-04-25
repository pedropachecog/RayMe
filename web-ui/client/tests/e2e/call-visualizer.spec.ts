import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard, installMockCallMedia } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-visualizer-thread';

test('voice visualizer reflects Listening, Thinking, and Speaking call states', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  await installMockCallMedia(page);
  await installVisualizerRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  const visualizer = page.getByTestId('voice-visualizer');
  await expect(visualizer).toBeVisible();
  await expect(visualizer.getByText('Listening')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'listening');
  await expect(visualizer).toHaveAttribute('data-listening-rms', /0\.[1-9]/);

  await expect(visualizer.getByText('Thinking')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'thinking');

  await expect(visualizer.getByText('Speaking')).toBeVisible();
  await expect(visualizer).toHaveAttribute('data-call-state', 'speaking');
  await expect(visualizer).toHaveAttribute('data-speaking-rms', /0\.[1-9]/);
  assertNoBrowserErrors();
});

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
