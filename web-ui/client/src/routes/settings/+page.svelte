<script lang="ts">
  import { onMount } from 'svelte';

  import {
    getSettings,
    testAiBackendSettings,
    testLlmSettings,
    testWebSettings,
    updateSettings
  } from '$lib/api/settings';
  import type { EndpointStatus, SettingsPayload } from '$lib/api/types';
  import { getBrowserReadiness, getBrowserReadinessText } from '$lib/browser/environment';
  import EndpointSettingsPanel from '$lib/components/EndpointSettingsPanel.svelte';
  import StatusChip from '$lib/components/StatusChip.svelte';

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
  let webStatus: EndpointStatus = 'Not configured';
  let aiBackendStatus: EndpointStatus = 'Not configured';
  let llmStatus: EndpointStatus = 'Not configured';
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
    webStatus = webUrl.trim() ? 'Connected' : 'Not configured';
    aiBackendStatus = aiBackendUrl.trim() ? aiBackendStatus : 'Not configured';
    llmStatus = llmBaseUrl.trim() && llmModel.trim() ? llmStatus : 'Not configured';
  }

  async function saveSettings() {
    saveState = 'saving';
    errorMessage = '';
    successMessage = '';

    try {
      const nextSettings = await updateSettings({
        web_url: webUrl,
        ai_backend_url: aiBackendUrl,
        llm_base_url: llmBaseUrl,
        llm_model: llmModel,
        ...(llmApiKey.trim() ? { llm_api_key: llmApiKey.trim() } : {})
      });
      applySettings(nextSettings);
      successMessage = 'Endpoint settings saved.';
    } catch {
      errorMessage = 'RayMe could not save endpoint settings.';
    } finally {
      saveState = 'idle';
    }
  }

  async function testWebEndpoint() {
    testingEndpoint = 'web';
    errorMessage = '';

    try {
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

    try {
      aiBackendStatus = (await testAiBackendSettings()).status;
    } catch {
      aiBackendStatus = 'Unreachable';
    } finally {
      testingEndpoint = null;
    }
  }

  async function testLlmEndpoint() {
    testingEndpoint = 'llm';
    errorMessage = '';

    try {
      llmStatus = (await testLlmSettings()).status;
    } catch {
      llmStatus = 'Unreachable';
    } finally {
      testingEndpoint = null;
    }
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
  }
</style>
