<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from 'lucide-svelte';
  import { onDestroy, onMount } from 'svelte';

  import {
    createCharacter,
    getCharacter,
    removePortrait,
    updateCharacter,
    uploadPortrait
  } from '$lib/api/characters';
  import type { CharacterDetail, CharacterEditorPayload } from '$lib/api/types';
  import CharacterFormSection from '$lib/components/CharacterFormSection.svelte';
  import PortraitDropzone from '$lib/components/PortraitDropzone.svelte';

  type EditorMode = 'create' | 'review' | 'edit';

  interface CharacterEditorForm {
    name: string;
    description: string;
    personality: string;
    scenario: string;
    first_mes: string;
    mes_example: string;
    system_prompt: string;
    creator_notes: string;
    character_notes: string;
    tagsText: string;
    alternate_greetings: string[];
    post_history_instructions: string;
    creator: string;
    character_version: string;
  }

  const discardConfirmation =
    'Discard unsaved changes? Your last saved character version will remain.';

  const characterId = page.params.id ?? 'new';
  const requestedMode = page.url.searchParams.get('mode');
  const isCreateMode = characterId === 'new' || requestedMode === 'create';
  const mode: EditorMode = isCreateMode ? 'create' : requestedMode === 'review' ? 'review' : 'edit';

  let form = emptyForm();
  let originalCharacter: CharacterDetail | null = null;
  let loadState: 'loading' | 'ready' | 'error' = isCreateMode ? 'ready' : 'loading';
  let saveState: 'idle' | 'saving' = 'idle';
  let portraitState: 'idle' | 'uploading' | 'removing' = 'idle';
  let errorMessage = '';
  let successMessage = '';
  let portraitError = '';
  let previewUrl: string | null = null;
  let localPreviewUrl: string | null = null;
  let selectedPortraitFile: File | null = null;
  let lorebookPresent = false;

  $: modeLabel = mode === 'create' ? 'Create character' : mode === 'review' ? 'Review character' : 'Edit character';
  $: portraitBusy = portraitState !== 'idle' || saveState === 'saving';

  onMount(() => {
    if (isCreateMode) {
      return;
    }

    void loadCharacter();
  });

  onDestroy(() => {
    revokeLocalPreview();
  });

  function emptyForm(): CharacterEditorForm {
    return {
      name: '',
      description: '',
      personality: '',
      scenario: '',
      first_mes: '',
      mes_example: '',
      system_prompt: '',
      creator_notes: '',
      character_notes: '',
      tagsText: '',
      alternate_greetings: [],
      post_history_instructions: '',
      creator: '',
      character_version: ''
    };
  }

  async function loadCharacter() {
    loadState = 'loading';
    errorMessage = '';

    try {
      const character = await getCharacter(characterId);
      applyCharacter(character);
      loadState = 'ready';
    } catch {
      loadState = 'error';
      errorMessage = 'RayMe could not load this character.';
    }
  }

  function applyCharacter(character: CharacterDetail) {
    originalCharacter = character;
    form = {
      name: character.name ?? '',
      description: character.description ?? '',
      personality: character.personality ?? '',
      scenario: character.scenario ?? '',
      first_mes: character.first_mes ?? '',
      mes_example: character.mes_example ?? '',
      system_prompt: character.system_prompt ?? '',
      creator_notes: character.creator_notes ?? '',
      character_notes: character.character_notes ?? '',
      tagsText: (character.tags ?? []).join(', '),
      alternate_greetings: [...(character.alternate_greetings ?? [])],
      post_history_instructions: character.post_history_instructions ?? '',
      creator: character.creator ?? '',
      character_version: character.character_version ?? ''
    };
    selectedPortraitFile = null;
    setPreviewUrl(character.portrait_url ?? null);
    lorebookPresent =
      character.lorebook_status === 'present_not_used_in_v1' || Boolean(character.lorebook_json);
  }

  function setPreviewUrl(nextPreviewUrl: string | null) {
    revokeLocalPreview();
    previewUrl = nextPreviewUrl;
  }

  function revokeLocalPreview() {
    if (localPreviewUrl) {
      URL.revokeObjectURL(localPreviewUrl);
      localPreviewUrl = null;
    }
  }

  function setPreviewFromFile(file: File) {
    revokeLocalPreview();
    localPreviewUrl = URL.createObjectURL(file);
    previewUrl = localPreviewUrl;
  }

  function buildPayload(): CharacterEditorPayload {
    return {
      name: form.name.trim(),
      description: form.description,
      personality: form.personality,
      scenario: form.scenario,
      first_mes: form.first_mes,
      mes_example: form.mes_example,
      system_prompt: form.system_prompt,
      creator_notes: form.creator_notes,
      character_notes: form.character_notes,
      tags: parseList(form.tagsText),
      alternate_greetings: form.alternate_greetings
        .map((greeting) => greeting.trim())
        .filter(Boolean),
      post_history_instructions: form.post_history_instructions,
      creator: form.creator,
      character_version: form.character_version
    };
  }

  function parseList(value: string): string[] {
    return value
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function saveCharacter() {
    errorMessage = '';
    successMessage = '';
    portraitError = '';

    if (!form.name.trim()) {
      errorMessage = 'Character name is required.';
      return;
    }

    saveState = 'saving';
    const payload = buildPayload();

    try {
      if (isCreateMode) {
        const created = await createCharacter(payload);
        const saved =
          selectedPortraitFile === null
            ? created
            : await uploadPortrait(created.id, selectedPortraitFile);
        applyCharacter(saved);
        successMessage = 'Character saved.';
        await goto(`/characters/${encodeURIComponent(saved.id)}`);
        return;
      }

      const updated = await updateCharacter(characterId, payload);
      applyCharacter(updated);
      successMessage = 'Character saved.';
    } catch {
      errorMessage = 'RayMe could not save this character.';
    } finally {
      saveState = 'idle';
    }
  }

  async function handlePortraitSelected(file: File) {
    portraitError = '';
    const previousPreview = previewUrl;
    setPreviewFromFile(file);

    if (isCreateMode) {
      selectedPortraitFile = file;
      return;
    }

    portraitState = 'uploading';

    try {
      const updated = await uploadPortrait(characterId, file);
      applyCharacter(updated);
    } catch (error) {
      setPreviewUrl(previousPreview);
      portraitError =
        error instanceof Error
          ? error.message
          : 'Portrait upload failed. Accepted formats: PNG, JPG, or WebP.';
    } finally {
      portraitState = 'idle';
    }
  }

  async function handlePortraitRemove() {
    portraitError = '';

    if (isCreateMode) {
      selectedPortraitFile = null;
      setPreviewUrl(null);
      return;
    }

    portraitState = 'removing';

    try {
      const updated = await removePortrait(characterId);
      applyCharacter(updated);
    } catch (error) {
      portraitError =
        error instanceof Error
          ? error.message
          : 'RayMe could not remove this portrait.';
    } finally {
      portraitState = 'idle';
    }
  }

  function addAlternateGreeting() {
    form = {
      ...form,
      alternate_greetings: [...form.alternate_greetings, '']
    };
  }

  function updateAlternateGreeting(index: number, value: string) {
    form = {
      ...form,
      alternate_greetings: form.alternate_greetings.map((greeting, greetingIndex) =>
        greetingIndex === index ? value : greeting
      )
    };
  }

  function removeAlternateGreeting(index: number) {
    form = {
      ...form,
      alternate_greetings: form.alternate_greetings.filter((_, greetingIndex) => greetingIndex !== index)
    };
  }

  function moveAlternateGreeting(index: number, direction: -1 | 1) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= form.alternate_greetings.length) {
      return;
    }

    const nextGreetings = [...form.alternate_greetings];
    const [movedGreeting] = nextGreetings.splice(index, 1);
    nextGreetings.splice(nextIndex, 0, movedGreeting);
    form = { ...form, alternate_greetings: nextGreetings };
  }

  function discardEdits() {
    if (!window.confirm(discardConfirmation)) {
      return;
    }

    if (isCreateMode) {
      form = emptyForm();
      selectedPortraitFile = null;
      setPreviewUrl(null);
      return;
    }

    if (originalCharacter) {
      applyCharacter(originalCharacter);
    } else {
      void loadCharacter();
    }
  }
</script>

<section class="editor" aria-labelledby="character-editor-title">
  <div class="heading">
    <div>
      <p class="eyebrow">{modeLabel}</p>
      <h1 id="character-editor-title">Character Editor</h1>
    </div>

    <div class="actions" aria-label="Character editor actions">
      <button type="button" disabled={saveState === 'saving'} on:click={discardEdits}>
        <span>Discard Edits</span>
      </button>
      <button class="primary" form="character-form" type="submit" disabled={saveState === 'saving'}>
        <Save size={18} strokeWidth={1.8} />
        <span>Save Character</span>
      </button>
    </div>
  </div>

  {#if errorMessage}
    <p class="inline-error" role="alert">{errorMessage}</p>
  {/if}
  {#if successMessage}
    <p class="inline-success" role="status">{successMessage}</p>
  {/if}

  {#if loadState === 'loading'}
    <div class="editor-skeleton" aria-label="Loading character editor"></div>
  {:else if loadState === 'error'}
    <div class="empty-state" role="status">
      <h2>Character unavailable</h2>
      <p>{errorMessage}</p>
      <button class="primary" type="button" on:click={loadCharacter}>Retry</button>
    </div>
  {:else}
    <form id="character-form" class="editor-form" on:submit|preventDefault={saveCharacter}>
      <div class="left-column">
        <CharacterFormSection
          title="Identity"
          eyebrow="Character card"
          description="Core fields and portrait data saved to the RayMe character API."
          labelledby="identity-section"
        >
          <PortraitDropzone
            {previewUrl}
            busy={portraitBusy}
            errorMessage={portraitError}
            onSelect={handlePortraitSelected}
            onRemove={handlePortraitRemove}
          />

          <label>
            <span>Name</span>
            <input name="name" type="text" bind:value={form.name} autocomplete="off" />
          </label>

          <label>
            <span>Description</span>
            <textarea name="description" rows="5" bind:value={form.description}></textarea>
          </label>

          <label>
            <span>Tags</span>
            <textarea name="tags" rows="3" bind:value={form.tagsText}></textarea>
          </label>

          <div class="field-grid">
            <label>
              <span>Creator</span>
              <input name="creator" type="text" bind:value={form.creator} autocomplete="off" />
            </label>

            <label>
              <span>Character version</span>
              <input
                name="character_version"
                type="text"
                bind:value={form.character_version}
                autocomplete="off"
              />
            </label>
          </div>

          {#if lorebookPresent}
            <p class="lorebook-status">Lorebook present - not used in v1</p>
          {/if}
        </CharacterFormSection>
      </div>

      <div class="right-column">
        <CharacterFormSection
          title="Persona"
          description="Prompt fields that shape the character's behavior and situation."
          labelledby="persona-section"
        >
          <label>
            <span>Personality</span>
            <textarea name="personality" rows="6" bind:value={form.personality}></textarea>
          </label>

          <label>
            <span>Scenario</span>
            <textarea name="scenario" rows="6" bind:value={form.scenario}></textarea>
          </label>
        </CharacterFormSection>

        <CharacterFormSection
          title="Opening messages"
          description="The default opening turn and optional alternates for new threads."
          labelledby="openings-section"
        >
          <label>
            <span>First message</span>
            <textarea name="first_mes" rows="5" bind:value={form.first_mes}></textarea>
          </label>

          <label>
            <span>Example messages</span>
            <textarea name="mes_example" rows="6" bind:value={form.mes_example}></textarea>
          </label>

          <div class="alternate-heading">
            <h3>Alternate greetings</h3>
            <button type="button" on:click={addAlternateGreeting}>
              <Plus size={16} strokeWidth={1.8} />
              <span>Add alternate greeting</span>
            </button>
          </div>

          {#if form.alternate_greetings.length === 0}
            <p class="muted-copy">No alternate greetings yet.</p>
          {:else}
            <div class="alternate-list">
              {#each form.alternate_greetings as greeting, index}
                <div class="alternate-item">
                  <textarea
                    rows="3"
                    value={greeting}
                    aria-label={`Edit alternate greeting ${index + 1}`}
                    on:input={(event) =>
                      updateAlternateGreeting(index, (event.currentTarget as HTMLTextAreaElement).value)}
                  ></textarea>
                  <div class="alternate-actions">
                    <button
                      type="button"
                      aria-label={`Move alternate greeting ${index + 1} up`}
                      disabled={index === 0}
                      on:click={() => moveAlternateGreeting(index, -1)}
                    >
                      <ArrowUp size={16} strokeWidth={1.8} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move alternate greeting ${index + 1} down`}
                      disabled={index === form.alternate_greetings.length - 1}
                      on:click={() => moveAlternateGreeting(index, 1)}
                    >
                      <ArrowDown size={16} strokeWidth={1.8} />
                    </button>
                    <button
                      class="danger"
                      type="button"
                      aria-label={`Remove alternate greeting ${index + 1}`}
                      on:click={() => removeAlternateGreeting(index)}
                    >
                      <Trash2 size={16} strokeWidth={1.8} />
                    </button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </CharacterFormSection>

        <CharacterFormSection
          title="System and notes"
          description="Advanced SillyTavern-compatible text fields preserved by RayMe."
          labelledby="system-section"
        >
          <label>
            <span>System prompt</span>
            <textarea name="system_prompt" rows="7" bind:value={form.system_prompt}></textarea>
          </label>

          <label>
            <span>Post-history instructions</span>
            <textarea
              name="post_history_instructions"
              rows="5"
              bind:value={form.post_history_instructions}
            ></textarea>
          </label>

          <label>
            <span>Creator notes</span>
            <textarea name="creator_notes" rows="5" bind:value={form.creator_notes}></textarea>
          </label>

          <label>
            <span>Character notes</span>
            <textarea name="character_notes" rows="5" bind:value={form.character_notes}></textarea>
          </label>
        </CharacterFormSection>
      </div>
    </form>
  {/if}
</section>

<style>
  .editor {
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

  .actions,
  .alternate-heading,
  .alternate-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  .alternate-heading {
    align-items: center;
    justify-content: space-between;
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  button.danger {
    color: var(--color-danger);
  }

  .inline-error,
  .inline-success,
  .lorebook-status,
  .muted-copy {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .inline-error {
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
  }

  .inline-success,
  .lorebook-status {
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }

  .muted-copy {
    background: rgba(9, 19, 40, 0.62);
    color: var(--color-text-muted);
  }

  .editor-form {
    display: grid;
    gap: var(--space-lg);
  }

  .left-column,
  .right-column {
    display: grid;
    align-content: start;
    gap: var(--space-lg);
  }

  .field-grid {
    display: grid;
    gap: var(--space-md);
  }

  label {
    display: grid;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  input,
  textarea {
    width: 100%;
    border: 0;
    border-radius: var(--radius-md);
    background: rgba(6, 14, 32, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  input {
    min-height: 44px;
    padding: 0 var(--space-md);
  }

  textarea {
    min-height: 112px;
    max-height: 280px;
    padding: var(--space-sm) var(--space-md);
    resize: vertical;
  }

  .alternate-list {
    display: grid;
    gap: var(--space-md);
  }

  .alternate-item {
    display: grid;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.54);
    padding: var(--space-sm);
  }

  .alternate-actions {
    justify-content: flex-end;
  }

  .alternate-actions button {
    width: 44px;
    padding: 0;
  }

  .editor-skeleton,
  .empty-state {
    min-height: 320px;
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.66);
  }

  .empty-state {
    display: grid;
    place-items: center;
    gap: var(--space-md);
    padding: var(--space-xl);
    text-align: center;
  }

  .empty-state p {
    color: var(--color-text-muted);
  }

  @media (min-width: 960px) {
    .heading {
      grid-template-columns: 1fr auto;
      align-items: end;
    }

    .editor-form {
      grid-template-columns: minmax(280px, 5fr) minmax(0, 7fr);
      align-items: start;
    }

    .field-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
