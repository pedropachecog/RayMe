<script lang="ts">
  import { ImagePlus, RefreshCw, Trash2, Upload } from 'lucide-svelte';

  export let previewUrl: string | null = null;
  export let fallbackInitials = '';
  export let busy = false;
  export let errorMessage = '';
  export let onSelect: (file: File) => void | Promise<void> = () => {};
  export let onRemove: () => void | Promise<void> = () => {};

  let fileInput: HTMLInputElement;
  let dragActive = false;
  let localError = '';

  const acceptedMimeTypes = ['image/png', 'image/jpeg', 'image/webp'];
  const acceptedLabel = 'PNG, JPG, or WebP';

  $: visibleError = errorMessage || localError;

  function openPicker() {
    fileInput?.click();
  }

  async function selectFile(file: File | undefined) {
    if (!file) {
      return;
    }

    if (!acceptedMimeTypes.includes(file.type)) {
      localError = `Portrait import failed. Accepted formats: ${acceptedLabel}.`;
      return;
    }

    localError = '';
    await onSelect(file);
  }

  async function handleInput(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    await selectFile(input.files?.[0]);
    input.value = '';
  }

  async function handleDrop(event: DragEvent) {
    event.preventDefault();
    dragActive = false;
    await selectFile(event.dataTransfer?.files?.[0]);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openPicker();
    }
  }
</script>

<div class="portrait-control">
  <input
    bind:this={fileInput}
    class="file-input"
    type="file"
    accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
    on:change={handleInput}
  />

  <div
    class:drag-active={dragActive}
    class="dropzone"
    role="button"
    tabindex="0"
    aria-label={previewUrl ? 'Replace character portrait' : 'Upload character portrait'}
    on:click={openPicker}
    on:keydown={handleKeydown}
    on:dragenter|preventDefault={() => (dragActive = true)}
    on:dragover|preventDefault={() => (dragActive = true)}
    on:dragleave|preventDefault={() => (dragActive = false)}
    on:drop={handleDrop}
  >
    {#if previewUrl}
      <img src={previewUrl} alt="Character portrait preview" />
      <span class="replace-chip">
        <RefreshCw size={16} strokeWidth={1.8} />
        Replace portrait
      </span>
    {:else}
      <span class="empty-preview" aria-hidden="true">
        {#if fallbackInitials}
          <span class="fallback-initials">{fallbackInitials}</span>
        {:else}
          <ImagePlus size={28} strokeWidth={1.8} />
        {/if}
      </span>
      <span class="dropzone-copy">
        <strong>Upload portrait</strong>
        <small>{acceptedLabel}</small>
      </span>
    {/if}
  </div>

  <div class="portrait-actions">
    <button type="button" disabled={busy} on:click={openPicker}>
      <Upload size={16} strokeWidth={1.8} />
      <span>{previewUrl ? 'Replace' : 'Upload'}</span>
    </button>
    <button class="danger" type="button" disabled={busy || !previewUrl} on:click={onRemove}>
      <Trash2 size={16} strokeWidth={1.8} />
      <span>Remove portrait</span>
    </button>
  </div>

  {#if visibleError}
    <p class="portrait-error" role="alert">{visibleError}</p>
  {/if}
</div>

<style>
  .portrait-control {
    display: grid;
    gap: var(--space-sm);
  }

  .file-input {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .dropzone {
    position: relative;
    display: grid;
    min-height: 260px;
    place-items: center;
    overflow: hidden;
    border-radius: var(--radius-md);
    background:
      linear-gradient(180deg, rgba(182, 160, 255, 0.1), rgba(112, 170, 255, 0.04)),
      rgba(9, 19, 40, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    cursor: pointer;
  }

  .dropzone.drag-active {
    box-shadow:
      inset 0 0 0 2px rgba(182, 160, 255, 0.72),
      0 0 28px rgba(182, 160, 255, 0.16);
  }

  .dropzone img {
    width: 100%;
    height: 100%;
    min-height: 260px;
    object-fit: cover;
  }

  .empty-preview {
    display: grid;
    width: 72px;
    height: 72px;
    place-items: center;
    border-radius: var(--radius-md);
    background: rgba(182, 160, 255, 0.14);
    color: var(--color-primary);
  }

  .fallback-initials {
    color: var(--color-surface);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .dropzone-copy {
    display: grid;
    gap: var(--space-xs);
    margin-top: calc(var(--space-2xl) + var(--space-sm));
    position: absolute;
    text-align: center;
  }

  .dropzone-copy strong,
  .replace-chip {
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .dropzone-copy small {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .replace-chip {
    position: absolute;
    inset: auto var(--space-md) var(--space-md) auto;
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    gap: var(--space-xs);
    border-radius: var(--radius-md);
    padding: 0 var(--space-sm);
    background: rgba(9, 19, 40, 0.82);
    backdrop-filter: blur(12px);
  }

  .portrait-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
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
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .danger {
    color: var(--color-danger);
  }

  .portrait-error {
    margin: 0;
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }
</style>
