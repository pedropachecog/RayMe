<script lang="ts">
  import { onMount } from 'svelte';

  import {
    getSettings,
    testAiBackendSettings,
    testLlmSettings,
    testWebSettings,
    updateSettings
  } from '$lib/api/settings';
  import type { AiBackendSettingsStatus, EndpointStatus, SettingsPayload } from '$lib/api/types';
  import { getBrowserReadiness, getBrowserReadinessText } from '$lib/browser/environment';
  import EndpointSettingsPanel from '$lib/components/EndpointSettingsPanel.svelte';
  import StatusChip from '$lib/components/StatusChip.svelte';
  import AudioSettingsPanel from '$lib/components/settings/AudioSettingsPanel.svelte';
  import VadSettingsPanel from '$lib/components/settings/VadSettingsPanel.svelte';

  let loadState: 'loading' | 'ready' | 'error' = 'loading';
  let saveState: 'idle' | 'saving' = 'idle';
  let testingEndpoint: 'web' | 'ai' | 'llm' | null = null;
  let errorMessage = '';
  let successMessage = '';
  let webUrl = '';
  let aiBackendUrl = '';
  let llmBaseUrl = '';
  let llmModel = '';
  let llmApiKey = '';
  let llmApiKeyConfigured = false;
  let saveAiAudio = true;
  let saveMicAudio = false;
  let vadThreshold = 0.5;
  let vadEndSilenceMs = 700;
  let sttModel = 'distil-large-v3';
  let ttsDefaultEngine = 'f5';
  let webStatus: EndpointStatus = 'Not configured';
  let aiBackendStatus: EndpointStatus = 'Not configured';
  let llmStatus: EndpointStatus = 'Not configured';
  let aiBackendOperationalStatus: AiBackendSettingsStatus = {
    endpoint_status: 'Not configured',
    stt_model: 'distil-large-v3',
    vad_ready: false,
    resident_tts_engine: null,
    available_engines: [],
    loading_engine: null,
    vram_used_mb: null,
    vram_headroom_mb: null
  };
  let secureContextLabel = 'Insecure context';
  let mediaDevicesLabel = 'Media devices unavailable';

  $: apiKeyPlaceholder = llmApiKeyConfigured ? 'API key configured' : 'Optional API key';
  $: secureTone = secureContextLabel === 'Secure context' ? 'healthy' : 'danger';
  $: mediaTone = mediaDevicesLabel === 'Media devices available' ? 'healthy' : 'warning';

  onMount(() => {
    refreshBrowserReadiness();
    void loadSettings();
  });

  function refreshBrowserReadiness() {
    const readinessText = getBrowserReadinessText(getBrowserReadiness());
    secureContextLabel = readinessText.secureContext;
    mediaDevicesLabel = readinessText.mediaDevicesAvailable;
  }

  async function loadSettings() {
    loadState = 'loading';
    errorMessage = '';

    try {
      applySettings(await getSettings());
      loadState = 'ready';
    } catch {
      loadState = 'error';
      errorMessage = 'RayMe could not load endpoint settings.';
    }
  }

  function applySettings(settings: SettingsPayload) {
    webUrl = settings.web_url ?? '';
    aiBackendUrl = settings.ai_backend_url ?? '';
    llmBaseUrl = settings.llm_base_url ?? '';
    llmModel = settings.llm_model ?? '';
    llmApiKey = '';
    llmApiKeyConfigured = settings.llm_api_key_configured === true;
    saveAiAudio = settings.save_ai_audio ?? true;
    saveMicAudio = settings.save_mic_audio ?? false;
    vadThreshold = clampNumber(settings.vad_threshold ?? 0.5, 0, 1);
    vadEndSilenceMs = Math.round(clampNumber(settings.vad_end_silence_ms ?? 700, 100, 3000));
    sttModel = settings.stt_model ?? 'distil-large-v3';
    ttsDefaultEngine = settings.tts_default_engine ?? 'f5';
    aiBackendOperationalStatus = normalizeAiBackendStatus(settings.ai_backend_status, aiBackendUrl);
    webStatus = webUrl.trim() ? 'Connected' : 'Not configured';
    aiBackendStatus = aiBackendOperationalStatus.endpoint_status;
    llmStatus = llmBaseUrl.trim() && llmModel.trim() ? llmStatus : 'Not configured';
  }

  async function saveSettings() {
    await persistCurrentSettings({ showSuccess: true });
  }

  async function persistCurrentSettings({ showSuccess }: { showSuccess: boolean }) {
    saveState = 'saving';
    errorMessage = '';
    if (showSuccess) {
      successMessage = '';
    }

    try {
      const nextSettings = await updateSettings({
        web_url: webUrl,
        ai_backend_url: aiBackendUrl,
        llm_base_url: llmBaseUrl,
        llm_model: llmModel,
        save_ai_audio: saveAiAudio,
        save_mic_audio: saveMicAudio,
        vad_threshold: clampNumber(vadThreshold, 0, 1),
        vad_end_silence_ms: Math.round(clampNumber(vadEndSilenceMs, 100, 3000)),
        stt_model: sttModel,
        tts_default_engine: ttsDefaultEngine,
        ...(llmApiKey.trim() ? { llm_api_key: llmApiKey.trim() } : {})
      });
      applySettings(nextSettings);
      if (showSuccess) {
        successMessage = 'Endpoint settings saved.';
      }
      return true;
    } catch {
      errorMessage = 'RayMe could not save endpoint settings.';
      return false;
    } finally {
      saveState = 'idle';
    }
  }

  async function testWebEndpoint() {
    testingEndpoint = 'web';
    errorMessage = '';
    successMessage = '';

    try {
      if (!(await persistCurrentSettings({ showSuccess: false }))) {
        return;
      }
      webStatus = (await testWebSettings()).status;
    } catch {
      webStatus = 'Unreachable';
    } finally {
      testingEndpoint = null;
    }
  }

  async function testAiBackendEndpoint() {
    testingEndpoint = 'ai';
    errorMessage = '';
    successMessage = '';

    try {
      if (!(await persistCurrentSettings({ showSuccess: false }))) {
        return;
      }
      aiBackendStatus = (await testAiBackendSettings()).status;
      aiBackendOperationalStatus = {
        ...aiBackendOperationalStatus,
        endpoint_status: aiBackendStatus
      };
    } catch {
      aiBackendStatus = 'Unreachable';
      aiBackendOperationalStatus = {
        ...aiBackendOperationalStatus,
        endpoint_status: 'Unreachable'
      };
    } finally {
      testingEndpoint = null;
    }
  }

  async function testLlmEndpoint() {
    testingEndpoint = 'llm';
    errorMessage = '';
    successMessage = '';

    try {
      if (!(await persistCurrentSettings({ showSuccess: false }))) {
        return;
      }
      llmStatus = (await testLlmSettings()).status;
    } catch {
      llmStatus = 'Unreachable';
    } finally {
      testingEndpoint = null;
    }
  }

  function clampNumber(value: number, min: number, max: number) {
    if (!Number.isFinite(value)) {
      return min;
    }
    return Math.min(max, Math.max(min, value));
  }

  function normalizeEndpointStatus(value: unknown, hasUrl: boolean): EndpointStatus {
    if (
      value === 'Connected' ||
      value === 'Unreachable' ||
      value === 'Unauthorized' ||
      value === 'Not configured'
    ) {
      return value;
    }
    return hasUrl ? 'Unreachable' : 'Not configured';
  }

  function normalizeAiBackendStatus(
    status: SettingsPayload['ai_backend_status'] | undefined,
    url: string
  ): AiBackendSettingsStatus {
    const endpointStatus = normalizeEndpointStatus(status?.endpoint_status, Boolean(url.trim()));
    return {
      endpoint_status: endpointStatus,
      stt_model: status?.stt_model ?? sttModel,
      vad_ready: status?.vad_ready === true,
      resident_tts_engine: status?.resident_tts_engine ?? null,
      available_engines: status?.available_engines ?? [],
      loading_engine: status?.loading_engine ?? null,
      vram_used_mb: typeof status?.vram_used_mb === 'number' ? status.vram_used_mb : null,
      vram_headroom_mb:
        typeof status?.vram_headroom_mb === 'number' ? status.vram_headroom_mb : null
    };
  }
</script>

<section class="settings" aria-labelledby="settings-title">
  <div class="heading">
    <div>
      <p class="eyebrow">Settings</p>
      <h1 id="settings-title">Endpoint Settings</h1>
    </div>
    <button class="primary" type="button" disabled={saveState === 'saving'} on:click={saveSettings}>
      <span>Save Settings</span>
    </button>
  </div>

  {#if errorMessage}
    <p class="inline-error" role="alert">{errorMessage}</p>
  {/if}
  {#if successMessage}
    <p class="inline-success" role="status">{successMessage}</p>
  {/if}

  {#if loadState === 'loading'}
    <div class="settings-skeleton" aria-label="Loading settings"></div>
  {:else if loadState === 'error'}
    <div class="empty-state" role="status">
      <h2>Settings unavailable</h2>
      <p>{errorMessage}</p>
      <button class="primary" type="button" on:click={loadSettings}>Retry</button>
    </div>
  {:else}
    <div class="settings-grid">
      <div class="endpoint-stack" aria-label="Endpoint configuration">
        <EndpointSettingsPanel
          idPrefix="web-ui"
          title="Web UI status"
          description="Browser-visible RayMe host address."
          status={webStatus}
          urlLabel="Web UI URL"
          bind:urlValue={webUrl}
          urlPlaceholder="https://192.168.1.199:8443"
          onUrlInput={(value) => (webUrl = value)}
          testing={testingEndpoint === 'web'}
          onTest={testWebEndpoint}
        />

        <EndpointSettingsPanel
          idPrefix="ai-backend"
          title="AI backend"
          description="Health probe for the local AI service."
          status={aiBackendStatus}
          urlLabel="AI backend URL"
          bind:urlValue={aiBackendUrl}
          urlPlaceholder="https://192.168.1.199:9443"
          onUrlInput={(value) => (aiBackendUrl = value)}
          aiBackendStatus={aiBackendOperationalStatus}
          testing={testingEndpoint === 'ai'}
          onTest={testAiBackendEndpoint}
        />

        <EndpointSettingsPanel
          idPrefix="llm"
          title="LLM status"
          description="OpenAI-compatible Chat Completions endpoint proxied by RayMe."
          status={llmStatus}
          urlLabel="LLM URL"
          bind:urlValue={llmBaseUrl}
          urlPlaceholder="https://api.openai.com/v1"
          onUrlInput={(value) => (llmBaseUrl = value)}
          apiKeyValue={llmApiKey}
          {apiKeyPlaceholder}
          apiKeyConfigured={llmApiKeyConfigured}
          onApiKeyInput={(value) => (llmApiKey = value)}
          modelValue={llmModel}
          modelPlaceholder="gpt-4o-mini"
          onModelInput={(value) => (llmModel = value)}
          testing={testingEndpoint === 'llm'}
          onTest={testLlmEndpoint}
        />
      </div>

      <aside class="readiness-panel" aria-labelledby="mobile-readiness-title">
        <div>
          <p class="eyebrow">Mobile readiness</p>
          <h2 id="mobile-readiness-title">HTTPS secure-context status</h2>
        </div>
        <StatusChip
          label={secureContextLabel}
          tone={secureTone}
          description="HTTPS secure-context status"
        />
        <div>
          <h2>Media-device availability status</h2>
          <StatusChip
            label={mediaDevicesLabel}
            tone={mediaTone}
            description="media-device availability status"
          />
        </div>
      </aside>

      <aside class="settings-stack" aria-label="Audio and VAD defaults">
        <AudioSettingsPanel
          saveAiAudio={saveAiAudio}
          saveMicAudio={saveMicAudio}
          onSaveAiAudioChange={(value) => (saveAiAudio = value)}
          onSaveMicAudioChange={(value) => (saveMicAudio = value)}
        />

        <VadSettingsPanel
          threshold={vadThreshold}
          endSilenceMs={vadEndSilenceMs}
          onThresholdChange={(value) => (vadThreshold = clampNumber(value, 0, 1))}
          onEndSilenceChange={(value) =>
            (vadEndSilenceMs = Math.round(clampNumber(value, 100, 3000)))}
        />
      </aside>
    </div>
  {/if}
</section>

<style>
  .settings {
    display: grid;
    gap: var(--space-xl);
  }

  .heading {
    display: grid;
    gap: var(--space-lg);
  }

  .eyebrow,
  h1,
  h2,
  p {
    margin: 0;
  }

  .eyebrow {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h1 {
    margin-top: var(--space-sm);
    color: var(--color-text);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: var(--line-display);
  }

  h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(20, 31, 56, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  .inline-error,
  .inline-success {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .inline-error {
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
  }

  .inline-success {
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }

  .settings-grid,
  .endpoint-stack,
  .settings-stack,
  .readiness-panel {
    display: grid;
    gap: var(--space-lg);
  }

  .readiness-panel {
    align-content: start;
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.78);
    padding: var(--space-lg);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  .settings-skeleton,
  .empty-state {
    min-height: 280px;
    border-radius: var(--radius-md);
    background: rgba(20, 31, 56, 0.66);
  }

  .empty-state {
    display: grid;
    place-items: center;
    gap: var(--space-md);
    padding: var(--space-xl);
    text-align: center;
  }

  .empty-state p {
    color: var(--color-text-muted);
  }

  @media (min-width: 1040px) {
    .heading {
      grid-template-columns: 1fr auto;
      align-items: end;
    }

    .settings-grid {
      grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
      align-items: start;
    }

    .settings-stack {
      grid-column: 1 / -1;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
