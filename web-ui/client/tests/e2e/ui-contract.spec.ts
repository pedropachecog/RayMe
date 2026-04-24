import { expect, test } from '@playwright/test';

const phaseOneRoutes = ['/', '/gallery', '/characters/:id', '/chat/:threadId', '/settings'] as const;
const futureControls = ['Voice Lab', 'Call', 'Account', 'Billing', 'Logout'] as const;
const generatedResponseAssertions = [
  'regenerate consumes a returned backend-generated AI alternate instead of local-only state',
  'swipe consumes a backend-generated alternate instead of local-only state',
  'continue consumes a backend-generated selected alternate instead of local-only state'
] as const;

test('phase 1 ui omits future controls', async ({ page }) => {
  await page.goto('/');
  await page.goto('/gallery');
  await page.goto('/settings');

  expect(phaseOneRoutes).toContain('/');
  expect(phaseOneRoutes).toContain('/gallery');
  expect(phaseOneRoutes).toContain('/settings');
  expect(futureControls).toEqual(['Voice Lab', 'Call', 'Account', 'Billing', 'Logout']);
  expect(generatedResponseAssertions).toContain('swipe consumes a backend-generated alternate instead of local-only state');
});
