import { Buffer } from 'node:buffer';

import type { Page } from '@playwright/test';

const PORTRAIT_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOoifkPAAMvAdgiKHurAAAAAElFTkSuQmCC';
const ALTERNATE_PORTRAIT_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgePwXAALHAeHvAw8LAAAAAElFTkSuQmCC';

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
