<script lang="ts">
  export let saveAiAudio = true;
  export let saveMicAudio = false;
  export let onSaveAiAudioChange: (value: boolean) => void = () => {};
  export let onSaveMicAudioChange: (value: boolean) => void = () => {};
</script>

<section class="settings-panel" aria-labelledby="audio-settings-title">
  <div>
    <p class="eyebrow">Audio defaults</p>
    <h2 id="audio-settings-title">Saved call audio</h2>
  </div>

  <label class="toggle-row">
    <span>
      <strong>Save AI audio</strong>
      <small>On by default; future AI call audio can be stored for replay.</small>
    </span>
    <input
      type="checkbox"
      role="switch"
      checked={saveAiAudio}
      on:change={(event) => onSaveAiAudioChange((event.currentTarget as HTMLInputElement).checked)}
    />
  </label>

  <label class="toggle-row">
    <span>
      <strong>Save mic audio</strong>
      <small>Off by default; future calls will not store your microphone audio unless enabled.</small>
    </span>
    <input
      type="checkbox"
      role="switch"
      checked={saveMicAudio}
      on:change={(event) => onSaveMicAudioChange((event.currentTarget as HTMLInputElement).checked)}
    />
  </label>
</section>

<style>
  .settings-panel {
    display: grid;
    gap: var(--space-lg);
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.78);
    padding: var(--space-lg);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  .eyebrow,
  h2,
  strong,
  small {
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

  .toggle-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-md);
    color: var(--color-text);
  }

  .toggle-row span {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
  }

  strong {
    font-size: var(--font-body);
    font-weight: 600;
    line-height: var(--line-body);
  }

  small {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  input[type='checkbox'] {
    width: 48px;
    height: 28px;
    margin: 0;
    accent-color: var(--color-primary);
  }
</style>
