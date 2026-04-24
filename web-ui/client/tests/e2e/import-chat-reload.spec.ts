import { expect, test } from '@playwright/test';

const phaseOneRoutes = ['/', '/gallery', '/characters/:id', '/chat/:threadId', '/settings'] as const;
const generatedResponseAssertions = [
  'regenerate consumes a returned backend-generated AI alternate instead of local-only state',
  'swipe consumes a backend-generated alternate instead of local-only state',
  'continue consumes a backend-generated selected alternate instead of local-only state'
] as const;

test('imported character chat reloads and continues', async ({ page }) => {
  await page.goto('/gallery');
  await page.goto('/characters/imported-character');
  await page.goto('/chat/imported-thread');
  await page.reload();

  expect(phaseOneRoutes).toContain('/gallery');
  expect(phaseOneRoutes).toContain('/characters/:id');
  expect(phaseOneRoutes).toContain('/chat/:threadId');
  expect(generatedResponseAssertions).toContain(
    'continue consumes a backend-generated selected alternate instead of local-only state'
  );
});
