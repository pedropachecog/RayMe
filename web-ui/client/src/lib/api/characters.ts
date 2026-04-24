import { apiFetch } from './client';
import type {
  CharacterDeleteResult,
  CharacterDetail,
  CharacterEditorPayload,
  CharacterImportResult,
  CharacterSummary,
  CharacterV2Export
} from './types';

export function listCharacters(): Promise<CharacterSummary[]> {
  return apiFetch<CharacterSummary[]>('/characters', { method: 'GET' });
}

export function getCharacter(characterId: string): Promise<CharacterDetail> {
  return apiFetch<CharacterDetail>(`/characters/${encodeURIComponent(characterId)}`, { method: 'GET' });
}

export function createCharacter(payload: CharacterEditorPayload): Promise<CharacterDetail> {
  return apiFetch<CharacterDetail>('/characters', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function updateCharacter(
  characterId: string,
  payload: CharacterEditorPayload
): Promise<CharacterDetail> {
  return apiFetch<CharacterDetail>(`/characters/${encodeURIComponent(characterId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export function deleteCharacter(characterId: string): Promise<CharacterDeleteResult> {
  return apiFetch<CharacterDeleteResult>(`/characters/${encodeURIComponent(characterId)}`, {
    method: 'DELETE'
  });
}

export function importCharacterCard(file: File): Promise<CharacterImportResult> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<CharacterImportResult>('/characters/import', {
    method: 'POST',
    body: formData
  });
}

export function uploadPortrait(characterId: string, file: File): Promise<CharacterDetail> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<CharacterDetail>(`/characters/${encodeURIComponent(characterId)}/portrait`, {
    method: 'PUT',
    body: formData
  });
}

export function removePortrait(characterId: string): Promise<CharacterDetail> {
  return apiFetch<CharacterDetail>(`/characters/${encodeURIComponent(characterId)}/portrait`, {
    method: 'DELETE'
  });
}

export function exportCharacterV2(characterId: string): Promise<CharacterV2Export> {
  return apiFetch<CharacterV2Export>(`/characters/${encodeURIComponent(characterId)}/export-v2`, {
    method: 'GET'
  });
}
