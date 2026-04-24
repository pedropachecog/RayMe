import { afterEach, describe, expect, it, vi } from 'vitest';

import { listCharacters } from '../../src/lib/api/characters';
import { createThread, deleteThread, listThreads, renameThread } from '../../src/lib/api/threads';
import type { CharacterSummary, ThreadSummary } from '../../src/lib/api/types';
import homeSource from '../../src/routes/+page.svelte?raw';
import threadListItemSource from '../../src/lib/components/ThreadListItem.svelte?raw';

const sampleThread: ThreadSummary = {
  id: 'thread-1',
  character_id: 'character-1',
  title: 'Night relay',
  character_name: 'Aster',
  character_portrait_url: '/portraits/aster.png',
  last_message_snippet: 'The signal is steady now.',
  last_message_at: '2026-04-24T06:00:00Z',
  created_at: '2026-04-24T05:30:00Z',
  updated_at: '2026-04-24T06:00:00Z'
};

const sampleCharacter: CharacterSummary = {
  id: 'character-1',
  name: 'Aster',
  description: 'A precise operator.',
  first_mes: 'Line open.',
  alternate_greetings: ['Backup line open.', 'Second channel ready.'],
  portrait_url: '/portraits/aster.png'
};

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init
  });
}

function installFetch(payloadByRoute: Record<string, unknown>) {
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init: RequestInit = {}) => {
    const routeKey = `${String(url)}::${init.method ?? 'GET'}`;
    const payload = payloadByRoute[routeKey] ?? payloadByRoute[String(url)];

    if (payload === undefined) {
      throw new Error(`Unhandled request: ${routeKey}`);
    }

    return payload instanceof Response ? payload : jsonResponse(payload);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof installFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url: url as string, init: init as RequestInit };
}

describe('Home threads dashboard', () => {
  it('renders ThreadListItem rows with portrait, name, title, snippet, and relative timestamp fields', async () => {
    const fetchMock = installFetch({
      '/api/threads::GET': { items: [sampleThread] }
    });

    const threads = await listThreads();

    expect(threads).toEqual([sampleThread]);
    expect(homeSource).toContain('<ThreadListItem');
    expect(threadListItemSource).toContain('<img src={portraitUrl}');
    expect(threadListItemSource).toContain('{characterName}');
    expect(threadListItemSource).toContain('{title}');
    expect(threadListItemSource).toContain('{snippet}');
    expect(threadListItemSource).toContain('{timestamp}');
    expect(threadListItemSource).toContain('formatRelativeTime');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/threads',
      init: { method: 'GET' }
    });
  });

  it('routes Start Chat to /gallery when no characters exist', async () => {
    const fetchMock = installFetch({
      '/api/characters::GET': { items: [] }
    });

    const characters = await listCharacters();

    expect(characters).toEqual([]);
    expect(homeSource).toContain('if (characters.length === 0)');
    expect(homeSource).toContain("await goto('/gallery')");
    expect(homeSource).toContain('handleStartChat');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters',
      init: { method: 'GET' }
    });
  });

  it('Start Chat with a selected character calls createThread through POST /api/threads and navigates to /chat/{thread_id}', async () => {
    const fetchMock = installFetch({
      '/api/threads::POST': { thread_id: 'thread-created' }
    });

    const result = await createThread({ character_id: sampleCharacter.id });
    const request = lastRequest(fetchMock);

    expect(result.thread_id).toBe('thread-created');
    expect(request.url).toBe('/api/threads');
    expect(request.init.method).toBe('POST');
    expect(JSON.parse(request.init.body as string)).toEqual({
      character_id: 'character-1'
    });
    expect(homeSource).toContain('const result = await createThread(payload)');
    expect(homeSource).toContain('selectedCharacterId');
    expect(homeSource).toContain('await goto(`/chat/${encodeURIComponent(result.thread_id)}`)');
  });

  it('passes alternate_greeting_index into createThread only when an alternate greeting is selected', async () => {
    const fetchMock = installFetch({
      '/api/threads::POST': { thread_id: 'thread-alt' }
    });

    await createThread({
      character_id: sampleCharacter.id,
      alternate_greeting_index: 1
    });
    const request = lastRequest(fetchMock);

    expect(JSON.parse(request.init.body as string)).toEqual({
      character_id: 'character-1',
      alternate_greeting_index: 1
    });
    expect(homeSource).toContain('selectedAlternateGreetingIndex === undefined');
    expect(homeSource).toContain('alternate_greeting_index: selectedAlternateGreetingIndex');
    expect(homeSource).toContain('selectedAlternateGreetings');
  });

  it('renames and deletes threads through exact backend routes with destructive confirmation copy', async () => {
    const fetchMock = installFetch({
      '/api/threads/thread-1::PATCH': {
        thread_id: 'thread-1',
        title: 'Renamed thread',
        updated_at: '2026-04-24T06:04:00Z'
      },
      '/api/threads/thread-1::DELETE': { thread_id: 'thread-1', deleted: true }
    });

    await renameThread('thread-1', { title: 'Renamed thread' });
    const renameRequest = lastRequest(fetchMock);
    expect(renameRequest.url).toBe('/api/threads/thread-1');
    expect(renameRequest.init.method).toBe('PATCH');
    expect(JSON.parse(renameRequest.init.body as string)).toEqual({ title: 'Renamed thread' });

    await deleteThread('thread-1');
    const deleteRequest = lastRequest(fetchMock);
    expect(deleteRequest.url).toBe('/api/threads/thread-1');
    expect(deleteRequest.init.method).toBe('DELETE');

    expect(homeSource).toContain('Rename');
    expect(homeSource).toContain('Delete');
    expect(homeSource).toContain('Delete this thread? This removes the conversation history.');
    expect(homeSource).toContain('<ConfirmDialog');
  });
});
