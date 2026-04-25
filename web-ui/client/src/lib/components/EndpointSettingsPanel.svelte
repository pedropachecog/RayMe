<script lang="ts">
  import { Eye, EyeOff, PlugZap } from 'lucide-svelte';

  import type { AiBackendSettingsStatus, EndpointStatus } from '$lib/api/types';

  export let idPrefix: string;
  export let title: string;
  export let description = '';
  export let status: EndpointStatus = 'Not configured';
  export let urlLabel: string | undefined = undefined;
  export let urlValue = '';
  export let urlPlaceholder = '';
  export let urlReadonly = false;
  export let onUrlInput: (value: string) => void = () => {};
  export let apiKeyValue: string | undefined = undefined;
  export let apiKeyPlaceholder = 'Optional API key';
  export let apiKeyConfigured = false;
  export let onApiKeyInput: (value: string) => void = () => {};
  export let modelValue: string | undefined = undefined;
  export let modelPlaceholder = 'Model name';
  export let onModelInput: (value: string) => void = () => {};
  export let aiBackendStatus: AiBackendSettingsStatus | undefined = undefined;
  export let testing = false;
  export let onTest: () => void | Promise<void> = () => {};

  let apiKeyVisible = false;

  $: showApiKey = apiKeyValue !== undefined;
  $: showModel = modelValue !== undefined;
  $: showAiBackendStatus = aiBackendStatus !== undefined;
  $: availableEngineLabels = (aiBackendStatus?.available_engines ?? []).map((engine) => {
    if (typeof engine === 'string') {
      return engine;
    }
    return engine.label ?? engine.id ?? engine.engine_id ?? 'Unknown engine';
  });
  $: vramHeadroom =
    typeof aiBackendStatus?.vram_headroom_mb === 'number'
      ? `${Math.round(aiBackendStatus.vram_headroom_mb)} MB`
      : 'Unknown';
  $: statusTone =
    status === 'Connected'
      ? 'connected'
      : status === 'Unauthorized'
        ? 'unauthorized'
        : status === 'Unreachable'
          ? 'unreachable'
          : 'not-configured';
</script>

<section class="endpoint-panel" aria-labelledby={`${idPrefix}-title`}>
  <div class="panel-heading">
    <div>
      <h2 id={`${idPrefix}-title`}>{title}</h2>
      {#if description}
        <p>{description}</p>
      {/if}
    </div>
    <span class={`status-pill ${statusTone}`} data-testid={`${idPrefix}-status`}>{status}</span>
  </div>

  {#if showAiBackendStatus && aiBackendStatus}
    <dl class="status-grid" aria-label="AI backend residency status">
      <div>
        <dt>STT model</dt>
        <dd>{aiBackendStatus.stt_model ?? 'Unknown'}</dd>
      </div>
      <div>
        <dt>VAD ready</dt>
        <dd>{aiBackendStatus.vad_ready ? 'Ready' : 'Not ready'}</dd>
      </div>
      <div>
        <dt>Resident TTS engine</dt>
        <dd>{aiBackendStatus.resident_tts_engine ?? 'None'}</dd>
      </div>
      <div>
        <dt>Available engines</dt>
        <dd>{availableEngineLabels.length ? availableEngineLabels.join(', ') : 'None'}</dd>
      </div>
      <div>
        <dt>Loading engine</dt>
        <dd>{aiBackendStatus.loading_engine ?? 'None'}</dd>
      </div>
      <div>
        <dt>VRAM headroom</dt>
        <dd>{vramHeadroom}</dd>
      </div>
    </dl>
  {/if}

  <div class="fields">
    {#if urlLabel}
      <label>
        <span>{urlLabel}</span>
        <input
          id={`${idPrefix}-url`}
          type="url"
          value={urlValue}
          placeholder={urlPlaceholder}
          readonly={urlReadonly}
          on:input={(event) => onUrlInput((event.currentTarget as HTMLInputElement).value)}
        />
      </label>
    {/if}

    {#if showApiKey}
      <label>
        <span>API key</span>
        <span class="secret-field">
          <input
            id={`${idPrefix}-api-key`}
            type={apiKeyVisible ? 'text' : 'password'}
            value={apiKeyValue}
            placeholder={apiKeyPlaceholder}
            autocomplete="off"
            on:input={(event) => onApiKeyInput((event.currentTarget as HTMLInputElement).value)}
          />
          <button
            class="icon-button"
            type="button"
            aria-label={apiKeyVisible ? 'Mask API key' : 'Reveal API key'}
            on:click={() => (apiKeyVisible = !apiKeyVisible)}
          >
            {#if apiKeyVisible}
              <EyeOff size={18} strokeWidth={1.8} />
            {:else}
              <Eye size={18} strokeWidth={1.8} />
            {/if}
          </button>
        </span>
      </label>
      {#if apiKeyConfigured && !apiKeyValue}
        <p class="key-configured">Stored API key is configured.</p>
      {/if}
    {/if}

    {#if showModel}
      <label>
        <span>Model</span>
        <input
          id={`${idPrefix}-model`}
          type="text"
          value={modelValue}
          placeholder={modelPlaceholder}
          on:input={(event) => onModelInput((event.currentTarget as HTMLInputElement).value)}
        />
      </label>
    {/if}
  </div>

  <div class="panel-actions">
    <button class="test-button" type="button" disabled={testing} on:click={onTest}>
      <PlugZap size={18} strokeWidth={1.8} />
      <span>Test Connection</span>
    </button>
  </div>
</section>

<style>
  .endpoint-panel {
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
    margin-top: var(--space-xs);
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .status-pill {
    display: inline-flex;
    min-height: 32px;
    flex: 0 0 auto;
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

  .connected {
    color: var(--color-text);
    box-shadow: inset 0 0 0 1px rgba(0, 227, 253, 0.22);
  }

  .unauthorized,
  .unreachable {
    color: var(--color-danger);
  }

  .fields {
    display: grid;
    gap: var(--space-md);
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
    margin: 0;
  }

  .status-grid div {
    min-width: 0;
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.5);
    padding: var(--space-sm);
  }

  dt,
  dd {
    margin: 0;
  }

  dt {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  dd {
    margin-top: var(--space-xs);
    overflow-wrap: anywhere;
    color: var(--color-text);
    font-size: var(--font-label);
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
    font-weight: 400;
    line-height: var(--line-body);
  }

  input::placeholder {
    color: rgba(158, 170, 213, 0.62);
  }

  input[readonly] {
    color: var(--color-text-muted);
  }

  .secret-field {
    position: relative;
    display: block;
  }

  .secret-field input {
    padding-right: calc(var(--space-2xl) + var(--space-sm));
  }

  .icon-button {
    position: absolute;
    inset: 0 0 0 auto;
    width: 44px;
    border: 0;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text-muted);
  }

  .key-configured {
    margin-top: calc(-1 * var(--space-sm));
    color: var(--color-text-muted);
    font-size: var(--font-label);
    line-height: var(--line-label);
  }

  .panel-actions {
    display: flex;
    justify-content: flex-start;
  }

  .test-button {
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
</style>
