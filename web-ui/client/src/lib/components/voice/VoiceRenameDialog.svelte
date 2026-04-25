<script lang="ts">
  import type { VoiceSummary } from '$lib/api/types';

  export let open = false;
  export let voice: VoiceSummary | null = null;
  export let submitting = false;
  export let onSave: (name: string) => void = () => {};
  export let onCancel: () => void = () => {};

  let draftName = '';
  let activeVoiceId: string | null = null;

  $: if (open && voice && activeVoiceId !== voice.voice_id) {
    activeVoiceId = voice.voice_id;
    draftName = voice.name;
  }

  $: if (!open) {
    activeVoiceId = null;
  }

  $: canSave = Boolean(draftName.trim()) && draftName.trim() !== (voice?.name ?? '');

  function submitRename() {
    if (canSave) {
      onSave(draftName.trim());
    }
  }
</script>

{#if open && voice}
  <div class="dialog-backdrop" role="presentation">
    <div
      class="dialog-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="voice-rename-title"
    >
      <div>
        <p class="eyebrow">Voice Library</p>
        <h2 id="voice-rename-title">Rename Voice</h2>
      </div>

      <label>
        <span>Voice name</span>
        <input aria-label="Rename voice name" type="text" bind:value={draftName} autocomplete="off" />
      </label>

      <div class="dialog-actions">
        <button class="secondary" type="button" disabled={submitting} on:click={onCancel}>Cancel</button>
        <button class="primary" type="button" disabled={!canSave || submitting} on:click={submitRename}>
          {submitting ? 'Renaming...' : 'Save Rename'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: grid;
    place-items: center;
    padding: var(--space-lg);
    background: rgba(6, 14, 32, 0.72);
    backdrop-filter: blur(16px);
  }

  .dialog-panel {
    display: grid;
    width: min(100%, 420px);
    gap: var(--space-lg);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(25, 37, 64, 0.94);
    box-shadow: var(--shadow-float);
  }

  .eyebrow,
  h2 {
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

  label {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  input {
    width: 100%;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(6, 14, 32, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .dialog-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-sm);
  }

  button {
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .secondary {
    background: rgba(20, 31, 56, 0.82);
  }

  .primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }
</style>
