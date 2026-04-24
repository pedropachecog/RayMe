import { expect, test, type Route } from '@playwright/test';

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

test('secure context media readiness and endpoint statuses are visible', async ({ page }) => {
  await page.addInitScript(() => {
    try {
      Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    } catch {
      // Chromium already treats localhost as a secure context.
    }
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { enumerateDevices: async () => [] },
      configurable: true
    });
  });

  await page.route('**/api/settings', async (route) => {
    expect(route.request().method()).toBe('GET');
    await fulfillJson(route, {
      web_url: 'https://192.168.1.199:8443',
      ai_backend_url: 'https://192.168.1.199:9443',
      llm_base_url: 'https://api.openai.com/v1',
      llm_model: 'gpt-4.1-mini',
      llm_api_key_configured: true
    });
  });
  await page.route('**/api/settings/test/web', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, { status: 'Connected' });
  });
  await page.route('**/api/settings/test/ai-backend', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, { status: 'Connected' });
  });
  await page.route('**/api/settings/test/llm', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, { status: 'Connected' });
  });

  await page.goto('/settings');

  await expect(page.getByText('Secure context').first()).toBeVisible();
  await expect(page.getByText('Media devices available')).toBeVisible();
  await expect(page.locator('[data-testid="web-ui-status"]')).toHaveText('Connected');
  await expect(page.locator('[data-testid="ai-backend-status"]')).toHaveText('Not configured');
  await expect(page.locator('[data-testid="llm-status"]')).toHaveText('Not configured');
  await expect(page.getByPlaceholder('API key configured')).toHaveAttribute('type', 'password');
  await expect(page.getByText(/server-secret|sk-/i)).toHaveCount(0);

  await page
    .locator('section[aria-labelledby="ai-backend-title"]')
    .getByRole('button', { name: 'Test Connection' })
    .click();
  await expect(page.locator('[data-testid="ai-backend-status"]')).toHaveText('Connected');

  await page
    .locator('section[aria-labelledby="llm-title"]')
    .getByRole('button', { name: 'Test Connection' })
    .click();
  await expect(page.locator('[data-testid="llm-status"]')).toHaveText('Connected');
});
