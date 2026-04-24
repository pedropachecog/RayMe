<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    Check,
    MessageSquarePlus,
    Settings,
    Upload,
    UserRoundPlus,
    X
  } from 'lucide-svelte';
  import { onMount } from 'svelte';

  import { listCharacters } from '$lib/api/characters';
  import { createThread, deleteThread, listThreads, renameThread } from '$lib/api/threads';
  import type { CharacterSummary, ThreadSummary } from '$lib/api/types';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import ThreadListItem from '$lib/components/ThreadListItem.svelte';

  const deleteConfirmation = 'Delete this thread? This removes the conversation history.';

  let threads: ThreadSummary[] = [];
  let characters: CharacterSummary[] = [];
  let threadsState: 'loading' | 'ready' | 'error' = 'loading';
  let startState: 'idle' | 'loading' | 'ready' | 'creating' | 'error' = 'idle';
  let threadActionState: 'idle' | 'saving' | 'deleting' = 'idle';
  let errorMessage = '';
  let startError = '';
  let activeMenuThreadId: string | null = null;
  let characterPickerOpen = false;
  let selectedCharacterId = '';
  let selectedAlternateGreetingIndex: number | undefined = undefined;
  let renamingThread: ThreadSummary | null = null;
  let renameTitle = '';
  let deletingThread: ThreadSummary | null = null;

  $: selectedCharacter = characters.find((character) => character.id === selectedCharacterId) ?? null;
  $: selectedAlternateGreetings = selectedCharacter?.alternate_greetings ?? [];

  onMount(() => {
    void refreshThreads();
  });

  async function refreshThreads() {
    threadsState = 'loading';
    errorMessage = '';

    try {
      threads = await listThreads();
      threadsState = 'ready';
    } catch {
      threadsState = 'error';
      errorMessage = 'RayMe could not load recent threads.';
    }
  }

  async function handleStartChat() {
    startState = 'loading';
    startError = '';

    try {
      characters = await listCharacters();
    } catch {
      startState = 'error';
      startError = 'RayMe could not load characters.';
      characterPickerOpen = true;
      return;
    }

    if (characters.length === 0) {
      startState = 'idle';
      await goto('/gallery');
      return;
    }

    selectedCharacterId = '';
    selectedAlternateGreetingIndex = undefined;
    characterPickerOpen = true;
    startState = 'ready';
  }

  function selectCharacter(characterId: string) {
    selectedCharacterId = characterId;
    selectedAlternateGreetingIndex = undefined;
  }

  function initialsFor(value: string): string {
    return value
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
  }

  async function createSelectedThread() {
    if (!selectedCharacterId) {
      return;
    }

    startState = 'creating';
    startError = '';

    try {
      const payload =
        selectedAlternateGreetingIndex === undefined
          ? { character_id: selectedCharacterId }
          : {
              character_id: selectedCharacterId,
              alternate_greeting_index: selectedAlternateGreetingIndex
            };
      const result = await createThread(payload);
      characterPickerOpen = false;
      await goto(`/chat/${encodeURIComponent(result.thread_id)}`);
    } catch {
      startState = 'error';
      startError = 'RayMe could not start this chat.';
    }
  }

  function openThread(thread: ThreadSummary) {
    void goto(`/chat/${encodeURIComponent(thread.id)}`);
  }

  function toggleThreadMenu(threadId: string) {
    activeMenuThreadId = activeMenuThreadId === threadId ? null : threadId;
  }

  function openRenameDialog(thread: ThreadSummary) {
    renamingThread = thread;
    renameTitle = thread.title?.trim() || thread.character_name || '';
    activeMenuThreadId = null;
  }

  async function submitRename() {
    if (!renamingThread || !renameTitle.trim()) {
      return;
    }

    threadActionState = 'saving';
    const threadId = renamingThread.id;
    const nextTitle = renameTitle.trim();

    try {
      const result = await renameThread(threadId, { title: nextTitle });
      threads = threads.map((thread) =>
        thread.id === threadId
          ? {
              ...thread,
              title: result.title,
              updated_at: result.updated_at ?? thread.updated_at
            }
          : thread
      );
      renamingThread = null;
      renameTitle = '';
    } finally {
      threadActionState = 'idle';
    }
  }

  function requestDeleteThread(thread: ThreadSummary) {
    deletingThread = thread;
    activeMenuThreadId = null;
  }

  async function confirmDeleteThread() {
    if (!deletingThread) {
      return;
    }

    threadActionState = 'deleting';
    const threadId = deletingThread.id;

    try {
      await deleteThread(threadId);
      threads = threads.filter((thread) => thread.id !== threadId);
      deletingThread = null;
    } finally {
      threadActionState = 'idle';
    }
  }

  function closeCharacterPicker() {
    if (startState !== 'creating') {
      characterPickerOpen = false;
      startState = 'idle';
      startError = '';
    }
  }

  function closeRenameDialog() {
    if (threadActionState !== 'saving') {
      renamingThread = null;
      renameTitle = '';
    }
  }
</script>

<section class="home">
  <div class="heading">
    <div>
      <p class="eyebrow">Home</p>
      <h1>RayMe</h1>
    </div>

    <div class="actions" aria-label="Home actions">
      <button class="primary" type="button" on:click={handleStartChat}>
        <MessageSquarePlus size={18} strokeWidth={1.8} />
        <span>Start Chat</span>
      </button>
      <button type="button" on:click={() => goto('/gallery')}>
        <Upload size={18} strokeWidth={1.8} />
        <span>Import Character</span>
      </button>
      <button type="button" on:click={() => goto('/gallery')}>
        <UserRoundPlus size={18} strokeWidth={1.8} />
        <span>Create Character</span>
      </button>
      <button type="button" on:click={() => goto('/settings')}>
        <Settings size={18} strokeWidth={1.8} />
        <span>Settings</span>
      </button>
    </div>
  </div>

  <section class="threads-panel" aria-labelledby="recent-threads-title">
    <div class="panel-heading">
      <div>
        <h2 id="recent-threads-title">Recent threads</h2>
        <p>Resume a conversation or start a new one from a saved character.</p>
      </div>
      <button class="panel-action" type="button" on:click={handleStartChat}>
        <MessageSquarePlus size={18} strokeWidth={1.8} />
        <span>Start Chat</span>
      </button>
    </div>

    {#if threadsState === 'loading'}
      <div class="thread-skeleton" aria-label="Loading recent threads">
        <span></span>
        <span></span>
        <span></span>
      </div>
    {:else if threadsState === 'error'}
      <div class="empty-state" role="status">
        <h3>Recent threads unavailable</h3>
        <p>{errorMessage}</p>
        <button class="primary empty-action" type="button" on:click={refreshThreads}>Retry</button>
      </div>
    {:else if threads.length === 0}
      <div class="empty-state">
        <h3>No conversations yet</h3>
        <p>Import a SillyTavern card or create a character to start your first chat.</p>
        <button class="primary empty-action" type="button" on:click={handleStartChat}>
          <MessageSquarePlus size={18} strokeWidth={1.8} />
          <span>Start Chat</span>
        </button>
      </div>
    {:else}
      <div class="thread-list" aria-label="Recent threads">
        {#each threads as thread (thread.id)}
          <ThreadListItem
            {thread}
            menuOpen={activeMenuThreadId === thread.id}
            onOpen={openThread}
            onToggleMenu={toggleThreadMenu}
            onRename={openRenameDialog}
            onDelete={requestDeleteThread}
          />
        {/each}
      </div>
    {/if}
  </section>
</section>

{#if characterPickerOpen}
  <div class="modal-backdrop" role="presentation">
    <div
      class="modal-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="character-picker-title"
    >
      <div class="modal-heading">
        <div>
          <p class="eyebrow">New thread</p>
          <h2 id="character-picker-title">Choose a character</h2>
        </div>
        <button class="icon-button" type="button" aria-label="Close character selection" on:click={closeCharacterPicker}>
          <X size={20} strokeWidth={1.8} />
        </button>
      </div>

      {#if startError}
        <p class="inline-error">{startError}</p>
      {/if}

      <div class="character-options" aria-label="Characters">
        {#each characters as character (character.id)}
          <button
            class:selected={selectedCharacterId === character.id}
            class="character-option"
            type="button"
            on:click={() => selectCharacter(character.id)}
          >
            <span class="character-avatar" aria-hidden="true">
              {#if character.portrait_url}
                <img src={character.portrait_url} alt="" loading="lazy" />
              {:else}
                <span>{initialsFor(character.name) || 'R'}</span>
              {/if}
            </span>
            <span>
              <strong>{character.name}</strong>
              <small>{character.description || character.first_mes || 'Ready for a new thread.'}</small>
            </span>
            {#if selectedCharacterId === character.id}
              <Check size={18} strokeWidth={2} />
            {/if}
          </button>
        {/each}
      </div>

      {#if selectedCharacter && selectedAlternateGreetings.length > 0}
        <fieldset class="alternate-picker">
          <legend>Opening greeting</legend>
          <label class:selected={selectedAlternateGreetingIndex === undefined}>
            <input
              type="radio"
              name="alternate-greeting"
              checked={selectedAlternateGreetingIndex === undefined}
              on:change={() => (selectedAlternateGreetingIndex = undefined)}
            />
            <span>{selectedCharacter.first_mes || 'Default greeting'}</span>
          </label>
          {#each selectedAlternateGreetings as greeting, index}
            <label class:selected={selectedAlternateGreetingIndex === index}>
              <input
                type="radio"
                name="alternate-greeting"
                checked={selectedAlternateGreetingIndex === index}
                on:change={() => (selectedAlternateGreetingIndex = index)}
              />
              <span>{greeting}</span>
            </label>
          {/each}
        </fieldset>
      {/if}

      <div class="modal-actions">
        <button type="button" on:click={closeCharacterPicker} disabled={startState === 'creating'}>
          Cancel
        </button>
        <button
          class="primary"
          data-testid="create-thread-submit"
          type="button"
          disabled={!selectedCharacterId || startState === 'creating'}
          on:click={createSelectedThread}
        >
          <MessageSquarePlus size={18} strokeWidth={1.8} />
          <span>Start Chat</span>
        </button>
      </div>
    </div>
  </div>
{/if}

{#if renamingThread}
  <div class="modal-backdrop" role="presentation">
    <div
      class="modal-panel rename-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rename-thread-title"
    >
      <form on:submit|preventDefault={submitRename}>
        <div class="modal-heading">
          <div>
            <p class="eyebrow">Thread action</p>
            <h2 id="rename-thread-title">Rename thread</h2>
          </div>
          <button class="icon-button" type="button" aria-label="Close rename" on:click={closeRenameDialog}>
            <X size={20} strokeWidth={1.8} />
          </button>
        </div>

        <label class="field-label" for="thread-title">Title</label>
        <input
          id="thread-title"
          bind:value={renameTitle}
          maxlength="240"
          autocomplete="off"
          disabled={threadActionState === 'saving'}
        />

        <div class="modal-actions">
          <button type="button" on:click={closeRenameDialog} disabled={threadActionState === 'saving'}>
            Cancel
          </button>
          <button class="primary" type="submit" disabled={!renameTitle.trim() || threadActionState === 'saving'}>
            Save
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<ConfirmDialog
  open={deletingThread !== null}
  title="Delete thread"
  body={deleteConfirmation}
  confirmLabel="Delete"
  submitting={threadActionState === 'deleting'}
  onCancel={() => (deletingThread = null)}
  onConfirm={confirmDeleteThread}
/>

<style>
  .home {
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
  h3,
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

  h2,
  h3 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  .actions,
  .modal-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 14px;
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

  .threads-panel {
    display: grid;
    min-height: 520px;
    gap: var(--space-lg);
    align-content: start;
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(9, 19, 40, 0.76);
    backdrop-filter: blur(20px);
  }

  .panel-heading {
    display: grid;
    gap: var(--space-md);
  }

  .panel-heading p {
    margin-top: var(--space-sm);
  }

  .panel-action {
    justify-self: start;
  }

  .thread-list,
  .thread-skeleton {
    display: grid;
    gap: var(--space-sm);
  }

  .thread-skeleton span {
    min-height: 96px;
    border-radius: var(--radius-md);
    background: linear-gradient(90deg, rgba(20, 31, 56, 0.58), rgba(25, 37, 64, 0.72), rgba(20, 31, 56, 0.58));
  }

  .empty-state {
    display: grid;
    min-height: 340px;
    place-items: center;
    align-content: center;
    gap: var(--space-sm);
    text-align: center;
  }

  .empty-state p {
    max-width: 360px;
  }

  .empty-action {
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

  .rename-panel {
    width: min(100%, 440px);
  }

  .rename-panel form {
    display: grid;
    gap: var(--space-lg);
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

  .inline-error {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 113, 108, 0.12);
    color: var(--color-danger);
  }

  .character-options {
    display: grid;
    gap: var(--space-sm);
  }

  .character-option {
    display: grid;
    grid-template-columns: 48px minmax(0, 1fr) 24px;
    min-height: 76px;
    justify-items: stretch;
    padding: var(--space-sm);
    background: rgba(9, 19, 40, 0.72);
    text-align: left;
  }

  .character-option.selected {
    box-shadow: inset 0 0 0 2px rgba(182, 160, 255, 0.72);
  }

  .character-avatar {
    display: grid;
    width: 48px;
    height: 48px;
    place-items: center;
    overflow: hidden;
    border-radius: 50%;
    background: var(--pulse-gradient);
    color: var(--color-surface);
    font-size: var(--font-heading);
    font-weight: 600;
  }

  .character-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .character-option strong,
  .character-option small {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .character-option strong {
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .character-option small {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .alternate-picker {
    display: grid;
    gap: var(--space-sm);
    border: 0;
    margin: 0;
    padding: 0;
  }

  .alternate-picker legend,
  .field-label {
    margin-bottom: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .alternate-picker label {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr);
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(9, 19, 40, 0.62);
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .alternate-picker label.selected {
    background: rgba(182, 160, 255, 0.16);
    color: var(--color-text);
  }

  input {
    width: 100%;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(9, 19, 40, 0.82);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
  }

  .modal-actions {
    justify-content: flex-end;
  }

  @media (min-width: 840px) {
    .heading {
      grid-template-columns: 1fr auto;
      align-items: end;
    }

    .panel-heading {
      grid-template-columns: 1fr auto;
      align-items: start;
    }
  }
</style>
