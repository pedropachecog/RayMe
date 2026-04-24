import { expect, type ConsoleMessage, type Page, type Request, type Route } from '@playwright/test';

const PLAYWRIGHT_APP_ORIGIN = 'http://127.0.0.1:4173';
const LOCAL_LLM_PROVIDER_URL = 'http://192.168.1.190:8001/v1';
const OPENAI_PROVIDER_ORIGIN = 'https://api.openai.com';

type BrowserErrorGuardOptions = {
  allowConsoleErrors?: RegExp[];
};

export function installBrowserErrorGuard(page: Page, options: BrowserErrorGuardOptions = {}) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (message: ConsoleMessage) => {
    if (message.type() !== 'error') {
      return;
    }

    const text = message.text();
    const allowed = (options.allowConsoleErrors ?? []).some((matcher) => {
      matcher.lastIndex = 0;
      return matcher.test(text);
    });

    if (!allowed) {
      consoleErrors.push(`console.error: ${text}`);
    }
  });

  page.on('pageerror', (error: Error) => {
    pageErrors.push(`pageerror: ${error.message}`);
  });

  return () => {
    expect([...consoleErrors, ...pageErrors]).toEqual([]);
  };
}

export async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export async function fulfillSse(route: Route, events: unknown[]) {
  await route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
    body: events
      .map((event) => {
        const payload = typeof event === 'string' ? event : JSON.stringify(event);
        return `data: ${payload}\n\n`;
      })
      .join('')
  });
}

export function expectRayMeApiRequest(request: Request) {
  const rawUrl = request.url();
  const url = new URL(rawUrl);

  if (url.search.includes('sk-')) {
    throw new Error(`Browser request includes a raw API key query string: ${rawUrl}`);
  }

  const currentPageOrigin = getCurrentPageOrigin(request);
  const isRayMeRelativeApi = url.pathname.startsWith('/api/');
  const isPlaywrightAppOrigin = url.origin === PLAYWRIGHT_APP_ORIGIN;
  const isCurrentPageOrigin = currentPageOrigin !== null && url.origin === currentPageOrigin;
  const isAllowedAppRequest = isRayMeRelativeApi || isPlaywrightAppOrigin || isCurrentPageOrigin;

  if (isAllowedAppRequest) {
    return;
  }

  if (isDirectProviderUrl(url)) {
    throw new Error(`Browser made a direct provider request instead of using RayMe /api: ${rawUrl}`);
  }
}

function getCurrentPageOrigin(request: Request) {
  try {
    const pageUrl = request.frame().page().url();
    return pageUrl ? new URL(pageUrl).origin : null;
  } catch {
    return null;
  }
}

function isDirectProviderUrl(url: URL) {
  if (url.href.startsWith(LOCAL_LLM_PROVIDER_URL) || url.origin === OPENAI_PROVIDER_ORIGIN) {
    return true;
  }

  const providerHostname = /(openai|anthropic|mistral|groq|openrouter|generativelanguage)/i;
  const providerPath = url.pathname.startsWith('/v1') || url.pathname.includes('/chat/completions');
  return providerHostname.test(url.hostname) || providerPath;
}
