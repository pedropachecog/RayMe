<script lang="ts">
  import { goto } from '$app/navigation';
  import { Check, MessageSquarePlus, Plus, Upload, X } from 'lucide-svelte';
  import { onMount } from 'svelte';

  import {
    deleteCharacter,
    exportCharacterV2,
    listCharacters
  } from '$lib/api/characters';
  import { createThread } from '$lib/api/threads';
  import type { CharacterSummary } from '$lib/api/types';
  import CharacterCard from '$lib/components/CharacterCard.svelte';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import ImportCardDialog from '$lib/components/ImportCardDialog.svelte';

  const deleteConfirmation =
    'Delete this character? Existing chats stay in history, but the character leaves the gallery.';

  let characters: CharacterSummary[] = [];
  let loadState: 'loading' | 'ready' | 'error' = 'loading';
  let actionState: 'idle' | 'creating-thread' | 'deleting' | 'exporting' = 'idle';
  let errorMessage = '';
  let importOpen = false;
  let deletingCharacter: CharacterSummary | null = null;
  let startingCharacter: CharacterSummary | null = null;
  let selectedAlternateGreetingIndex: number | undefined = undefined;

  $: alternateGreetings = startingCharacter?.alternate_greetings ?? [];

  onMount(() => {
    void refreshCharacters();
  });

  async function refreshCharacters() {
    loadState = 'loading';
    errorMessage = '';

    try {
      characters = await listCharacters();
      loadState = 'ready';
    } catch {
      loadState = 'error';
      errorMessage = 'RayMe could not load characters.';
    }
  }

  function createCharacter() {
    void goto('/characters/new?mode=create');
  }

  function editCharacter(character: CharacterSummary) {
    void goto(`/characters/${encodeURIComponent(character.id)}`);
  }

  function requestDeleteCharacter(character: CharacterSummary) {
    deletingCharacter = character;
  }

  async function confirmDeleteCharacter() {
    if (!deletingCharacter) {
      return;
    }

    actionState = 'deleting';
    const characterId = deletingCharacter.id;

    try {
      await deleteCharacter(characterId);
      characters = characters.filter((character) => character.id !== characterId);
      deletingCharacter = null;
    } finally {
      actionState = 'idle';
    }
  }

  function requestStartChat(character: CharacterSummary) {
    if ((character.alternate_greetings ?? []).length > 0) {
      startingCharacter = character;
      selectedAlternateGreetingIndex = undefined;
      return;
    }

    void startChat(character);
  }

  async function startChat(character: CharacterSummary) {
    actionState = 'creating-thread';
    errorMessage = '';

    try {
      const payload =
        selectedAlternateGreetingIndex === undefined
          ? { character_id: character.id }
          : {
              character_id: character.id,
              alternate_greeting_index: selectedAlternateGreetingIndex
            };
      const result = await createThread(payload);
      startingCharacter = null;
      await goto(`/chat/${encodeURIComponent(result.thread_id)}`);
    } catch {
      errorMessage = 'RayMe could not start this chat.';
    } finally {
      actionState = 'idle';
    }
  }

  async function exportJson(character: CharacterSummary) {
    actionState = 'exporting';
    errorMessage = '';

    try {
      const exported = await exportCharacterV2(character.id);
      downloadJson(exported, `${safeFileStem(character.name)}-v2.json`);
    } catch {
      errorMessage = 'RayMe could not export this character.';
    } finally {
      actionState = 'idle';
    }
  }

  function downloadJson(value: unknown, filename: string) {
    const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function safeFileStem(value: string): string {
    const stem = value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return stem || 'character';
  }

  function closeStartDialog() {
    if (actionState !== 'creating-thread') {
      startingCharacter = null;
      selectedAlternateGreetingIndex = undefined;
    }
  }
</script>

<section class="gallery" aria-labelledby="gallery-title">
  <div class="heading">
    <div>
      <p class="eyebrow">Gallery</p>
      <h1 id="gallery-title">Character Gallery</h1>
    </div>

    <div class="actions" aria-label="Gallery actions">
      <button class="primary" type="button" on:click={() => (importOpen = true)}>
        <Upload size={18} strokeWidth={1.8} />
        <span>Import Character</span>
      </button>
      <button type="button" on:click={createCharacter}>
        <Plus size={18} strokeWidth={1.8} />
        <span>Create Character</span>
      </button>
    </div>
  </div>

  {#if errorMessage}
    <p class="inline-error" role="alert">{errorMessage}</p>
  {/if}

  {#if loadState === 'loading'}
    <div class="card-grid" aria-label="Loading characters">
      {#each Array(4) as _}
        <div class="card-skeleton"></div>
      {/each}
    </div>
  {:else if loadState === 'error'}
    <div class="empty-state" role="status">
      <h2>Characters unavailable</h2>
      <p>{errorMessage}</p>
      <button class="primary" type="button" on:click={refreshCharacters}>Retry</button>
    </div>
  {:else if characters.length === 0}
    <div class="empty-state">
      <h2>No characters yet</h2>
      <p>Import a SillyTavern card or create a character to start your first chat.</p>
      <div class="empty-actions">
        <button class="primary" type="button" on:click={() => (importOpen = true)}>
          <Upload size={18} strokeWidth={1.8} />
          <span>Import Character</span>
        </button>
        <button type="button" on:click={createCharacter}>
          <Plus size={18} strokeWidth={1.8} />
          <span>Create Character</span>
        </button>
      </div>
    </div>
  {:else}
    <div class="card-grid" aria-label="Characters">
      {#each characters as character (character.id)}
        <CharacterCard
          {character}
          busy={actionState !== 'idle'}
          onStartChat={requestStartChat}
          onEdit={editCharacter}
          onExportJson={exportJson}
          onDelete={requestDeleteCharacter}
        />
      {/each}
    </div>
  {/if}
</section>

<ImportCardDialog
  open={importOpen}
  onClose={() => (importOpen = false)}
  onImported={(result) => {
    importOpen = false;
    void goto(`/characters/${encodeURIComponent(result.character.id)}?mode=review`);
  }}
/>

{#if startingCharacter}
  <div class="modal-backdrop" role="presentation">
    <div
      class="modal-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="alternate-greeting-title"
    >
      <div class="modal-heading">
        <div>
          <p class="eyebrow">Opening greeting</p>
          <h2 id="alternate-greeting-title">{startingCharacter.name}</h2>
        </div>
        <button class="icon-button" type="button" aria-label="Close greeting selection" on:click={closeStartDialog}>
          <X size={20} strokeWidth={1.8} />
        </button>
      </div>

      <fieldset class="alternate-picker">
        <legend>Choose the first message for this thread</legend>
        <label class:selected={selectedAlternateGreetingIndex === undefined}>
          <input
            type="radio"
            name="gallery-alternate-greeting"
            checked={selectedAlternateGreetingIndex === undefined}
            on:change={() => (selectedAlternateGreetingIndex = undefined)}
          />
          <span>{startingCharacter.first_mes || 'Default greeting'}</span>
          {#if selectedAlternateGreetingIndex === undefined}
            <Check size={18} strokeWidth={2} />
          {/if}
        </label>
        {#each alternateGreetings as greeting, index}
          <label class:selected={selectedAlternateGreetingIndex === index}>
            <input
              type="radio"
              name="gallery-alternate-greeting"
              checked={selectedAlternateGreetingIndex === index}
              on:change={() => (selectedAlternateGreetingIndex = index)}
            />
            <span>{greeting}</span>
            {#if selectedAlternateGreetingIndex === index}
              <Check size={18} strokeWidth={2} />
            {/if}
          </label>
        {/each}
      </fieldset>

      <div class="modal-actions">
        <button type="button" disabled={actionState === 'creating-thread'} on:click={closeStartDialog}>
          Cancel
        </button>
        <button
          class="primary"
          type="button"
          disabled={actionState === 'creating-thread'}
          on:click={() => startChat(startingCharacter)}
        >
          <MessageSquarePlus size={18} strokeWidth={1.8} />
          <span>Start Chat</span>
        </button>
      </div>
    </div>
  </div>
{/if}

<ConfirmDialog
  open={deletingCharacter !== null}
  title="Delete character"
  body={deleteConfirmation}
  confirmLabel="Delete"
  submitting={actionState === 'deleting'}
  onCancel={() => (deletingCharacter = null)}
  onConfirm={confirmDeleteCharacter}
/>

<style>
  .gallery {
    display: grid;
    gap: var(--space-xl);
  }

  .heading {
    display: grid;
    gap: var(--space-lg);
  }

  .eyebrow,
  h1,
  h2,
  p {
    margin: 0;
  }

  .eyebrow {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h1 {
    margin-top: var(--space-sm);
    color: var(--color-text);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: var(--line-display);
  }

  h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .actions,
  .empty-actions,
  .modal-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.78);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  .inline-error {
    width: fit-content;
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 113, 108, 0.12);
    color: var(--color-danger);
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: var(--space-lg);
  }

  .card-skeleton {
    min-height: 460px;
    border-radius: var(--radius-md);
    background: linear-gradient(90deg, rgba(20, 31, 56, 0.58), rgba(25, 37, 64, 0.72), rgba(20, 31, 56, 0.58));
  }

  .empty-state {
    display: grid;
    min-height: 420px;
    place-items: center;
    align-content: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(9, 19, 40, 0.76);
    text-align: center;
  }

  .empty-state p {
    max-width: 380px;
  }

  .empty-actions {
    justify-content: center;
    margin-top: var(--space-sm);
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 70;
    display: grid;
    place-items: center;
    padding: var(--space-lg);
    background: rgba(6, 14, 32, 0.72);
    backdrop-filter: blur(16px);
  }

  .modal-panel {
    display: grid;
    width: min(100%, 640px);
    max-height: min(720px, calc(100vh - 48px));
    gap: var(--space-lg);
    overflow: auto;
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(25, 37, 64, 0.94);
    box-shadow: var(--shadow-float);
  }

  .modal-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-md);
  }

  .icon-button {
    width: 44px;
    min-width: 44px;
    padding: 0;
    color: var(--color-text-muted);
  }

  .alternate-picker {
    display: grid;
    gap: var(--space-sm);
    min-width: 0;
    margin: 0;
    border: 0;
    padding: 0;
  }

  .alternate-picker legend {
    margin-bottom: var(--space-sm);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .alternate-picker label {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr) 24px;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
  }

  .alternate-picker label.selected {
    box-shadow: inset 0 0 0 2px rgba(182, 160, 255, 0.72);
    color: var(--color-text);
  }

  .alternate-picker span {
    display: -webkit-box;
    min-width: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
  }

  .modal-actions {
    justify-content: flex-end;
  }

  @media (min-width: 760px) {
    .heading {
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
    }
  }
</style>
