<script lang="ts">
  import type { VoxCpm2EngineSettings } from '$lib/api/types';

  type VoxCpm2SettingsState = Required<VoxCpm2EngineSettings>;

  const DEFAULT_SETTINGS: VoxCpm2SettingsState = {
    cloning_mode: 'reference_only',
    style_prompt: '',
    cfg_value: 2.0,
    inference_timesteps: 10,
    normalize: false,
    denoise: false
  };

  export let settings: VoxCpm2SettingsState = { ...DEFAULT_SETTINGS };
  export let transcript = '';

  $: normalizedSettings = { ...DEFAULT_SETTINGS, ...settings };
  $: showMissingTranscriptWarning =
    normalizedSettings.cloning_mode === 'transcript_guided' && !transcript.trim();

  function updateSetting<Key extends keyof VoxCpm2SettingsState>(
    key: Key,
    value: VoxCpm2SettingsState[Key]
  ) {
    settings = { ...normalizedSettings, [key]: value };
  }

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement).value;
  }

  function checkedValue(event: Event): boolean {
    return (event.currentTarget as HTMLInputElement).checked;
  }

  function numberValue(event: Event, min: number, max: number): number {
    const parsed = Number(inputValue(event));
    if (Number.isNaN(parsed)) {
      return min;
    }
    return Math.min(max, Math.max(min, parsed));
  }
</script>

<section class="voxcpm2-controls" aria-labelledby="voxcpm2-controls-title">
  <div class="control-heading">
    <div>
      <h2 id="voxcpm2-controls-title">VoxCPM2</h2>
      <p>Transcript-guided mode may improve VoxCPM2 results</p>
    </div>
  </div>

  {#if showMissingTranscriptWarning}
    <p class="warning" role="alert">No transcript saved. VoxCPM2 will use reference-only cloning for this sample.</p>
  {/if}

  <fieldset class="mode-options">
    <legend>Cloning mode</legend>
    <label>
      <input
        type="radio"
        name="voxcpm2-cloning-mode"
        value="reference_only"
        checked={normalizedSettings.cloning_mode === 'reference_only'}
        on:change={() => updateSetting('cloning_mode', 'reference_only')}
      />
      <span>Reference only</span>
    </label>
    <label>
      <input
        type="radio"
        name="voxcpm2-cloning-mode"
        value="transcript_guided"
        checked={normalizedSettings.cloning_mode === 'transcript_guided'}
        on:change={() => updateSetting('cloning_mode', 'transcript_guided')}
      />
      <span>Transcript guided</span>
    </label>
  </fieldset>

  <label class="wide">
    <span>Style prompt</span>
    <input
      aria-label="Style prompt"
      type="text"
      maxlength="300"
      value={normalizedSettings.style_prompt}
      on:input={(event) => updateSetting('style_prompt', inputValue(event))}
    />
  </label>

  <div class="numeric-grid">
    <label>
      <span>CFG value {normalizedSettings.cfg_value.toFixed(1)}</span>
      <input
        aria-label="CFG value"
        type="number"
        min="1"
        max="3"
        step="0.1"
        value={normalizedSettings.cfg_value}
        on:input={(event) => updateSetting('cfg_value', numberValue(event, 1, 3))}
      />
    </label>

    <label>
      <span>Inference timesteps {normalizedSettings.inference_timesteps}</span>
      <input
        aria-label="Inference timesteps"
        type="number"
        min="4"
        max="30"
        step="1"
        value={normalizedSettings.inference_timesteps}
        on:input={(event) =>
          updateSetting('inference_timesteps', Math.round(numberValue(event, 4, 30)))}
      />
    </label>
  </div>

  <div class="toggle-grid">
    <label class="toggle">
      <input
        aria-label="Normalize"
        type="checkbox"
        checked={normalizedSettings.normalize}
        on:change={(event) => updateSetting('normalize', checkedValue(event))}
      />
      <span>Normalize</span>
    </label>

    <label class="toggle">
      <input
        aria-label="Denoise"
        type="checkbox"
        checked={normalizedSettings.denoise}
        on:change={(event) => updateSetting('denoise', checkedValue(event))}
      />
      <span>Denoise</span>
    </label>
  </div>
</section>

<style>
  .voxcpm2-controls {
    display: grid;
    min-width: 0;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.72);
  }

  .control-heading {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-md);
  }

  h2,
  p,
  fieldset {
    margin: 0;
  }

  h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p,
  legend,
  label {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .warning {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 199, 87, 0.12);
    color: var(--color-text);
  }

  .mode-options,
  .numeric-grid,
  .toggle-grid {
    display: grid;
    min-width: 0;
    gap: var(--space-sm);
  }

  .mode-options {
    border: 0;
    padding: 0;
  }

  .mode-options label,
  .toggle {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(9, 19, 40, 0.72);
    color: var(--color-text);
  }

  .wide,
  .numeric-grid label {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
    color: var(--color-text);
  }

  input[type='text'],
  input[type='number'] {
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

  input[type='radio'],
  input[type='checkbox'] {
    width: 18px;
    height: 18px;
    margin: 0;
  }

  @media (min-width: 720px) {
    .mode-options,
    .numeric-grid,
    .toggle-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .mode-options legend {
      grid-column: 1 / -1;
    }
  }
</style>
