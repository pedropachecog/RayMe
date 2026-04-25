import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  deleteCharacter,
  exportCharacterV2,
  importCharacterCard,
  listCharacters
} from '../../src/lib/api/characters';
import { createThread } from '../../src/lib/api/threads';
import type { CharacterSummary } from '../../src/lib/api/types';
import characterCardSource from '../../src/lib/components/CharacterCard.svelte?raw';
import importCardDialogSource from '../../src/lib/components/ImportCardDialog.svelte?raw';
import voiceStateBadgeSource from '../../src/lib/components/voice/VoiceStateBadge.svelte?raw';
import gallerySource from '../../src/routes/gallery/+page.svelte?raw';

const sampleCharacter: CharacterSummary = {
  id: 'character-1',
  name: 'Aster <script>alert(1)</script>',
  description: '<img src=x onerror=alert(1)> **Operator**',
  first_mes: 'Line open.',
  alternate_greetings: ['Backup line open.', 'Second channel ready.'],
  tags: ['operator', 'relay', 'calm'],
  portrait_url: '/portraits/aster.png'
};

const voiceStateCharacters: CharacterSummary[] = [
  {
    id: 'assigned-character',
    name: 'Assigned Aster',
    description: 'Has a voice.',
    default_voice_id: 'voice-a',
    default_voice_state: 'assigned',
    default_voice_label: 'Aster Saved Voice',
    default_voice: {
      id: 'voice-a',
      name: 'Aster Saved Voice',
      default_engine: 'f5',
      status: 'available'
    }
  },
  {
    id: 'no-voice-character',
    name: 'Quiet Basil',
    description: 'No voice set.',
    default_voice_id: null,
    default_voice_state: 'none',
    default_voice_label: 'No voice',
    default_voice: null
  },
  {
    id: 'unavailable-character',
    name: 'Deleted Cato',
    description: 'References a deleted voice.',
    default_voice_id: 'voice-deleted',
    default_voice_state: 'unavailable',
    default_voice_label: 'Voice unavailable',
    default_voice: {
      id: 'voice-deleted',
      deleted_name: 'Deleted voice',
      status: 'deleted'
    }
  }
];

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

describe('Gallery character grid', () => {
  it('lists characters and renders malicious snippets through renderTrustedMarkdown', async () => {
    const fetchMock = installFetch({
      '/api/characters::GET': { items: [sampleCharacter] }
    });

    const characters = await listCharacters();

    expect(characters).toEqual([sampleCharacter]);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters',
      init: { method: 'GET' }
    });
    expect(gallerySource).toContain('listCharacters');
    expect(gallerySource).toContain('<CharacterCard');
    expect(characterCardSource).toContain('renderTrustedMarkdown');
    expect(characterCardSource).toContain('{@html renderedSnippet}');
    expect(characterCardSource).toContain('Start Chat');
    expect(characterCardSource).toContain('Edit');
    expect(characterCardSource).toContain('Export JSON');
    expect(characterCardSource).toContain('Delete');
  });

  it('renders assigned, no voice, and unavailable Gallery badge states', async () => {
    const fetchMock = installFetch({
      '/api/characters::GET': { items: voiceStateCharacters }
    });

    const characters = await listCharacters();

    expect(characters).toHaveLength(3);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/characters',
      init: { method: 'GET' }
    });
    expect(characterCardSource).toContain('<VoiceStateBadge');
    expect(characterCardSource).toContain('default_voice_state');
    expect(characterCardSource).toContain('default_voice_label');
    expect(voiceStateBadgeSource).toContain('Voice:');
    expect(voiceStateBadgeSource).toContain('No voice');
    expect(voiceStateBadgeSource).toContain('Voice unavailable');
    expect(voiceStateBadgeSource).toContain('AlertTriangle');
  });

  it('routes create and edit actions to the real editor paths', () => {
    expect(gallerySource).toContain("goto('/characters/new?mode=create')");
    expect(gallerySource).toContain('goto(`/characters/${encodeURIComponent(character.id)}`)');
  });

  it('imports JSON or PNG through POST /api/characters/import and opens editor review', async () => {
    const fetchMock = installFetch({
      '/api/characters/import::POST': {
        character: sampleCharacter,
        warnings: ['Lorebook present - not used in v1', 'Ignored non-string values in tags'],
        source_format: 'v2_json'
      }
    });
    const file = new File(['{}'], 'aster.json', { type: 'application/json' });

    const result = await importCharacterCard(file);
    const request = lastRequest(fetchMock);

    expect(`${request.init.method} ${request.url}`).toBe('POST /api/characters/import');
    expect(request.init.body).toBeInstanceOf(FormData);
    expect(result.character.id).toBe('character-1');
    expect(gallerySource).toContain('goto(`/characters/${encodeURIComponent(result.character.id)}?mode=review`)');
    expect(importCardDialogSource).toContain('importCharacterCard(selectedFile)');
    expect(importCardDialogSource).toContain('accept=".json,.png,application/json,image/png"');
    expect(importCardDialogSource).toContain('Lorebook present - not used in v1');
    expect(importCardDialogSource).toContain('Fields preserved');
    expect(importCardDialogSource).toContain('Unsupported fields ignored');
    expect(importCardDialogSource).toContain('Unsupported file');
    expect(importCardDialogSource).toContain('Malformed JSON');
    expect(importCardDialogSource).toContain('Unreadable PNG metadata');
    expect(importCardDialogSource).toContain('Unsafe content');
  });

  it('deletes only after exact confirmation copy and removes the card after DELETE /api/characters/{character_id}', async () => {
    const fetchMock = installFetch({
      '/api/characters/character-1::DELETE': {
        character_id: 'character-1',
        deleted_at: '2026-04-24T06:00:00Z',
        preserved_thread_ids: ['thread-1'],
        strategy: 'soft_delete'
      }
    });

    await deleteCharacter('character-1');
    const request = lastRequest(fetchMock);

    expect(`${request.init.method} ${request.url}`).toBe('DELETE /api/characters/character-1');
    expect(gallerySource).toContain(
      'Delete this character? Existing chats stay in history, but the character leaves the gallery.'
    );
    expect(gallerySource).toContain('await deleteCharacter(characterId)');
    expect(gallerySource).toContain('characters = characters.filter((character) => character.id !== characterId)');
    expect(gallerySource).toContain('<ConfirmDialog');
  });

  it('starts chat through POST /api/threads with the selected character and navigates to /chat/{thread_id}', async () => {
    const fetchMock = installFetch({
      '/api/threads::POST': { thread_id: 'thread-created' }
    });

    const result = await createThread({ character_id: sampleCharacter.id });
    const request = lastRequest(fetchMock);

    expect(result.thread_id).toBe('thread-created');
    expect(`${request.init.method} ${request.url}`).toBe('POST /api/threads');
    expect(JSON.parse(request.init.body as string)).toEqual({ character_id: 'character-1' });
    expect(gallerySource).toContain('const result = await createThread(payload)');
    expect(gallerySource).toContain('character_id: character.id');
    expect(gallerySource).toContain('goto(`/chat/${encodeURIComponent(result.thread_id)}`)');
  });

  it('passes alternate_greeting_index when an alternate greeting is selected before thread creation', async () => {
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
    expect(gallerySource).toContain('selectedAlternateGreetingIndex === undefined');
    expect(gallerySource).toContain('alternate_greeting_index: selectedAlternateGreetingIndex');
    expect(gallerySource).toContain('alternateGreetings');
  });

  it('exports v2 JSON through GET /api/characters/{character_id}/export-v2 and downloads the v2 object', async () => {
    const exportedPayload = {
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: { name: 'Aster' }
    };
    const fetchMock = installFetch({
      '/api/characters/character-1/export-v2::GET': exportedPayload
    });

    const downloadedObject = await exportCharacterV2('character-1');
    const request = lastRequest(fetchMock);

    expect(`${request.init.method} ${request.url}`).toBe('GET /api/characters/character-1/export-v2');
    expect(downloadedObject).toMatchObject({
      spec: 'chara_card_v2',
      spec_version: '2.0',
      data: { name: 'Aster' }
    });
    expect(gallerySource).toContain('exportCharacterV2(character.id)');
    expect(gallerySource).toContain('downloadJson(exported, `${safeFileStem(character.name)}-v2.json`)');
    expect(gallerySource).toContain('JSON.stringify(value, null, 2)');
    expect(gallerySource).toContain('anchor.download = filename');
  });
});
