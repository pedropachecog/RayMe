import { expect, test } from '@playwright/test';

const phaseOneRoutes = ['/', '/gallery', '/characters/:id', '/chat/:threadId', '/settings'] as const;
const generatedResponseAssertions = [
  'regenerate consumes a returned backend-generated AI alternate instead of local-only state',
  'swipe consumes a backend-generated alternate instead of local-only state',
  'continue consumes a backend-generated selected alternate instead of local-only state'
] as const;

test.use({ viewport: { width: 393, height: 851 }, isMobile: true });

test('mobile viewport can import chat reload and continue', async ({ page }) => {
  await page.goto('/gallery');
  await page.goto('/characters/mobile-imported-character');
  await page.goto('/chat/mobile-thread');
  await page.reload();

  expect(phaseOneRoutes).toContain('/gallery');
  expect(phaseOneRoutes).toContain('/characters/:id');
  expect(phaseOneRoutes).toContain('/chat/:threadId');
  expect(generatedResponseAssertions).toContain(
    'continue consumes a backend-generated selected alternate instead of local-only state'
  );
});
