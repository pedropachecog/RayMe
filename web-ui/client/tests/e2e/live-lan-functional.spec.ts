import { expect, test, type Locator, type Page, type Request } from '@playwright/test';

import { expectRayMeApiRequest, installBrowserErrorGuard } from './helpers/acceptance';
import { portraitPng } from './helpers/images';

const missingLiveEnvMessage =
  'RAYME_LIVE_WEB_URL and RAYME_LIVE_AI_HEALTH_URL are required for live LAN E2E';

const liveWebUrl = process.env.RAYME_LIVE_WEB_URL;
const liveAiHealthUrl = process.env.RAYME_LIVE_AI_HEALTH_URL;

if (!liveWebUrl || !liveAiHealthUrl) {
  throw new Error(missingLiveEnvMessage);
}

const webUiUrl = 'https://192.168.1.199:8443';
const aiBackendUrl = 'https://192.168.1.199:9443';
const localLlmUrl = 'http://192.168.1.190:8001/v1';
const localLlmModel = 'unsloth/Qwen3.5-27B';
const liveCharacterPrefix = 'Live Phase 01.1 Portrait';
const selectedAlternateGreeting = 'Live selected alternate greeting.';

test.use({ ignoreHTTPSErrors: true });

test('live OMEN-PC Settings portraits and text flow pass before Android handoff', async ({
  page
}) => {
  test.setTimeout(300_000);

  const expectNoBrowserErrors = installBrowserErrorGuard(page);
  const settingsRequests: string[] = [];
  const characterName = `${liveCharacterPrefix} ${Date.now()}`;

  page.on('request', (request) => {
    expectRayMeApiRequest(request);
    const label = settingsRequestLabel(request);
    if (label) {
      settingsRequests.push(label);
    }
  });

  await verifyLiveHealth(page);
  await verifySettings(page, settingsRequests);

  const characterId = await importLiveCharacter(page, characterName);
  await uploadAndAssertPortrait(page, characterId);
  const threadId = await assertPortraitSurfacesAndStartChat(page, characterId, characterName);
  await runFullTextFlow(page, threadId);

  expectNoBrowserErrors();
});

async function verifyLiveHealth(page: Page) {
  const response = await page.goto(liveAiHealthUrl);
  expect(response?.ok(), `AI backend health at ${liveAiHealthUrl}`).toBe(true);
  await expect(page.locator('body')).toContainText(/ok|healthy|status/i);
}

async function verifySettings(page: Page, completedSettingsRequests: string[]) {
  await page.goto(`${liveWebUrl}/settings`);
  await expect(page.getByRole('heading', { name: 'Endpoint Settings' })).toBeVisible();

  const webSection = page.locator('section[aria-labelledby="web-ui-title"]');
  const aiBackendSection = page.locator('section[aria-labelledby="ai-backend-title"]');
  const llmSection = page.locator('section[aria-labelledby="llm-title"]');

  await webSection.getByLabel('Web UI URL').fill(webUiUrl);
  await aiBackendSection.getByLabel('AI backend URL').fill(aiBackendUrl);
  await llmSection.getByLabel('LLM URL').fill(localLlmUrl);
  await llmSection.getByLabel('Model').fill(localLlmModel);
  await llmSection.getByRole('textbox', { name: /API key/ }).fill('');

  const settingsSaved = page.waitForResponse(
    (response) => isSettingsRequest(response.request(), 'PATCH', '/api/settings') && response.ok()
  );
  await page.getByRole('button', { name: 'Save Settings' }).click();
  await settingsSaved;
  await expect(page.getByText('Endpoint settings saved.')).toBeVisible();

  await runConnectionTest(page, webSection, 'web-ui-status', '/api/settings/test/web', completedSettingsRequests);
  await runConnectionTest(
    page,
    aiBackendSection,
    'ai-backend-status',
    '/api/settings/test/ai-backend',
    completedSettingsRequests
  );
  await runConnectionTest(page, llmSection, 'llm-status', '/api/settings/test/llm', completedSettingsRequests);

  await page.reload();
  await expect(webSection.getByLabel('Web UI URL')).toHaveValue(webUiUrl);
  await expect(aiBackendSection.getByLabel('AI backend URL')).toHaveValue(aiBackendUrl);
  await expect(llmSection.getByLabel('LLM URL')).toHaveValue(localLlmUrl);
  await expect(llmSection.getByLabel('Model')).toHaveValue(localLlmModel);
  await expect(llmSection.getByRole('textbox', { name: /API key/ })).toHaveValue('');
}

async function runConnectionTest(
  page: Page,
  section: Locator,
  statusTestId: string,
  testPath: string,
  completedSettingsRequests: string[]
) {
  const startIndex = completedSettingsRequests.length;
  const patchResponse = page.waitForResponse(
    (response) => isSettingsRequest(response.request(), 'PATCH', '/api/settings') && response.ok(),
    { timeout: 30_000 }
  );
  const testResponse = page.waitForResponse(
    (response) => isSettingsRequest(response.request(), 'POST', testPath) && response.ok(),
    { timeout: 30_000 }
  );

  await section.getByRole('button', { name: 'Test Connection' }).click();
  const [patchResult, testResult] = await Promise.allSettled([patchResponse, testResponse]);
  const observedRequests = completedSettingsRequests.slice(startIndex);
  const observedRequestText = observedRequests.length > 0 ? observedRequests.join(' -> ') : 'none';

  if (patchResult.status === 'rejected' || testResult.status === 'rejected') {
    throw new Error(
      `Expected PATCH /api/settings before POST ${testPath}; observed Settings requests: ${observedRequestText}`
    );
  }

  await expect(page.getByTestId(statusTestId)).toHaveText('Connected', { timeout: 60_000 });

  expect(observedRequests.slice(0, 2)).toEqual(['PATCH /api/settings', `POST ${testPath}`]);
}

async function importLiveCharacter(page: Page, characterName: string) {
  await page.goto(`${liveWebUrl}/gallery`);
  await page.getByRole('button', { name: 'Import Character' }).first().click();

  const importDialog = page.getByRole('dialog', { name: 'Import Character' });
  await importDialog.locator('input[type="file"]').setInputFiles({
    name: 'phase1-live-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(makeLiveCard(characterName)))
  });
  await importDialog.getByRole('button', { name: 'Import Character' }).click();

  await expect(page).toHaveURL(/\/characters\/[^/?]+\?mode=review$/, { timeout: 60_000 });
  await expect(page.getByLabel('Name')).toHaveValue(characterName);
  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();

  return characterIdFromUrl(page.url());
}

async function uploadAndAssertPortrait(page: Page, characterId: string) {
  await page.locator('input[type="file"]').setInputFiles({
    name: 'phase1-live-portrait.png',
    mimeType: 'image/png',
    buffer: portraitPng()
  });

  await assertVisiblePortrait(
    page.locator('img[alt="Character portrait preview"]'),
    `/api/characters/${characterId}/portrait`
  );
  await page.getByRole('button', { name: 'Save Character' }).click();
  await expect(page.getByText('Character saved.')).toBeVisible();
  await page.reload();
  await assertVisiblePortrait(
    page.locator('img[alt="Character portrait preview"]'),
    `/api/characters/${characterId}/portrait`
  );
}

async function assertPortraitSurfacesAndStartChat(
  page: Page,
  characterId: string,
  characterName: string
) {
  await page.goto(`${liveWebUrl}/gallery`);
  const galleryCard = page.getByTestId(`character-card-${characterId}`);
  await expect(galleryCard.getByRole('heading', { name: characterName })).toBeVisible();
  await assertVisiblePortrait(galleryCard.locator('img'), `/api/characters/${characterId}/portrait`);
  await page.reload();
  await assertVisiblePortrait(
    page.getByTestId(`character-card-${characterId}`).locator('img'),
    `/api/characters/${characterId}/portrait`
  );

  await page.goto(liveWebUrl);
  await page.getByRole('button', { name: 'Start Chat' }).first().click();
  const picker = page.getByRole('dialog', { name: 'Choose a character' });
  const option = picker.getByRole('button', { name: new RegExp(escapeRegExp(characterName)) });
  await expect(option).toBeVisible();
  await assertVisiblePortrait(option.locator('img'), `/api/characters/${characterId}/portrait`);
  await option.click();
  await picker.getByLabel(selectedAlternateGreeting).check();
  await picker.getByTestId('create-thread-submit').click();

  await expect(page).toHaveURL(/\/chat\/[^/]+$/, { timeout: 60_000 });
  const threadId = threadIdFromUrl(page.url());
  await expect(page.getByText(selectedAlternateGreeting).first()).toBeVisible();
  await assertVisiblePortrait(
    page.locator('.chat-header .portrait img'),
    `/api/characters/${characterId}/portrait`
  );

  await page.reload();
  await assertVisiblePortrait(
    page.locator('.chat-header .portrait img'),
    `/api/characters/${characterId}/portrait`
  );

  await page.goto(liveWebUrl);
  await assertVisiblePortrait(
    page.getByTestId(`thread-row-${threadId}`).locator('img'),
    `/api/characters/${characterId}/portrait`
  );

  return threadId;
}

async function runFullTextFlow(page: Page, threadId: string) {
  await page.goto(`${liveWebUrl}/chat/${threadId}`);
  await expect(page.getByText(selectedAlternateGreeting).first()).toBeVisible();

  const assistantMessages = page.locator('[data-message-role="assistant"]');
  const openingCount = await assistantMessages.count();
  await sendAndWaitForAssistant(page, 'Give me one short line.', openingCount);

  let target = assistantMessages.last();
  await runMessageMenuAction(page, target, 'Regenerate');
  await waitForActionToSettle(target);

  target = assistantMessages.last();
  const selectedBeforeSwipe = await target.getAttribute('data-selected-alternate-id');
  await target.getByRole('button', { name: 'Generate alternate' }).click();
  await expect(target).not.toHaveAttribute('data-selected-alternate-id', selectedBeforeSwipe ?? '', {
    timeout: 120_000
  });

  target = assistantMessages.last();
  const selectedBeforeContinue = await target.getAttribute('data-selected-alternate-id');
  await page.getByRole('textbox', { name: 'Message' }).fill('add one clue');
  await runMessageMenuAction(page, target, 'Continue');
  await expect(target).not.toHaveAttribute('data-selected-alternate-id', selectedBeforeContinue ?? '', {
    timeout: 120_000
  });

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`/chat/${escapeRegExp(threadId)}$`));
  await expect(assistantMessages.last().locator('.message-content')).not.toHaveText('', {
    timeout: 60_000
  });
  const beforeReloadContinueCount = await assistantMessages.count();
  await sendAndWaitForAssistant(page, 'continue after reload', beforeReloadContinueCount);
}

async function sendAndWaitForAssistant(page: Page, prompt: string, previousAssistantCount: number) {
  const assistantMessages = page.locator('[data-message-role="assistant"]');
  await page.getByRole('textbox', { name: 'Message' }).fill(prompt);
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(assistantMessages).toHaveCount(previousAssistantCount + 1, { timeout: 180_000 });

  const nextAssistant = assistantMessages.nth(previousAssistantCount);
  await expect(nextAssistant).toHaveAttribute('data-streaming', 'false', { timeout: 180_000 });
  await expect
    .poll(async () => (await nextAssistant.locator('.message-content').innerText()).trim().length, {
      timeout: 180_000
    })
    .toBeGreaterThan(0);
}

async function runMessageMenuAction(page: Page, message: Locator, label: string) {
  await message.hover();
  await message.getByRole('button', { name: 'Message actions' }).click();
  await page.getByRole('menuitem', { name: label }).click();
}

async function waitForActionToSettle(message: Locator) {
  await expect(message).not.toHaveAttribute('data-streaming', 'true', { timeout: 120_000 });
  await expect
    .poll(async () => (await message.locator('.message-content').innerText()).trim().length, {
      timeout: 120_000
    })
    .toBeGreaterThan(0);
}

async function assertVisiblePortrait(locator: Locator, expectedSrcPart: string) {
  await expect(locator).toBeVisible({ timeout: 60_000 });
  await expect(locator).toHaveAttribute('src', new RegExp(escapeRegExp(expectedSrcPart)));
}

function makeLiveCard(characterName: string) {
  return {
    spec: 'chara_card_v3',
    spec_version: '3.0',
    data: {
      name: characterName,
      description: 'Live LAN verification character created before Android handoff.',
      personality: 'Concise, direct, and stable for browser acceptance.',
      scenario: 'A live OMEN-PC LAN verification room.',
      first_mes: 'Live default opening greeting.',
      mes_example: '<START>\n{{char}}: Live LAN verification is ready.',
      system_prompt: 'Answer briefly for live acceptance verification.',
      creator_notes: 'Created by live-lan-functional.spec.ts.',
      character_notes: 'Functional live LAN acceptance fixture.',
      tags: ['phase-01.1', 'live-lan'],
      alternate_greetings: ['Live alternate greeting zero.', selectedAlternateGreeting],
      post_history_instructions: 'Keep live verification replies short.',
      creator: 'RayMe',
      character_version: '1.0'
    }
  };
}

function settingsRequestLabel(request: Request) {
  if (isSettingsRequest(request, 'PATCH', '/api/settings')) {
    return 'PATCH /api/settings';
  }

  for (const path of [
    '/api/settings/test/web',
    '/api/settings/test/ai-backend',
    '/api/settings/test/llm'
  ]) {
    if (isSettingsRequest(request, 'POST', path)) {
      return `POST ${path}`;
    }
  }

  return null;
}

function isSettingsRequest(request: Request, method: string, path: string) {
  const url = new URL(request.url());
  return request.method() === method && url.pathname === path;
}

function characterIdFromUrl(rawUrl: string) {
  const parts = new URL(rawUrl).pathname.split('/').filter(Boolean);
  expect(parts[0]).toBe('characters');
  expect(parts[1]).toBeTruthy();
  return decodeURIComponent(parts[1]);
}

function threadIdFromUrl(rawUrl: string) {
  const parts = new URL(rawUrl).pathname.split('/').filter(Boolean);
  expect(parts[0]).toBe('chat');
  expect(parts[1]).toBeTruthy();
  return decodeURIComponent(parts[1]);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
