import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createCharacter,
  getCharacter,
  removePortrait,
  updateCharacter,
  uploadPortrait
} from '../../src/lib/api/characters';
import type { CharacterDetail, CharacterEditorPayload } from '../../src/lib/api/types';
import characterFormSectionSource from '../../src/lib/components/CharacterFormSection.svelte?raw';
import portraitDropzoneSource from '../../src/lib/components/PortraitDropzone.svelte?raw';
import editorSource from '../../src/routes/characters/[id]/+page.svelte?raw';

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

const requiredLabels = [
  'Name',
  'Description',
  'Personality',
  'Scenario',
  'First message',
  'Example messages',
  'System prompt',
  'Creator notes',
  'Character notes',
  'Tags',
  'Alternate greetings',
  'Post-history instructions',
  'Creator',
  'Character version'
];

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
  tags: ['operator', 'relay'],
  alternate_greetings: ['Backup line open.'],
  post_history_instructions: 'Preserve tone.',
  creator: 'RayMe',
  character_version: '1.0'
};

const characterDetail: CharacterDetail = {
  id: 'character-1',
  ...characterPayload,
  portrait_url: '/api/characters/character-1/portrait',
  lorebook_status: 'present_not_used_in_v1',
  lorebook_json: { entries: [] }
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

describe('Character Editor route', () => {
  it('renders every REQ-11 field label plus portrait and lorebook controls', () => {
    for (const label of requiredLabels) {
      expect(editorSource).toContain(label);
    }

    for (const field of requiredFields) {
      expect(editorSource).toContain(field);
    }

    expect(editorSource).toContain('<CharacterFormSection');
    expect(editorSource).toContain('<PortraitDropzone');
    expect(characterFormSectionSource).toContain('<slot />');
    expect(portraitDropzoneSource).toContain('accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"');
    expect(portraitDropzoneSource).toContain('Accepted formats:');
    expect(editorSource).toContain('Lorebook present - not used in v1');
    expect(editorSource).toContain('Discard Edits');
    expect(editorSource).toContain('Save Character');
    expect(editorSource).toContain('Discard unsaved changes? Your last saved character version will remain.');
  });

  it('loads edit/review mode through GET /api/characters/{character_id} and skips getCharacter("new") in create mode', async () => {
    const fetchMock = installFetch({
      '/api/characters/character-1::GET': characterDetail
    });

    const character = await getCharacter('character-1');
    const request = lastRequest(fetchMock);

    expect(character.id).toBe('character-1');
    expect(`${request.init.method} ${request.url}`).toBe('GET /api/characters/character-1');
    expect(editorSource).toContain('await getCharacter(characterId)');
    expect(editorSource).toContain('if (isCreateMode)');
    expect(editorSource).not.toContain("getCharacter('new')");
    expect(editorSource).not.toContain('getCharacter("new")');
  });

  it('creates characters through POST /api/characters with every REQ-11 payload field', async () => {
    const fetchMock = installFetch({
      '/api/characters::POST': characterDetail
    });

    await createCharacter(characterPayload);
    const request = lastRequest(fetchMock);
    const body = JSON.parse(request.init.body as string);

    expect(`${request.init.method} ${request.url}`).toBe('POST /api/characters');
    for (const field of requiredFields) {
      expect(body).toHaveProperty(field);
    }
    expect(editorSource).toContain('const created = await createCharacter(payload)');
    expect(editorSource).toContain('selectedPortraitFile === null');
  });

  it('saves edit and review mode through PATCH /api/characters/{character_id} with every REQ-11 payload field', async () => {
    const fetchMock = installFetch({
      '/api/characters/character-1::PATCH': characterDetail
    });

    await updateCharacter('character-1', characterPayload);
    const request = lastRequest(fetchMock);
    const body = JSON.parse(request.init.body as string);

    expect(`${request.init.method} ${request.url}`).toBe('PATCH /api/characters/character-1');
    for (const field of requiredFields) {
      expect(body).toHaveProperty(field);
    }
    expect(editorSource).toContain("requestedMode === 'review'");
    expect(editorSource).toContain('await updateCharacter(characterId, payload)');
  });

  it('uploads and removes portraits through PUT and DELETE /api/characters/{character_id}/portrait', async () => {
    const fetchMock = installFetch({
      '/api/characters/character-1/portrait::PUT': characterDetail,
      '/api/characters/character-1/portrait::DELETE': {
        ...characterDetail,
        portrait_url: null
      }
    });
    const file = new File(['image-bytes'], 'aster.png', { type: 'image/png' });

    await uploadPortrait('character-1', file);
    let request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('PUT /api/characters/character-1/portrait');
    expect(request.init.body).toBeInstanceOf(FormData);

    await removePortrait('character-1');
    request = lastRequest(fetchMock);
    expect(`${request.init.method} ${request.url}`).toBe('DELETE /api/characters/character-1/portrait');
    expect(editorSource).toContain('await uploadPortrait(created.id, selectedPortraitFile)');
    expect(editorSource).toContain('await uploadPortrait(characterId, file)');
    expect(editorSource).toContain('await removePortrait(characterId)');
  });

  it('supports alternate greeting add, edit, remove, and reorder actions with accessible labels', () => {
    expect(editorSource).toContain('addAlternateGreeting');
    expect(editorSource).toContain('updateAlternateGreeting');
    expect(editorSource).toContain('removeAlternateGreeting');
    expect(editorSource).toContain('moveAlternateGreeting');
    expect(editorSource).toContain('aria-label={`Edit alternate greeting ${index + 1}`}');
    expect(editorSource).toContain('aria-label={`Move alternate greeting ${index + 1} up`}');
    expect(editorSource).toContain('aria-label={`Move alternate greeting ${index + 1} down`}');
    expect(editorSource).toContain('aria-label={`Remove alternate greeting ${index + 1}`}');
  });
});
