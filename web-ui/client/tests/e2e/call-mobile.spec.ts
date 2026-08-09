import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installBrowserErrorGuard,
  installCallDebugEventRoute,
  installMockCallMedia
} from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-mobile-thread';

test.describe('mobile-chromium call path', () => {
  test('keeps call controls visible above bottom navigation on mobile', async ({ page }, testInfo) => {
    if (testInfo.project.name !== 'mobile-chromium') {
      return;
    }

    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    await page.addInitScript(() => {
      const requests: string[] = [];
      Object.defineProperty(window, '__raymeWakeLockRequests', {
        configurable: true,
        value: requests
      });
      Object.defineProperty(navigator, 'wakeLock', {
        configurable: true,
        value: {
          request: async (type: string) => {
            requests.push(type);
            return {
              released: false,
              addEventListener: () => undefined,
              removeEventListener: () => undefined,
              release: async () => undefined
            };
          }
        }
      });
    });
    await installMockCallMedia(page);
    await installMobileRoutes(page);

    await page.goto(`/chat/${threadId}`);
    await page.getByRole('button', { name: 'Start call' }).click();

    await expect.poll(() => page.evaluate(() => (
      window as Window & { __raymeWakeLockRequests?: string[] }
    ).__raymeWakeLockRequests ?? [])).toEqual(['screen']);

    const toolbar = page.getByTestId('call-toolbar');
    const bottomNavigation = page.getByTestId('bottom-navigation');
    await expect(toolbar.getByTestId('call-ready-state')).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'Mute' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'End Call' })).toBeVisible();
    await expect(toolbar.getByRole('button', { name: 'More call options' })).toBeVisible();

    const toolbarBox = await toolbar.boundingBox();
    const navBox = await bottomNavigation.boundingBox();
    expect(toolbarBox).not.toBeNull();
    expect(navBox).not.toBeNull();
    expect(toolbarBox!.y + toolbarBox!.height).toBeLessThanOrEqual(navBox!.y);

    for (const control of [
      toolbar.getByRole('button', { name: 'Mute' }),
      toolbar.getByRole('button', { name: 'End Call' }),
      toolbar.getByRole('button', { name: 'More call options' })
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.y + box!.height).toBeLessThanOrEqual(navBox!.y);
    }

    await toolbar.getByRole('button', { name: 'More call options' }).click();
    await expect(toolbar.getByRole('button', { name: 'Interrupt' })).toBeVisible();
    await expect(toolbar.getByRole('combobox').first()).toBeVisible();
    await expect(toolbar.getByRole('combobox').nth(1)).toBeVisible();
    assertNoBrowserErrors();
  });

  test('explains when the browser cannot keep the screen awake without ending the call', async ({ page }, testInfo) => {
    if (testInfo.project.name !== 'mobile-chromium') {
      return;
    }

    const assertNoBrowserErrors = installBrowserErrorGuard(page);
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'wakeLock', {
        configurable: true,
        value: {
          request: async () => {
            throw new DOMException('Wake lock denied', 'NotAllowedError');
          }
        }
      });
    });
    await installMockCallMedia(page);
    await installMobileRoutes(page);

    await page.goto(`/chat/${threadId}`);
    await page.getByRole('button', { name: 'Start call' }).click();

    await expect(page.getByTestId('wake-lock-notice')).toHaveText(
      'RayMe could not keep your screen awake. Keep the screen on during this call.'
    );
    await expect(page.getByRole('button', { name: 'End Call' })).toBeVisible();
    assertNoBrowserErrors();
  });
});

async function installMobileRoutes(page: Page) {
  await installCallDebugEventRoute(page);
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
  await page.route('**/api/calls/*/offer', async (route) => {
    await fulfillJson(route, {
      call_id: 'call-mobile-01',
      session_id: 'rtc-call-mobile-01',
      answer: { type: 'answer', sdp: 'v=0\r\n' },
      event_channel: 'rayme-events'
    });
  });
}
