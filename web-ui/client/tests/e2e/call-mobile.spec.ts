import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBrowserErrorGuard } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-mobile-thread';

test.describe('mobile-chromium call path', () => {
  test('keeps call controls visible above bottom navigation on mobile', async ({ page }, testInfo) => {
    if (testInfo.project.name !== 'mobile-chromium') {
      return;
    }

    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    await installMobileRoutes(page);

    await page.goto(`/chat/${threadId}`);
    await page.getByRole('button', { name: 'Start call' }).click();

    const toolbar = page.getByTestId('call-toolbar');
    const bottomNavigation = page.getByTestId('bottom-navigation');
    await expect(toolbar.getByRole('button', { name: 'Mute' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'Interrupt' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'End Call' })).toBeVisible();
    await expect(toolbar.getByRole('combobox').first()).toBeVisible();
    await expect(toolbar.getByRole('combobox').nth(1)).toBeVisible();

    const toolbarBox = await toolbar.boundingBox();
    const navBox = await bottomNavigation.boundingBox();
    expect(toolbarBox).not.toBeNull();
    expect(navBox).not.toBeNull();
    expect(toolbarBox!.y + toolbarBox!.height).toBeLessThanOrEqual(navBox!.y);

    for (const control of [
      toolbar.getByRole('button', { name: 'Mute' }),
      toolbar.getByRole('button', { name: 'Interrupt' }),
      toolbar.getByRole('button', { name: 'End Call' }),
      toolbar.getByRole('combobox').first(),
      toolbar.getByRole('combobox').nth(1)
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.y + box!.height).toBeLessThanOrEqual(navBox!.y);
    }
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
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-mobile-01',
      session_id: 'rtc-call-mobile-01',
      thread_id: threadId,
      state: 'speaking'
    }, 201);
  });
  await page.route('**/webrtc/offer', async (route) => {
    await fulfillJson(route, { type: 'answer', sdp: 'v=0\r\n' });
  });
}
