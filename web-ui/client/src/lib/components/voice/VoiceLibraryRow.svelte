<script lang="ts">
  import { Pencil, Play, RefreshCw, Trash2 } from 'lucide-svelte';

  import type {
    TtsModelReadiness,
    TtsPromptReadiness,
    VoiceSummary,
    VoiceTestPlayPayload
  } from '$lib/api/types';

  type VoiceLibraryOperation = 'idle' | 'preparing' | 'testing' | 'failed';

  export let voice: VoiceSummary;
  export let engineLabel = '';
  export let modelReadiness: TtsModelReadiness = { state: 'idle', engine_id: null };
  export let promptReadiness: TtsPromptReadiness = { state: 'none' };
  export let operation: VoiceLibraryOperation = 'idle';
  export let operationError = '';
  export let testAudioUrl: string | null = null;
  export let onTestPlay: (voice: VoiceSummary, payload: VoiceTestPlayPayload) => void = () => {};
  export let onRetryPreparation: (voice: VoiceSummary, payload: VoiceTestPlayPayload) => void = () => {};
  export let onRename: (voice: VoiceSummary) => void = () => {};
  export let onDelete: (voice: VoiceSummary) => void = () => {};

  let testText = '';
  let useDefaultEngine = true;
  let speechSpeed = voiceSpeechSpeed(voice);

  $: transcriptLabel = voice.reference_transcript?.trim()
    ? 'Transcript present'
    : 'No transcript stored';
  $: assignmentStatus =
    typeof voice.metadata?.assignment_status === 'string'
      ? voice.metadata.assignment_status
      : voice.unavailable_label || 'No assignments';
  $: updatedLabel = formatTimestamp(voice.updated_at ?? voice.created_at);
  $: createdLabel = formatTimestamp(voice.created_at);
  $: isQwenVoice = voice.default_engine === 'qwen3_1_7b';
  $: modelStatusCopy = modelReadinessCopy(modelReadiness);
  $: promptStatusCopy = promptReadinessCopy(promptReadiness);

  function playVoice() {
    if (operation === 'preparing' || operation === 'testing') {
      return;
    }
    onTestPlay(voice, testPayload());
  }

  function retryVoice() {
    onRetryPreparation(voice, testPayload());
  }

  function testPayload(): VoiceTestPlayPayload {
    return {
      text: testText.trim(),
      use_default_engine: useDefaultEngine,
      engine: useDefaultEngine ? null : voice.default_engine,
      speech_speed: speechSpeed
    };
  }

  function modelReadinessCopy(readiness: TtsModelReadiness) {
    if (readiness.state === 'loading') return 'Loading Qwen3-TTS 1.7B…';
    if (readiness.state === 'resident') return 'Qwen3-TTS 1.7B loaded';
    if (readiness.state === 'failed' || readiness.state === 'unavailable') {
      return 'Qwen3-TTS 1.7B unavailable';
    }
    return 'Qwen3-TTS 1.7B not loaded';
  }

  function promptReadinessCopy(readiness: TtsPromptReadiness) {
    if (readiness.state === 'prewarming') return 'Preparing saved voice…';
    if (readiness.state === 'ready') return 'Saved voice ready';
    if (readiness.state === 'failed') return 'Voice preparation failed';
    return 'Voice not prepared';
  }

  function voiceSpeechSpeed(value: VoiceSummary) {
    const metadata = value.metadata ?? {};
    const rawSpeed = metadata.speech_speed;
    if (typeof rawSpeed === 'number') {
      return rawSpeed;
    }
    const engineSettings = metadata.engine_settings;
    if (engineSettings && typeof engineSettings === 'object' && !Array.isArray(engineSettings)) {
      const engineValue = (engineSettings as Record<string, unknown>)[value.default_engine];
      if (engineValue && typeof engineValue === 'object' && !Array.isArray(engineValue)) {
        const speed = (engineValue as Record<string, unknown>).speech_speed;
        if (typeof speed === 'number') {
          return speed;
        }
      }
    }
    return 1.0;
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

  <label class="speed-control">
    <span>Speech speed {speechSpeed.toFixed(2)}x</span>
    <input
      aria-label={`${voice.name} speech speed`}
      type="range"
      min="0.5"
      max="1.5"
      step="0.05"
      bind:value={speechSpeed}
    />
  </label>

  {#if isQwenVoice}
    <div class="readiness" aria-label={`${voice.name} Qwen readiness`}>
      <span>Model</span>
      <strong>{modelStatusCopy}</strong>
      <span>Saved voice</span>
      <strong>{promptStatusCopy}</strong>
    </div>
  {/if}

  <div class="actions">
    <button
      type="button"
      aria-disabled={operation === 'preparing' || operation === 'testing'}
      on:click={operation === 'failed' && isQwenVoice ? retryVoice : playVoice}
    >
      {#if operation === 'preparing' || (operation === 'failed' && isQwenVoice)}
        <RefreshCw
          class={operation === 'preparing' ? 'preparing-icon' : undefined}
          size={16}
          strokeWidth={1.8}
          aria-hidden="true"
        />
      {:else}
        <Play size={16} strokeWidth={1.8} aria-hidden="true" />
      {/if}
      <span>
        {operation === 'preparing'
          ? 'Preparing voice…'
          : operation === 'testing'
            ? 'Testing voice…'
            : operation === 'failed' && isQwenVoice
              ? 'Retry Preparation'
              : 'Test Voice'}
      </span>
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

  {#if operation === 'preparing'}
    <p class="row-status" role="status">Preparing saved voice…</p>
  {:else if operation === 'testing'}
    <p class="row-status" role="status">Testing voice…</p>
  {:else if isQwenVoice && promptReadiness.state === 'ready'}
    <p class="row-status" role="status">Saved voice ready</p>
  {/if}
  {#if operationError}
    <p class="row-error" role="alert">{operationError}</p>
  {/if}
  {#if testAudioUrl}
    <div class="test-player" aria-label={`${voice.name} test playback`}>
      <span>Generated test</span>
      <audio aria-label={`${voice.name} generated test audio`} controls preload="metadata" src={testAudioUrl}></audio>
    </div>
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
  .toggle,
  .speed-control,
  .test-player,
  .readiness {
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

  .readiness {
    display: grid;
    min-width: 0;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: var(--space-xs) var(--space-sm);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(20, 31, 56, 0.6);
  }

  .readiness span {
    color: var(--color-text-muted);
  }

  .readiness strong {
    min-width: 0;
    color: var(--color-text);
    overflow-wrap: anywhere;
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

  input[type='range'],
  audio {
    width: 100%;
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
    overflow-wrap: anywhere;
  }

  .danger {
    color: var(--color-danger);
  }

  .row-status {
    width: fit-content;
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }

  .row-error {
    color: var(--color-danger);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    overflow-wrap: anywhere;
  }

  :global(.preparing-icon) {
    animation: preparation-spin 1s linear infinite;
  }

  @keyframes preparation-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.preparing-icon) {
      animation: none;
    }
  }

  @media (max-width: 520px) {
    .actions button {
      flex: 1 1 100%;
      max-width: 100%;
    }

    .readiness {
      grid-template-columns: 1fr;
    }
  }
</style>
