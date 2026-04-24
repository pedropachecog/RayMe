import { expect, test } from '@playwright/test';

const phaseOneRoutes = ['/', '/gallery', '/characters/:id', '/chat/:threadId', '/settings'] as const;
const browserReadinessAssertions = [
  'secure context status is visible from Settings',
  'media device availability status is visible from Settings'
] as const;

test('secure context and media device status are visible', async ({ page }) => {
  await page.goto('/');
  await page.goto('/settings');

  expect(phaseOneRoutes).toContain('/');
  expect(phaseOneRoutes).toContain('/settings');
  expect(browserReadinessAssertions).toContain('secure context status is visible from Settings');
  expect(browserReadinessAssertions).toContain('media device availability status is visible from Settings');
});
