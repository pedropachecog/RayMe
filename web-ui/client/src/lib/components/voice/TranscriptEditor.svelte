<script lang="ts">
  export let transcript = '';
  export let disabled = true;
  export let state: 'idle' | 'pending' | 'ready' | 'error' = 'idle';
  export let errorMessage = '';
  export let onTranscribe: () => void = () => {};
</script>

<section class="transcript-editor" aria-labelledby="transcript-step-title">
  <div class="section-heading">
    <div>
      <h2 id="transcript-step-title">Transcribe Sample</h2>
      <p>
        {#if state === 'pending'}
          Transcribing sample...
        {:else if state === 'error'}
          RayMe could not process this sample. Check the file format, keep the sample near 6-15 seconds, and try again.
        {:else}
          Review and edit the transcript before previewing the voice.
        {/if}
      </p>
    </div>
    <button type="button" disabled={disabled || state === 'pending'} on:click={onTranscribe}>
      {state === 'error' ? 'Retry Transcript' : 'Transcribe Sample'}
    </button>
  </div>

  <label>
    <span>Reference transcript</span>
    <textarea
      aria-label="Reference transcript"
      bind:value={transcript}
      disabled={disabled || state === 'pending'}
      rows="7"
    ></textarea>
  </label>

  {#if errorMessage}
    <p class="error" role="alert">{errorMessage}</p>
  {/if}
</section>

<style>
  .transcript-editor {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.72);
  }

  .section-heading {
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

  button {
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(9, 19, 40, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  label {
    display: grid;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  textarea {
    min-height: 160px;
    max-height: 360px;
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

  textarea:focus {
    box-shadow: inset 0 0 0 2px rgba(182, 160, 255, 0.72);
  }

  .error {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }
</style>
