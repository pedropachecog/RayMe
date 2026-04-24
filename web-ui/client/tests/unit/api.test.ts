import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiFetch } from '../../src/lib/api/client';
import {
  createCharacter,
  deleteCharacter,
  exportCharacterV2,
  getCharacter,
  importCharacterCard,
  listCharacters,
  removePortrait,
  updateCharacter,
  uploadPortrait
} from '../../src/lib/api/characters';
import { testAiBackendSettings, testLlmSettings, testWebSettings } from '../../src/lib/api/settings';
import { readChatStream } from '../../src/lib/api/stream';
import { createThread } from '../../src/lib/api/threads';
import type { CharacterEditorPayload, ThreadMessage } from '../../src/lib/api/types';

const statusValues = ['Connected', 'Unreachable', 'Unauthorized', 'Not configured'];

const characterPayload: CharacterEditorPayload = {
  name: 'Aster',
  description: 'A precise operator.',
  personality: 'Focused',
  scenario: 'A quiet relay room.',
  first_mes: 'Line open.',
  mes_example: '<START>',
  system_prompt: 'Stay in character.',
  creator_notes: 'Private notes',
  character_notes: 'Public notes',
  tags: ['operator'],
  alternate_greetings: ['Backup line open.'],
  post_history_instructions: 'Preserve tone.',
  creator: 'RayMe',
  character_version: '1.0',
  portrait_url: '/api/characters/character-1/portrait'
};

afterEach(() => {
  vi.restoreAllMocks();
});

function mockJsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init
  });
}

function installFetch(payload: unknown = {}) {
  const fetchMock = vi.fn(async () => mockJsonResponse(payload));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof installFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url: url as string, init: init as RequestInit };
}

describe('apiFetch', () => {
  it('prepends /api and rejects absolute LLM/provider URLs', async () => {
    const fetchMock = installFetch({ ok: true });

    await apiFetch('/settings', { method: 'GET' });
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/settings',
      init: { method: 'GET' }
    });

    await expect(apiFetch('https://api.openai.com/v1/chat/completions')).rejects.toThrow(
      /RayMe backend routes/
    );
    await expect(apiFetch('http://llm.local/v1/chat/completions')).rejects.toThrow(
      /RayMe backend routes/
    );
  });
});

describe('thread wrappers', () => {
  it('createThread calls exactly POST /api/threads and returns thread_id', async () => {
    const fetchMock = installFetch({ thread_id: 'thread-123' });

    const result = await createThread({
      character_id: 'character-1',
      title: 'Opening',
      alternate_greeting_index: 2
    });
    const request = lastRequest(fetchMock);

    expect(result.thread_id).toBe('thread-123');
    expect(request.url).toBe('/api/threads');
    expect(request.init.method).toBe('POST');
    expect(JSON.parse(request.init.body as string)).toEqual({
      character_id: 'character-1',
      title: 'Opening',
      alternate_greeting_index: 2
    });
  });
});

describe('character wrappers', () => {
  it('calls exact character CRUD, import, portrait, and export routes with methods', async () => {
    const fetchMock = installFetch({
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: { name: 'Aster' }
    });
    const file = new File(['{}'], 'aster.json', { type: 'application/json' });

    await listCharacters();
    expect(lastRequest(fetchMock)).toMatchObject({ url: '/api/characters', init: { method: 'GET' } });

    await getCharacter('character 1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character%201',
      init: { method: 'GET' }
    });

    await createCharacter(characterPayload);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters',
      init: { method: 'POST' }
    });

    await updateCharacter('character-1', characterPayload);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character-1',
      init: { method: 'PATCH' }
    });

    await deleteCharacter('character-1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character-1',
      init: { method: 'DELETE' }
    });

    await importCharacterCard(file);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/import',
      init: { method: 'POST' }
    });
    expect(lastRequest(fetchMock).init.body).toBeInstanceOf(FormData);

    await uploadPortrait('character-1', file);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character-1/portrait',
      init: { method: 'PUT' }
    });
    expect(lastRequest(fetchMock).init.body).toBeInstanceOf(FormData);

    await removePortrait('character-1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character-1/portrait',
      init: { method: 'DELETE' }
    });

    const exported = await exportCharacterV2('character-1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters/character-1/export-v2',
      init: { method: 'GET' }
    });
    expect(exported).toMatchObject({
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: { name: 'Aster' }
    });
  });

  it('sends REQ-11 fields for createCharacter and updateCharacter', async () => {
    const fetchMock = installFetch({ id: 'character-1', ...characterPayload });
    const requiredFields = [
      'name',
      'description',
      'personality',
      'scenario',
      'first_mes',
      'mes_example',
      'system_prompt',
      'creator_notes',
      'character_notes',
      'tags',
      'alternate_greetings',
      'post_history_instructions',
      'creator',
      'character_version'
    ];

    await createCharacter(characterPayload);
    const createBody = JSON.parse(lastRequest(fetchMock).init.body as string);
    for (const field of requiredFields) {
      expect(createBody).toHaveProperty(field);
    }

    await updateCharacter('character-1', characterPayload);
    const updateBody = JSON.parse(lastRequest(fetchMock).init.body as string);
    for (const field of requiredFields) {
      expect(updateBody).toHaveProperty(field);
    }
  });
});

describe('settings wrappers', () => {
  it('calls endpoint test routes and preserves exact status values', async () => {
    const fetchMock = installFetch({ status: 'Connected' });

    await testWebSettings();
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/settings/test/web',
      init: { method: 'POST' }
    });

    await testAiBackendSettings();
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/settings/test/ai-backend',
      init: { method: 'POST' }
    });

    const result = await testLlmSettings();
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/settings/test/llm',
      init: { method: 'POST' }
    });
    expect(statusValues).toContain(result.status);
  });
});

describe('readChatStream', () => {
  it('dispatches token, done, and error data events', async () => {
    const doneMessage: ThreadMessage = {
      id: 'ai-message',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: 'Hello',
      selected_alternate_id: null,
      alternates: [],
      stale_after_edit: false,
      created_at: null,
      updated_at: null
    };
    const stream = [
      'data: {"type":"token","text":"Hel"}\n\n',
      'data: {"type":"token","text":"lo"}\n\n',
      `data: ${JSON.stringify({ type: 'done', message: doneMessage })}\n\n`,
      'data: {"type":"error","message":"Upstream stopped"}\n\n'
    ].join('');
    const tokens: string[] = [];
    const done = vi.fn();
    const errors: string[] = [];

    await readChatStream(new Response(stream), {
      onToken: (text) => tokens.push(text),
      onDone: done,
      onError: (message) => errors.push(message)
    });

    expect(tokens).toEqual(['Hel', 'lo']);
    expect(done).toHaveBeenCalledWith(doneMessage);
    expect(errors).toEqual(['Upstream stopped']);
  });

  it('passes onDone(message: ThreadMessage) with the full done object', async () => {
    const doneMessage: ThreadMessage = {
      id: 'ai-message',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: 'Selected answer',
      selected_alternate_id: 'alternate-selected',
      alternates: [
        {
          id: 'alternate-selected',
          message_id: 'ai-message',
          alternate_index: 0,
          content_text: 'Selected answer',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      stale_after_edit: false,
      created_at: null,
      updated_at: null
    };
    const done = vi.fn();

    await readChatStream(
      new Response(`data: ${JSON.stringify({ type: 'done', message: doneMessage })}\n\n`),
      { onDone: done }
    );

    expect(done).toHaveBeenCalledTimes(1);
    expect(done.mock.calls[0][0]).toEqual({
      id: 'ai-message',
      thread_id: 'thread-1',
      message_kind: 'ai_text',
      role: 'assistant',
      sequence: 2,
      content_text: 'Selected answer',
      selected_alternate_id: 'alternate-selected',
      alternates: [
        {
          id: 'alternate-selected',
          message_id: 'ai-message',
          alternate_index: 0,
          content_text: 'Selected answer',
          source_action: 'regenerate',
          created_at: null
        }
      ],
      stale_after_edit: false,
      created_at: null,
      updated_at: null
    });
  });
});
