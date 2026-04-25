import { expect, test, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';

const canonicalLiveWebUrl = 'https://192.168.1.199:8443';
const canonicalLiveAiHealthUrl = 'https://192.168.1.199:9443/health';

const liveEnabled = process.env.RAYME_ENABLE_LIVE_E2E === '1';
const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;

test.skip(
  !liveEnabled || !liveWebUrl || !liveAiHealthUrl,
  'Set RAYME_ENABLE_LIVE_E2E=1, RAYME_LIVE_WEB_URL, and RAYME_LIVE_AI_HEALTH_URL to run live call acceptance.'
);

test.use({ ignoreHTTPSErrors: true });

test('live OMEN-PC browser call completes two user to AI cycles without mocked call media', async ({
  page
}) => {
  test.setTimeout(300_000);
  expect(liveWebUrl).toBe(canonicalLiveWebUrl);
  expect(liveAiHealthUrl).toBe(canonicalLiveAiHealthUrl);

  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  const liveEvents: string[] = [];

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    recordLiveCallRequest(request, liveEvents);
  });

  const healthResponse = await page.goto(canonicalLiveAiHealthUrl);
  expect(healthResponse?.ok(), `AI backend health at ${canonicalLiveAiHealthUrl}`).toBe(true);
  await expect(page.locator('body')).toContainText(/ok|healthy|status/i);

  await page.goto(`${canonicalLiveWebUrl}/`);
  await page.getByRole('button', { name: 'Start Call' }).first().click();
  await expect(page.getByText('Listening')).toBeVisible({ timeout: 60_000 });

  await page.getByTestId('live-call-mic-script').fill('First live call turn.');
  await page.getByRole('button', { name: 'Send Live Utterance' }).click();
  await expect(page.getByText('Speaking')).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/First live call turn\.|AI:/)).toBeVisible({ timeout: 120_000 });

  await page.getByTestId('live-call-mic-script').fill('Second live call turn.');
  await page.getByRole('button', { name: 'Send Live Utterance' }).click();
  await expect(page.getByText('Speaking')).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/Second live call turn\.|AI:/)).toBeVisible({ timeout: 120_000 });

  await page.getByRole('button', { name: 'End Call' }).click();
  await expect(page.getByRole('button', { name: 'Return to Thread' })).toBeVisible({ timeout: 60_000 });
  expect(liveEvents).toEqual(
    expect.arrayContaining([
      expect.stringMatching(/^POST \/api\/calls/),
      expect.stringMatching(/^POST \/webrtc\/offer/),
      expect.stringMatching(/^POST \/api\/calls\/.+\/end$/)
    ])
  );
  assertNoBrowserErrors();
});

function recordLiveCallRequest(request: Request, events: string[]) {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/calls') || url.pathname.startsWith('/webrtc')) {
    events.push(`${request.method()} ${url.pathname}`);
  }
}
