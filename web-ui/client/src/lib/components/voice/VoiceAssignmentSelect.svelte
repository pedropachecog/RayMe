<script lang="ts">
  import { FileAudio } from 'lucide-svelte';

  import type { CharacterDefaultVoiceState, TtsEngineId, VoiceSummary } from '$lib/api/types';

  export let voices: VoiceSummary[] = [];
  export let selectedVoiceId: string | null = null;
  export let defaultVoiceState: CharacterDefaultVoiceState = 'none';
  export let defaultVoiceLabel: string | null = null;
  export let disabled = false;
  export let loading = false;
  export let errorMessage = '';
  export let onChange: (voiceId: string | null) => void = () => {};
  export let onCreateVoice: () => void = () => {};

  $: hasVoices = voices.length > 0;
  $: showUnavailable =
    defaultVoiceState === 'unavailable' && Boolean(selectedVoiceId) && !voices.some((voice) => voiceIdFor(voice) === selectedVoiceId);

  function engineLabel(engine: TtsEngineId | null | undefined): string {
    switch (engine) {
      case 'f5':
        return 'F5-TTS';
      case 'xtts_v2':
        return 'XTTS v2';
      case 'qwen3_0_6b':
        return 'Qwen3-TTS 0.6B-Base';
      case 'luxtts':
        return 'LuxTTS';
      case 'chatterbox_turbo':
        return 'Chatterbox Turbo';
      case 'tada_1b':
        return 'TADA 1B';
      case 'voxcpm2':
        return 'VoxCPM2';
      default:
        return engine ? String(engine) : 'Unknown engine';
    }
  }

  function voiceIdFor(voice: VoiceSummary): string {
    return voice.voice_id || voice.id || '';
  }

  function chooseVoice(voiceId: string | null) {
    if (disabled || loading) {
      return;
    }

    onChange(voiceId);
  }
</script>

<section class="voice-assignment" aria-labelledby="default-voice-label">
  <div class="voice-heading">
    <div>
      <h3 id="default-voice-label">Default voice</h3>
      <p>Saved with Save Character.</p>
    </div>
    {#if !hasVoices && !loading}
      <button class="secondary" type="button" disabled={disabled} on:click={onCreateVoice}>
        <FileAudio size={16} strokeWidth={1.8} />
        <span>Create Voice</span>
      </button>
    {/if}
  </div>

  {#if errorMessage}
    <p class="voice-error" role="alert">{errorMessage}</p>
  {/if}

  {#if loading}
    <p class="voice-muted" role="status">Loading saved voices...</p>
  {:else}
    <div class="voice-options" role="radiogroup" aria-labelledby="default-voice-label">
      <button
        class:selected={selectedVoiceId === null}
        type="button"
        role="radio"
        aria-checked={selectedVoiceId === null}
        disabled={disabled}
        on:click={() => chooseVoice(null)}
      >
        <span>No voice assigned</span>
      </button>

      {#each voices as voice (voiceIdFor(voice))}
        {@const voiceId = voiceIdFor(voice)}
        <button
          class:selected={selectedVoiceId === voiceId}
          type="button"
          role="radio"
          aria-checked={selectedVoiceId === voiceId}
          disabled={disabled}
          title={`${voice.name} - ${engineLabel(voice.default_engine)}`}
          on:click={() => chooseVoice(voiceId)}
        >
          <span class="voice-name">{voice.name}</span>
          <span class="voice-engine">{engineLabel(voice.default_engine)}</span>
          {#if voice.default_engine === 'qwen3_0_6b'}
            <span class="caveat">Qwen3-TTS 0.6B-Base caveat</span>
          {/if}
        </button>
      {/each}

      {#if showUnavailable}
        <button class="unavailable" type="button" role="radio" aria-checked="true" disabled>
          <span>{defaultVoiceLabel || 'Voice unavailable'}</span>
          <span class="voice-engine">Voice unavailable</span>
        </button>
      {/if}
    </div>
  {/if}
</section>

<style>
  .voice-assignment {
    display: grid;
    gap: var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    background: rgba(9, 19, 40, 0.56);
  }

  .voice-heading {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  h3,
  p {
    margin: 0;
  }

  h3 {
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 600;
    line-height: var(--line-body);
  }

  .voice-heading p,
  .voice-muted {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .voice-error {
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(255, 113, 108, 0.12);
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .voice-options {
    display: grid;
    gap: var(--space-sm);
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: flex-start;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(20, 31, 56, 0.72);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    text-align: left;
  }

  button.selected {
    background: rgba(182, 160, 255, 0.22);
    box-shadow: inset 0 0 0 1px rgba(182, 160, 255, 0.42);
  }

  button.secondary {
    flex-shrink: 0;
    justify-content: center;
    padding-inline: var(--space-md);
  }

  button.unavailable {
    color: var(--color-danger);
  }

  .voice-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .voice-engine,
  .caveat {
    flex-shrink: 0;
    border-radius: var(--radius-sm);
    padding: 2px var(--space-xs);
    background: rgba(6, 14, 32, 0.72);
    color: var(--color-text-muted);
  }

  .caveat {
    color: var(--color-primary);
  }

  @media (max-width: 520px) {
    .voice-heading {
      display: grid;
    }

    button {
      flex-wrap: wrap;
    }
  }
</style>
