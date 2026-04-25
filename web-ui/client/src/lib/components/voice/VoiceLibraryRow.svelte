<script lang="ts">
  import { Pencil, Play, Trash2 } from 'lucide-svelte';

  import type { VoiceSummary, VoiceTestPlayPayload } from '$lib/api/types';

  export let voice: VoiceSummary;
  export let engineLabel = '';
  export let testing = false;
  export let onTestPlay: (voice: VoiceSummary, payload: VoiceTestPlayPayload) => void = () => {};
  export let onRename: (voice: VoiceSummary) => void = () => {};
  export let onDelete: (voice: VoiceSummary) => void = () => {};

  let testText = '';
  let useDefaultEngine = true;

  $: transcriptLabel = voice.reference_transcript?.trim()
    ? 'Transcript present'
    : 'No transcript stored';
  $: assignmentStatus =
    typeof voice.metadata?.assignment_status === 'string'
      ? voice.metadata.assignment_status
      : voice.unavailable_label || 'No assignments';
  $: updatedLabel = formatTimestamp(voice.updated_at ?? voice.created_at);
  $: createdLabel = formatTimestamp(voice.created_at);

  function playVoice() {
    onTestPlay(voice, {
      text: testText.trim(),
      use_default_engine: useDefaultEngine,
      engine: useDefaultEngine ? null : voice.default_engine
    });
  }

  function formatTimestamp(value?: string | null) {
    if (!value) {
      return 'Time not available';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short'
    }).format(date);
  }
</script>

<li class="voice-row" aria-label={`${voice.name} voice row`}>
  <div class="row-main">
    <div class="title-line">
      <h3>{voice.name}</h3>
      <span>{engineLabel || voice.default_engine}</span>
    </div>

    <div class="metadata" aria-label="Voice metadata">
      <span>{transcriptLabel}</span>
      <span>Created {createdLabel}</span>
      <span>Updated {updatedLabel}</span>
      <span>{assignmentStatus}</span>
    </div>
  </div>

  <label class="test-text">
    <span>Test phrase</span>
    <input type="text" placeholder="Type a test phrase" bind:value={testText} />
  </label>

  <label class="toggle">
    <input type="checkbox" bind:checked={useDefaultEngine} />
    <span>Use default engine</span>
  </label>

  <div class="actions">
    <button type="button" disabled={testing} on:click={playVoice}>
      <Play size={16} strokeWidth={1.8} aria-hidden="true" />
      <span>Test Voice</span>
    </button>
    <button type="button" on:click={() => onRename(voice)}>
      <Pencil size={16} strokeWidth={1.8} aria-hidden="true" />
      <span>Rename Voice</span>
    </button>
    <button class="danger" type="button" on:click={() => onDelete(voice)}>
      <Trash2 size={16} strokeWidth={1.8} aria-hidden="true" />
      <span>Delete Voice</span>
    </button>
  </div>

  {#if testing}
    <p class="row-status" role="status">Testing voice...</p>
  {/if}
</li>

<style>
  .voice-row {
    display: grid;
    min-height: 88px;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(9, 19, 40, 0.74);
  }

  .row-main,
  .test-text {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
  }

  .title-line,
  .metadata,
  .actions {
    display: flex;
    min-width: 0;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-sm);
  }

  h3,
  p {
    margin: 0;
  }

  h3 {
    min-width: 0;
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 600;
    line-height: var(--line-body);
    overflow-wrap: anywhere;
  }

  .title-line span,
  .metadata span,
  .row-status {
    border-radius: var(--radius-sm);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(25, 37, 64, 0.86);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .test-text,
  .toggle {
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .toggle {
    display: inline-flex;
    width: fit-content;
    min-height: 44px;
    align-items: center;
    gap: var(--space-sm);
  }

  input[type='text'] {
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

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.86);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .danger {
    color: var(--color-danger);
  }

  .row-status {
    width: fit-content;
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }
</style>
