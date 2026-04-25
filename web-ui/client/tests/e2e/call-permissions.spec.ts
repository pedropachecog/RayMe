import { expect, test, type Page } from '@playwright/test';

import { fulfillJson, installBlockedCallMicrophone, installBrowserErrorGuard } from './helpers/acceptance';
import { makeThreadDetail } from './helpers/fixtures';

const threadId = 'call-permissions-thread';
const micBlockedCopy = 'Microphone access is blocked. Allow microphone access in Chrome, then retry.';

test('microphone denial shows public recovery copy and retry action', async ({ context, page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page, {
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 403/]
  });
  await installBlockedCallMicrophone(page);
  await context.grantPermissions([], { origin: 'http://127.0.0.1:4173' });
  await installPermissionRoutes(page);

  await page.goto(`/chat/${threadId}`);
  await page.getByRole('button', { name: 'Start call' }).click();

  await expect(page.getByText(micBlockedCopy)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry Microphone' })).toBeVisible();
  await expect(page.getByText(/DOMException|NotAllowedError|Traceback|stack trace/i)).toHaveCount(0);
  assertNoBrowserErrors();
});

async function installPermissionRoutes(page: Page) {
  await page.route(`**/api/threads/${threadId}`, async (route) => {
    await fulfillJson(route, makeThreadDetail({
      id: threadId,
      title: 'Permissions Thread',
      character_name: 'Permissions Aster',
      messages: []
    }));
  });
  await page.route('**/api/characters/*/portrait**', async (route) => {
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/calls/start', async (route) => {
    await fulfillJson(route, {
      detail: {
        code: 'microphone_blocked',
        message: micBlockedCopy
      }
    }, 403);
  });
}
