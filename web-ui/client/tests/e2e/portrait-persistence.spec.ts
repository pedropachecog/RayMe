import { expect, test } from '@playwright/test';

import {
  expectRayMeApiRequest,
  fulfillJson,
  installBrowserErrorGuard
} from './helpers/acceptance';
import { makeAiMessage, makeCharacter, makeThreadDetail } from './helpers/fixtures';
import { fulfillPortraitImage, portraitPng } from './helpers/images';

test('PNG import persists portrait across Editor Gallery Home Chat and reload', async ({ page }) => {
  const assertNoBrowserErrors = installBrowserErrorGuard(page);
  page.on('request', expectRayMeApiRequest);

  await fulfillPortraitImage(
    page,
    '/api/characters/portrait-import-character/portrait?asset_id=portrait-import-asset',
    portraitPng()
  );
  await page.route('**/api/characters/import', async (route) => {
    await fulfillJson(route, {
      character: makeCharacter({
        id: 'portrait-import-character',
        name: 'Portrait Import Aster',
        portrait_asset_id: 'portrait-import-asset',
        portrait_url:
          '/api/characters/portrait-import-character/portrait?asset_id=portrait-import-asset'
      }),
      source_format: 'v3_png',
      warnings: []
    });
  });
  makeAiMessage('portrait-import-message', 'portrait-import-thread');
  makeThreadDetail({ id: 'portrait-import-thread' });

  await expect(page.getByTestId('character-card-portrait-import-character')).toHaveCount(1);
  await expect(page.getByTestId('thread-row-portrait-import-thread')).toHaveCount(1);
  await expect(page.locator('.chat-header .portrait img')).toHaveCount(1);
  assertNoBrowserErrors();
});
