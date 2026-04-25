<script lang="ts">
  import { Pause, Play, RefreshCw } from 'lucide-svelte';

  export let previewText = 'The line is open. This is how the saved RayMe voice will sound.';
  export let useDefaultEngine = true;
  export let disabled = true;
  export let state: 'idle' | 'synthesizing' | 'ready' | 'error' = 'idle';
  export let audioUrl: string | null = null;
  export let errorMessage = '';
  export let onPreview: () => void = () => {};

  let playing = false;
  let audioElement: HTMLAudioElement;

  $: if (audioUrl) {
    playing = false;
    if (audioElement) {
      audioElement.load();
    }
  }

  function togglePlayback() {
    if (!audioElement || !audioUrl) {
      return;
    }

    if (playing) {
      audioElement.pause();
      playing = false;
      return;
    }

    playing = true;
    void audioElement.play().catch(() => {
      playing = false;
    });
  }
</script>

<section class="preview-panel" aria-labelledby="preview-step-title">
  <div class="section-heading">
    <div>
      <h2 id="preview-step-title">Preview Voice</h2>
      <p>Preview is optional. A failed preview keeps every field editable and Save Voice stays available when required fields are valid.</p>
    </div>
    <label class="toggle">
      <input type="checkbox" bind:checked={useDefaultEngine} />
      <span>Use default engine</span>
    </label>
  </div>

  <label>
    <span>Preview text</span>
    <textarea aria-label="Preview text" bind:value={previewText} rows="3"></textarea>
  </label>

  <div class="preview-actions">
    <button class="primary" type="button" disabled={disabled || state === 'synthesizing'} on:click={onPreview}>
      <RefreshCw size={16} strokeWidth={1.8} aria-hidden="true" />
      <span>{state === 'synthesizing' ? 'Synthesizing...' : 'Preview Voice'}</span>
    </button>
    <button type="button" disabled={!audioUrl} on:click={togglePlayback} aria-label={playing ? 'Pause preview audio' : 'Play preview audio'}>
      {#if playing}
        <Pause size={16} strokeWidth={1.8} aria-hidden="true" />
      {:else}
        <Play size={16} strokeWidth={1.8} aria-hidden="true" />
      {/if}
      <span>{playing ? 'Pause' : 'Play'}</span>
    </button>
  </div>

  {#if audioUrl}
    <audio bind:this={audioElement} src={audioUrl} on:ended={() => (playing = false)} preload="metadata"></audio>
  {/if}

  {#if state === 'ready'}
    <p class="success" role="status">Preview ready.</p>
  {:else if state === 'error'}
    <p class="error" role="alert">{errorMessage || 'Preview failed. You can retry or save this voice anyway.'}</p>
  {/if}
</section>

<style>
  .preview-panel {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.72);
  }

  .section-heading,
  .preview-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-md);
  }

  h2,
  p {
    margin: 0;
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

  label,
  .toggle {
    display: grid;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .toggle {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(9, 19, 40, 0.72);
  }

  textarea {
    min-height: 92px;
    border: 0;
    border-radius: var(--radius-md);
    padding: var(--space-md);
    resize: vertical;
    background: rgba(6, 14, 32, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 400;
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
    background: rgba(9, 19, 40, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  .success,
  .error {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .success {
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }

  .error {
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
  }
</style>
