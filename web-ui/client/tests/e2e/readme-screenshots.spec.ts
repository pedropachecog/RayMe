import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  fulfillSse,
  installBrowserErrorGuard,
  installCallDebugEventRoute,
  installMockCallMedia
} from './helpers/acceptance';
import { makeCharacter, makeThreadDetail } from './helpers/fixtures';

/**
 * Captures README screenshots from the LIVE running SvelteKit client.
 *
 * Playwright's `webServer` config builds the real client with `npm run build`
 * and serves it at http://127.0.0.1:4173 before this spec runs, so every
 * `page.screenshot` here is a real browser render of the production build --
 * not a `docs/stitch` design mockup.
 *
 * The Python `web-ui/server` backend is not booted; `/api/*` calls are mocked
 * with `page.route` (the established pattern across this repo's E2E specs) so
 * the live build renders realistic, populated content.
 */

const SPEC_DIR = dirname(fileURLToPath(import.meta.url));
// Spec lives at web-ui/client/tests/e2e/ -> repo root is four levels up.
const SCREENSHOT_DIR = resolve(SPEC_DIR, '../../../../docs/screenshots');

const DESKTOP_VIEWPORT = { width: 1280, height: 800 };

function screenshotPath(name: string): string {
  return resolve(SCREENSHOT_DIR, name);
}

const galleryCharacter = makeCharacter({
  id: 'readme-aster',
  name: 'Aster',
  description: 'A warm, attentive conversational companion you can call.',
  tags: ['featured'],
  portrait_url: null
});

const secondCharacter = makeCharacter({
  id: 'readme-nova',
  name: 'Nova',
  description: 'An imported SillyTavern card ready for a live phone call.',
  tags: ['imported'],
  portrait_url: null
});

const recentThreads = [
  {
    id: 'readme-thread-call',
    character_id: galleryCharacter.id,
    title: 'Evening check-in with Aster',
    character_name: 'Aster',
    character_portrait_url: null,
    last_message_snippet: 'Call ended - 4 min 12 sec. Talk again soon.',
    last_message_at: '2026-05-22T19:04:00Z',
    created_at: '2026-05-22T18:59:00Z',
    updated_at: '2026-05-22T19:04:00Z'
  },
  {
    id: 'readme-thread-text',
    character_id: secondCharacter.id,
    title: 'Planning the weekend with Nova',
    character_name: 'Nova',
    character_portrait_url: null,
    last_message_snippet: 'Sounds good - let me know when you want to talk it through.',
    last_message_at: '2026-05-21T21:12:00Z',
    created_at: '2026-05-21T20:40:00Z',
    updated_at: '2026-05-21T21:12:00Z'
  }
];

async function captureScreenshot(page: Page, name: string) {
  await page.screenshot({ path: screenshotPath(name), fullPage: true });
}

test.describe('README live screenshots', () => {
  test.beforeAll(async () => {
    await mkdir(SCREENSHOT_DIR, { recursive: true });
  });

  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'desktop-chromium',
      'README screenshots are captured once, on the desktop project only.'
    );
  });

  test('captures the live home screen', async ({ page }) => {
    const expectNoBrowserErrors = installBrowserErrorGuard(page);

    await page.route('**/api/threads', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillJson(route, { items: recentThreads });
        return;
      }
      await route.fallback();
    });
    await page.route('**/api/characters', async (route) => {
      await fulfillJson(route, { items: [galleryCharacter, secondCharacter] });
    });

    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto('/');

    await expect(page.getByRole('heading', { level: 1, name: 'RayMe' })).toBeVisible();
    await expect(page.getByText('Evening check-in with Aster')).toBeVisible();

    await captureScreenshot(page, 'home.png');
    await expectNoBrowserErrors();
  });

  test('captures the live character gallery', async ({ page }) => {
    const expectNoBrowserErrors = installBrowserErrorGuard(page);

    await page.route('**/api/characters', async (route) => {
      await fulfillJson(route, { items: [galleryCharacter, secondCharacter] });
    });
    await page.route('**/api/threads', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillJson(route, { items: recentThreads });
        return;
      }
      await route.fallback();
    });

    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto('/gallery');

    await expect(page.getByRole('heading', { level: 1, name: 'Character Gallery' })).toBeVisible();
    await expect(page.getByTestId('character-card-readme-aster')).toBeVisible();

    await captureScreenshot(page, 'gallery.png');
    await expectNoBrowserErrors();
  });

  test('captures the live call screen', async ({ page }) => {
    const expectNoBrowserErrors = installBrowserErrorGuard(page);

    const callThreadId = 'readme-call-thread';
    const callThread = makeThreadDetail({
      id: callThreadId,
      character_id: galleryCharacter.id,
      title: 'Evening check-in with Aster',
      character_name: 'Aster',
      character_portrait_url: null,
      character_portrait_asset_id: null,
      character_portrait_storage_path: null,
      messages: []
    });

    const exchanges = [
      {
        userText: "Hey Aster -- I'm finally trying a real call instead of texting.",
        aiText: "It's so good to actually hear your voice. Take your time -- I'm listening."
      },
      {
        userText: 'Honestly, the live captions make this feel a lot less nerve-wracking.',
        aiText: "That's exactly why they're here. Whenever you're ready, just keep talking."
      }
    ];

    await installMockCallMedia(page);
    await installCallDebugEventRoute(page);

    await page.route('**/api/threads/*', async (route) => {
      await fulfillJson(route, callThread);
    });
    await page.route('**/api/characters/*/portrait**', async (route) => {
      await route.fulfill({ status: 204 });
    });
    await page.route('**/api/calls/start', async (route) => {
      await fulfillJson(
        route,
        {
          call_id: 'readme-call-01',
          session_id: 'rtc-readme-call-01',
          thread_id: callThreadId,
          state: 'listening',
          events: exchanges.map((exchange, index) => ({
            type: 'user_final',
            session_id: 'rtc-readme-call-01',
            turn_id: `readme-turn-${index + 1}`,
            text: exchange.userText
          }))
        },
        201
      );
    });
    await page.route('**/api/calls/*/offer', async (route) => {
      await fulfillJson(route, {
        call_id: 'readme-call-01',
        session_id: 'rtc-readme-call-01',
        answer: { type: 'answer', sdp: 'v=0\r\n' },
        event_channel: 'rayme-events'
      });
    });
    let turnIndex = 0;
    await page.route('**/api/calls/*/turns', async (route) => {
      const exchange = exchanges[Math.min(turnIndex, exchanges.length - 1)];
      const turnId = `readme-turn-${turnIndex + 1}`;
      turnIndex += 1;
      await fulfillSse(route, [
        { type: 'ai_audio_started', turn_id: turnId, audio: { duration_ms: 1800, samples: 28800 } },
        { type: 'ai_token', turn_id: turnId, text: exchange.aiText },
        { type: 'ai_done', turn_id: turnId }
      ]);
    });
    await page.route('**/api/calls/*/end', async (route) => {
      await fulfillJson(route, { state: 'ended' });
    });

    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto(`/chat/${callThreadId}`);
    await page.getByRole('button', { name: 'Start call' }).click();

    await expect(page.getByTestId('voice-visualizer')).toBeVisible();
    await expect(page.getByText(exchanges[0].userText)).toBeVisible();
    await expect(page.getByText(exchanges[exchanges.length - 1].aiText)).toBeVisible();

    await captureScreenshot(page, 'call.png');
    await expectNoBrowserErrors();
  });
});
