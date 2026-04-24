import { describe, expect, it, vi } from 'vitest';

import {
  expectRayMeApiRequest,
  fulfillJson,
  fulfillSse,
  installBrowserErrorGuard
} from '../e2e/helpers/acceptance';

type Listener = (value: unknown) => void;

function makePage() {
  const listeners = new Map<string, Listener[]>();
  return {
    on: vi.fn((event: string, listener: Listener) => {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    }),
    emit(event: string, value: unknown) {
      for (const listener of listeners.get(event) ?? []) {
        listener(value);
      }
    }
  };
}

function makeConsoleMessage(type: string, text: string) {
  return {
    type: () => type,
    text: () => text
  };
}

function makeRoute() {
  return {
    fulfill: vi.fn().mockResolvedValue(undefined)
  };
}

function makeRequest(url: string, pageUrl = 'http://127.0.0.1:4173/settings') {
  return {
    url: () => url,
    frame: () => ({
      page: () => ({
        url: () => pageUrl
      })
    })
  };
}

describe('acceptance E2E helpers', () => {
  it('records browser console errors and page exceptions until asserted', () => {
    const page = makePage();
    const assertNoErrors = installBrowserErrorGuard(page as never);

    page.emit('console', makeConsoleMessage('info', 'booted'));
    expect(assertNoErrors).not.toThrow();

    page.emit('console', makeConsoleMessage('error', 'bootstrap failed'));
    page.emit('pageerror', new Error('route crashed'));

    expect(assertNoErrors).toThrow(/console\.error: bootstrap failed/);
    expect(assertNoErrors).toThrow(/pageerror: route crashed/);
  });

  it('supports narrow console error allowlists', () => {
    const page = makePage();
    const assertNoErrors = installBrowserErrorGuard(page as never, {
      allowConsoleErrors: [/^known benign warning$/]
    });

    page.emit('console', makeConsoleMessage('error', 'known benign warning'));
    expect(assertNoErrors).not.toThrow();

    page.emit('console', makeConsoleMessage('error', 'known benign warning plus leak'));
    expect(assertNoErrors).toThrow(/known benign warning plus leak/);
  });

  it('fulfills JSON and SSE responses with the expected content types', async () => {
    const jsonRoute = makeRoute();
    await fulfillJson(jsonRoute as never, { ok: true }, 201);
    expect(jsonRoute.fulfill).toHaveBeenCalledWith({
      status: 201,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ok: true })
    });

    const sseRoute = makeRoute();
    await fulfillSse(sseRoute as never, ['{"type":"token","text":"hi"}', { type: 'done' }]);
    expect(sseRoute.fulfill).toHaveBeenCalledWith({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: 'data: {"type":"token","text":"hi"}\n\ndata: {"type":"done"}\n\n'
    });
  });

  it('allows RayMe API requests and rejects direct provider or key-leaking requests', () => {
    expect(() =>
      expectRayMeApiRequest(makeRequest('http://127.0.0.1:4173/api/settings') as never)
    ).not.toThrow();
    expect(() =>
      expectRayMeApiRequest(
        makeRequest('https://192.168.1.199:8443/api/settings', 'https://192.168.1.199:8443/') as never
      )
    ).not.toThrow();

    expect(() =>
      expectRayMeApiRequest(makeRequest('http://192.168.1.190:8001/v1/chat/completions') as never)
    ).toThrow(/direct provider/i);
    expect(() =>
      expectRayMeApiRequest(makeRequest('https://api.openai.com/v1/chat/completions') as never)
    ).toThrow(/direct provider/i);
    expect(() =>
      expectRayMeApiRequest(makeRequest('http://127.0.0.1:4173/api/settings?api_key=sk-test') as never)
    ).toThrow(/raw API key/i);
  });
});
