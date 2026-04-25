<script lang="ts">
  export let threshold = 0.5;
  export let endSilenceMs = 700;
  export let onThresholdChange: (value: number) => void = () => {};
  export let onEndSilenceChange: (value: number) => void = () => {};

  function numericInput(event: Event) {
    return Number((event.currentTarget as HTMLInputElement).value);
  }
</script>

<section class="settings-panel" aria-labelledby="vad-settings-title">
  <div class="panel-heading">
    <div>
      <p class="eyebrow">Voice activity detection</p>
      <h2 id="vad-settings-title">VAD values</h2>
    </div>
    <span>Coming in Call Feel</span>
  </div>

  <label>
    <span>VAD threshold</span>
    <input
      type="range"
      min="0"
      max="1"
      step="0.05"
      value={threshold}
      on:input={(event) => onThresholdChange(numericInput(event))}
    />
    <output>{threshold.toFixed(2)}</output>
  </label>

  <label>
    <span>End-of-utterance silence</span>
    <input
      type="number"
      min="100"
      max="3000"
      step="50"
      value={endSilenceMs}
      on:input={(event) => onEndSilenceChange(numericInput(event))}
    />
    <small>Stored now; call behavior wiring belongs to Call Feel.</small>
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

  .panel-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-md);
  }

  .eyebrow,
  h2,
  label,
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

  .panel-heading > span {
    display: inline-flex;
    min-height: 32px;
    align-items: center;
    border-radius: var(--radius-md);
    padding: 0 10px;
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    white-space: nowrap;
  }

  label {
    display: grid;
    gap: var(--space-sm);
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

  input[type='range'] {
    padding: 0;
    accent-color: var(--color-primary);
  }

  output,
  small {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }
</style>
