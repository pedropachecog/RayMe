import { describe, expect, it, vi } from 'vitest';

import {
  expectRayMeApiRequest,
  fulfillJson,
  fulfillSse,
  installBrowserErrorGuard
} from '../e2e/helpers/acceptance';
import {
  makeAiMessage,
  makeCharacter,
  makeThreadDetail,
  makeUserMessage,
  PHASE1_LOCAL_LLM_MODEL,
  PHASE1_LOCAL_LLM_URL
} from '../e2e/helpers/fixtures';

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

describe('Phase 01.1 fixture builders', () => {
  it('exports the current local LLM endpoint and model constants', () => {
    expect(PHASE1_LOCAL_LLM_URL).toBe('http://192.168.1.190:8001/v1');
    expect(PHASE1_LOCAL_LLM_MODEL).toBe('unsloth/Qwen3.5-27B');
  });

  it('builds complete character fixtures with portrait and SillyTavern fields', () => {
    const character = makeCharacter({ name: 'Overridden Aster' });

    expect(character).toMatchObject({
      id: 'phase011-character',
      name: 'Overridden Aster',
      first_mes: 'Default Phase 01.1 greeting.',
      source_format: 'v3_json',
      portrait_asset_id: 'phase011-portrait',
      portrait_storage_path: 'characters/phase011-character/phase011-portrait.png',
      lorebook_status: 'present_not_used_in_v1',
      warnings: ['Lorebook present - not used in v1'],
      alternate_greetings: ['Alternate greeting zero.', 'Alternate greeting selected.']
    });
    expect(character.description).toBeTruthy();
    expect(character.personality).toBeTruthy();
    expect(character.raw_source_json).toMatchObject({ spec: 'chara_card_v3' });
  });

  it('builds selected AI alternates and plain user messages', () => {
    const aiMessage = makeAiMessage('ai-one', 'thread-one', 2, 'Selected response.', 'swipe', 3);
    expect(aiMessage).toMatchObject({
      id: 'ai-one',
      thread_id: 'thread-one',
      sequence: 2,
      message_kind: 'ai_text',
      role: 'assistant',
      content_text: 'Selected response.',
      selected_alternate_id: 'alt-ai-one-swipe-3',
      stale_after_edit: false
    });
    expect(aiMessage.alternates).toEqual([
      {
        id: 'alt-ai-one-swipe-3',
        message_id: 'ai-one',
        alternate_index: 3,
        content_text: 'Selected response.',
        source_action: 'swipe',
        created_at: null
      }
    ]);

    const userMessage = makeUserMessage('user-one', 'thread-one', 1, 'Hello there.');
    expect(userMessage).toMatchObject({
      id: 'user-one',
      thread_id: 'thread-one',
      sequence: 1,
      message_kind: 'user_text',
      role: 'user',
      content_text: 'Hello there.',
      selected_alternate_id: null,
      alternates: []
    });
  });

  it('builds ordered thread detail fixtures with portrait metadata overrides', () => {
    const detail = makeThreadDetail({
      character_portrait_url: '/api/characters/phase011-character/portrait?asset_id=asset-two',
      character_portrait_asset_id: 'asset-two',
      character_portrait_storage_path: 'characters/phase011-character/asset-two.png',
      messages: [
        makeUserMessage('user-two', 'phase011-thread', 3, 'Later user turn.'),
        makeAiMessage('ai-opening', 'phase011-thread', 0, 'Opening turn.', 'first_mes')
      ]
    });

    expect(detail.character_portrait_url).toBe(
      '/api/characters/phase011-character/portrait?asset_id=asset-two'
    );
    expect(detail.character_portrait_asset_id).toBe('asset-two');
    expect(detail.character_portrait_storage_path).toBe('characters/phase011-character/asset-two.png');
    expect(detail.messages.map((message) => message.sequence)).toEqual([0, 3]);
  });
});
