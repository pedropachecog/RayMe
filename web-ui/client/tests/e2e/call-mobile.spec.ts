import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-mobile-thread';

test.describe('mobile-chromium call path', () => {
  test('keeps call controls visible above bottom navigation on mobile', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile-chromium', 'mobile-chromium only');
    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    await installMobileRoutes(page);

    await page.goto(`/chat/${threadId}`);
    await page.getByRole('button', { name: 'Start call' }).click();

    const toolbar = page.getByTestId('call-toolbar');
    const bottomNavigation = page.getByTestId('bottom-navigation');
    await expect(toolbar.getByRole('button', { name: 'Mute' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'Interrupt' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'End Call' })).toBeVisible();

    const toolbarBox = await toolbar.boundingBox();
    const navBox = await bottomNavigation.boundingBox();
    expect(toolbarBox).not.toBeNull();
    expect(navBox).not.toBeNull();
    expect(toolbarBox!.y + toolbarBox!.height).toBeLessThanOrEqual(navBox!.y);
    assertNoBrowserErrors();
  });
});

async function installMobileRoutes(page: Page) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, makeThreadDetail({
      id: threadId,
      title: 'Mobile Thread',
      character_name: 'Mobile Aster',
      messages: []
    }));
  });
  await page.route('**/api/calls', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-mobile-01',
      thread_id: threadId,
      state: 'speaking'
    }, 201);
  });
  await page.route('**/webrtc/offer', async (route) => {
    await fulfillJson(route, { type: 'answer', sdp: 'v=0\r\n' });
  });
}
