import { Buffer } from 'node:buffer';

import type { Page } from '@playwright/test';

const PORTRAIT_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';
const ALTERNATE_PORTRAIT_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/l6Y2YQAAAABJRU5ErkJggg==';

export function portraitPng() {
  return Buffer.from(PORTRAIT_PNG_BASE64, 'base64');
}

export function alternatePortraitPng() {
  return Buffer.from(ALTERNATE_PORTRAIT_PNG_BASE64, 'base64');
}

export async function fulfillPortraitImage(page: Page, portraitUrl: string, body = portraitPng()) {
  await page.route(`**${portraitUrl}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'image/png' },
      body
    });
  });
}
