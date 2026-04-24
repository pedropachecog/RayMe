<script lang="ts">
  import { FileUp, X } from 'lucide-svelte';

  import { importCharacterCard } from '$lib/api/characters';
  import type { CharacterImportResult } from '$lib/api/types';

  export let open = false;
  export let onClose: () => void = () => {};
  export let onImported: (result: CharacterImportResult) => void = () => {};

  const staticWarningChips = ['Fields preserved'];
  const unsupportedFileMessage = 'Unsupported file';
  const malformedJsonMessage = 'Malformed JSON';
  const unreadablePngMessage = 'Unreadable PNG metadata';
  const unsafeContentMessage = 'Unsafe content';

  let selectedFile: File | null = null;
  let importState: 'idle' | 'parsing' | 'success' | 'error' = 'idle';
  let errorMessage = '';
  let warnings: string[] = [];

  $: warningChips = Array.from(new Set([...staticWarningChips, ...normalizeWarnings(warnings)]));

  function chooseFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    selectedFile = input.files?.[0] ?? null;
    errorMessage = '';
    importState = 'idle';
  }

  async function submitImport() {
    if (!selectedFile || importState === 'parsing') {
      return;
    }

    if (!isSupportedFile(selectedFile)) {
      importState = 'error';
      errorMessage = unsupportedFileMessage;
      return;
    }

    importState = 'parsing';
    errorMessage = '';

    try {
      const result = await importCharacterCard(selectedFile);
      warnings = result.warnings ?? [];
      importState = 'success';
      onImported(result);
    } catch (error) {
      importState = 'error';
      errorMessage = classifyImportError(error, selectedFile);
    }
  }

  function close() {
    if (importState !== 'parsing') {
      selectedFile = null;
      errorMessage = '';
      warnings = [];
      importState = 'idle';
      onClose();
    }
  }

  function isSupportedFile(file: File): boolean {
    const name = file.name.toLowerCase();
    return name.endsWith('.json') || name.endsWith('.png') || file.type === 'application/json' || file.type === 'image/png';
  }

  function normalizeWarnings(values: string[]): string[] {
    const chips: string[] = [];
    for (const warning of values) {
      const normalized = warning.toLowerCase();
      if (normalized.includes('lorebook')) {
        chips.push('Lorebook present - not used in v1');
      } else if (normalized.includes('ignored') || normalized.includes('unsupported')) {
        chips.push('Unsupported fields ignored');
      } else if (warning.trim()) {
        chips.push(warning.trim());
      }
    }
    return chips;
  }

  function classifyImportError(error: unknown, file: File): string {
    const message = error instanceof Error ? error.message.toLowerCase() : '';
    if (message.includes('unsupported') || message.includes('415')) {
      return unsupportedFileMessage;
    }
    if (message.includes('unsafe') || message.includes('dangerous') || message.includes('xss')) {
      return unsafeContentMessage;
    }
    if (message.includes('png') || file.name.toLowerCase().endsWith('.png')) {
      return unreadablePngMessage;
    }
    if (message.includes('json') || file.name.toLowerCase().endsWith('.json')) {
      return malformedJsonMessage;
    }
    return unsafeContentMessage;
  }
</script>

{#if open}
  <div class="dialog-backdrop" role="presentation">
    <div class="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="import-card-title">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">Character card</p>
          <h2 id="import-card-title">Import Character</h2>
        </div>
        <button class="icon-button" type="button" aria-label="Close import" on:click={close}>
          <X size={20} strokeWidth={1.8} />
        </button>
      </div>

      <label class:active={importState === 'parsing'} class="dropzone">
        <FileUp size={24} strokeWidth={1.8} />
        <span>{selectedFile?.name ?? 'Choose a JSON or PNG character card'}</span>
        <input
          type="file"
          accept=".json,.png,application/json,image/png"
          disabled={importState === 'parsing'}
          on:change={chooseFile}
        />
      </label>

      <div class="warning-chips" aria-label="Import handling">
        {#each warningChips as warning}
          <span>{warning}</span>
        {/each}
      </div>

      {#if importState === 'parsing'}
        <p class="progress" role="status">Reading character card...</p>
      {:else if errorMessage}
        <p class="inline-error" role="alert">{errorMessage}</p>
      {/if}

      <div class="dialog-actions">
        <button type="button" disabled={importState === 'parsing'} on:click={close}>Cancel</button>
        <button
          class="primary"
          type="button"
          disabled={!selectedFile || importState === 'parsing'}
          on:click={submitImport}
        >
          <FileUp size={18} strokeWidth={1.8} />
          <span>Import Character</span>
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 70;
    display: grid;
    place-items: center;
    padding: var(--space-lg);
    background: rgba(6, 14, 32, 0.72);
    backdrop-filter: blur(16px);
  }

  .dialog-panel {
    display: grid;
    width: min(100%, 520px);
    gap: var(--space-lg);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(25, 37, 64, 0.94);
    box-shadow: var(--shadow-float);
  }

  .dialog-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-md);
  }

  .eyebrow,
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

  h2 {
    margin-top: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
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

  .icon-button {
    width: 44px;
    min-width: 44px;
    padding: 0;
    color: var(--color-text-muted);
  }

  .dropzone {
    position: relative;
    display: grid;
    min-height: 160px;
    place-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
    text-align: center;
    box-shadow: inset 0 0 0 2px rgba(64, 72, 93, 0.18);
  }

  .dropzone.active {
    box-shadow: inset 0 0 0 2px rgba(182, 160, 255, 0.64);
  }

  .dropzone input {
    position: absolute;
    inset: 0;
    cursor: pointer;
    opacity: 0;
  }

  .warning-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
  }

  .warning-chips span {
    border-radius: var(--radius-md);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(0, 227, 253, 0.12);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .progress,
  .inline-error {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .progress {
    background: rgba(182, 160, 255, 0.14);
    color: var(--color-text);
  }

  .inline-error {
    background: rgba(255, 113, 108, 0.12);
    color: var(--color-danger);
  }

  .dialog-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-sm);
  }
</style>
