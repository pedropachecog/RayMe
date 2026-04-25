import { expect, test, type Page, type Route } from '@playwright/test';

import { installBrowserErrorGuard } from './helpers/acceptance';

const forbiddenCopy = [
  'Account',
  'Billing',
  'Logout',
  'Voice model',
  'Voice controls',
  'Wake word',
  'Search',
  'Filter',
  'Subscription',
  'Screen awareness',
  'VAD sensitivity'
] as const;

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

async function installContractRoutes(page: Page) {
  const character = {
    id: 'contract-character',
    name: 'Contract Aster',
    description: 'Sanitized contract character.',
    first_mes: 'Contract opening.',
    alternate_greetings: [],
    tags: ['contract'],
    lorebook_json: null,
    deleted_at: null,
    updated_at: null,
    portrait_url: null
  };

  await page.route('**/api/threads', async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: 'contract-thread',
          character_id: character.id,
          title: 'Contract thread',
          character_name: character.name,
          last_message_snippet: 'A recent text-only message.',
          last_message_at: '2026-04-24T00:00:00Z',
          created_at: '2026-04-24T00:00:00Z',
          updated_at: '2026-04-24T00:00:00Z'
        }
      ]
    });
  });
  await page.route('**/api/characters', async (route) => {
    await fulfillJson(route, { items: [character] });
  });
  await page.route('**/api/characters/contract-character', async (route) => {
    await fulfillJson(route, character);
  });
  await page.route('**/api/threads/contract-thread', async (route) => {
    await fulfillJson(route, {
      id: 'contract-thread',
      character_id: character.id,
      title: 'Contract thread',
      character_name: character.name,
      character_portrait_url: null,
      character_snapshot: { name: character.name, first_mes: character.first_mes },
      messages: [
        {
          id: 'contract-opening',
          thread_id: 'contract-thread',
          message_kind: 'ai_text',
          role: 'assistant',
          sequence: 0,
          content_text: 'Contract opening.',
          selected_alternate_id: 'contract-opening-alt',
          alternates: [
            {
              id: 'contract-opening-alt',
              message_id: 'contract-opening',
              alternate_index: 0,
              content_text: 'Contract opening.',
              source_action: 'first_mes',
              created_at: null
            }
          ],
          stale_after_edit: false,
          created_at: null,
          updated_at: null
        }
      ]
    });
  });
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, {
      web_url: 'https://192.168.1.199:8443',
      ai_backend_url: 'https://192.168.1.199:9443',
      llm_base_url: 'https://api.openai.com/v1',
      llm_model: 'gpt-4.1-mini',
      llm_api_key_configured: true
    });
  });
}

async function expectNoFutureControls(page: Page) {
  for (const label of forbiddenCopy) {
    await expect(page.getByText(new RegExp(`\\b${label}\\b`, 'i'))).toHaveCount(0);
    await expect(page.getByRole('button', { name: new RegExp(label, 'i') })).toHaveCount(0);
    await expect(page.getByRole('link', { name: new RegExp(label, 'i') })).toHaveCount(0);
  }
}

test('phase 2 ui exposes Voice Lab navigation without call controls', async ({ page }) => {
  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  await installContractRoutes(page);

  for (const path of ['/', '/gallery', '/settings', '/characters/contract-character', '/chat/contract-thread']) {
    await page.goto(path);
    await expectNoFutureControls(page);
  }

  await page.goto('/');
  await expect(page.locator('nav[aria-label="Top-level"] a')).toHaveCount(4);
  await expect(page.locator('nav[aria-label="Primary mobile"] a')).toHaveCount(4);
  await expect(page.getByRole('link', { name: 'Home' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Gallery' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Voice Lab' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Settings' }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start Chat' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /^Call$/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Call$/i })).toHaveCount(0);
  await expectNoBrowserErrors();
});
