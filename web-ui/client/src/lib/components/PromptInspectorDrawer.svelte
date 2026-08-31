<script lang="ts">
  import { X } from 'lucide-svelte';
  import { onDestroy, tick } from 'svelte';

  import { GenerationApiError } from '$lib/api/client';
  import { previewPrompt } from '$lib/api/promptPreview';
  import type {
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptPreviewSection,
    PromptPreviewWireMessage
  } from '$lib/api/types';

  interface PromptInspectorTarget {
    id: string;
    sequence: number;
    content: string;
  }

  export let open = false;
  export let threadId: string;
  export let composerDraft = '';
  export let targets: PromptInspectorTarget[] = [];
  export let returnFocus: HTMLElement | null = null;
  export let onClose: () => void = () => {};

  let dialogElement: HTMLElement;
  let closeButton: HTMLButtonElement;
  let resultHeading: HTMLHeadingElement;
  let action: 'send' = 'send';
  let result: PromptPreviewResponse | null = null;
  let resultSignature = '';
  let loading = false;
  let errorCopy = '';
  let budgetFailure = false;
  let previewController: AbortController | null = null;
  let priorBodyOverflow = '';
  let wasOpen = false;

  $: currentSignature = JSON.stringify({ action, composerDraft, threadId });
  $: stale = Boolean(result && resultSignature !== currentSignature);
  $: previewDisabled = loading || !composerDraft.trim();

  $: {
    if (open && !wasOpen) {
      void handleOpened();
    } else if (!open && wasOpen) {
      releaseOpenState();
    }
    wasOpen = open;
  }

  onDestroy(() => {
    previewController?.abort();
    releaseOpenState();
  });

  async function handleOpened() {
    if (typeof document !== 'undefined') {
      priorBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    await tick();
    closeButton?.focus();
  }

  function releaseOpenState() {
    previewController?.abort();
    previewController = null;
    loading = false;
    if (typeof document !== 'undefined') {
      document.body.style.overflow = priorBodyOverflow;
    }
  }

  async function closeDrawer() {
    previewController?.abort();
    onClose();
    await tick();
    returnFocus?.focus();
  }

  function closeFromBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      void closeDrawer();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      void closeDrawer();
      return;
    }

    if (event.key !== 'Tab' || !dialogElement) {
      return;
    }

    const controls = Array.from(
      dialogElement.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((control) => control.getClientRects().length > 0);
    const first = controls[0];
    const last = controls.at(-1);

    if (!first || !last) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function requestPreview(event: MouseEvent) {
    if (previewDisabled) {
      return;
    }

    const keyboardInitiated = event.detail === 0;
    previewController?.abort();
    const controller = new AbortController();
    previewController = controller;
    loading = true;
    errorCopy = '';
    budgetFailure = false;

    const payload: PromptPreviewRequest = {
      action: 'send',
      thread_id: threadId,
      composer_text: composerDraft
    };

    try {
      const nextResult = await previewPrompt(payload, { signal: controller.signal });
      if (previewController !== controller) {
        return;
      }
      result = nextResult;
      resultSignature = currentSignature;
      if (keyboardInitiated) {
        await tick();
        resultHeading?.focus();
      }
    } catch (error) {
      if (isAbortError(error) || previewController !== controller) {
        return;
      }
      budgetFailure =
        error instanceof GenerationApiError && error.failure.code === 'prompt_budget_exceeded';
      errorCopy = budgetFailure
        ? 'This request does not fit the configured context. Raise the context limit or reduce prompt/history content, then try again.'
        : 'RayMe could not preview this request. Check Prompt & Generation settings, then try again.';
    } finally {
      if (previewController === controller) {
        previewController = null;
        loading = false;
      }
    }
  }

  function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === 'AbortError';
  }

  function sectionForMessage(
    message: PromptPreviewWireMessage,
    preview: PromptPreviewResponse
  ): PromptPreviewSection[] {
    return message.section_ids
      .map((sectionId) => preview.sections.find((section) => section.section_id === sectionId))
      .filter((section): section is PromptPreviewSection => Boolean(section));
  }

  function displaySource(source: string): string {
    return source
      .split(/[_-]+/)
      .filter(Boolean)
      .map((part) => `${part[0]?.toUpperCase() ?? ''}${part.slice(1)}`)
      .join(' ');
  }

  function requestJson(preview: PromptPreviewResponse): string {
    const request = preview.effective_request;
    return JSON.stringify(
      {
        model: request.model,
        messages: request.messages,
        stream: request.stream,
        max_tokens: request.max_tokens,
        temperature: request.temperature,
        top_p: request.top_p,
        presence_penalty: request.presence_penalty,
        frequency_penalty: request.frequency_penalty,
        ...(request.extra_body ? { extra_body: request.extra_body } : {})
      },
      null,
      2
    );
  }
</script>

{#if open}
  <div class="inspector-backdrop" role="presentation" onclick={closeFromBackdrop}>
    <div
      bind:this={dialogElement}
      class="inspector-drawer"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      aria-labelledby="prompt-inspector-title"
      aria-describedby="prompt-inspector-intro prompt-inspector-privacy"
      data-target-count={targets.length}
      onkeydown={handleKeydown}
    >
      <header class="drawer-header">
        <div>
          <p class="eyebrow">Preview only</p>
          <h2 id="prompt-inspector-title">Prompt Inspector</h2>
          <p id="prompt-inspector-intro">
            Preview the exact credential-free request RayMe would build. This does not generate, save, or change anything.
          </p>
          <p id="prompt-inspector-privacy">Credentials and runtime seeds are never included.</p>
        </div>
        <button
          bind:this={closeButton}
          class="icon-button"
          type="button"
          aria-label="Close Prompt Inspector"
          onclick={() => closeDrawer()}
        >
          <X size={20} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </header>

      <div class="drawer-body">
        <section class="controls" aria-labelledby="preview-controls-title">
          <h3 id="preview-controls-title">Preview controls</h3>
          <fieldset>
            <legend>Variant</legend>
            <label class="radio-card">
              <input type="radio" name="prompt-variant" value="text" checked />
              <span>Text</span>
            </label>
          </fieldset>

          <label class="field">
            <span>Action</span>
            <select bind:value={action}>
              <option value="send">Send</option>
            </select>
          </label>

          {#if !composerDraft.trim()}
            <p class="guidance">Enter a composer draft to inspect Send.</p>
          {/if}
        </section>

        <section
          class="result-region"
          aria-busy={loading}
          aria-labelledby="preview-result-title"
        >
          {#if stale}
            <p class="stale-banner" role="status">Preview out of date</p>
          {/if}

          {#if errorCopy}
            <div class:budget-failure={budgetFailure} class="preview-error" role="alert">
              <p>{errorCopy}</p>
              <button type="button" disabled={previewDisabled} onclick={requestPreview}>Try again</button>
            </div>
          {/if}

          {#if !result}
            <div class="empty-state">
              <h3 id="preview-result-title">No request preview yet</h3>
              <p>Choose a variant and action, then preview the request RayMe would send.</p>
            </div>
          {:else}
            <div class="result-stack" class:stale>
              <h3 bind:this={resultHeading} id="preview-result-title" tabindex="-1">Request preview</h3>

              <section class="result-section" aria-labelledby="request-summary-title">
                <h4 id="request-summary-title">Request summary</h4>
                <dl class="metadata-grid">
                  <div><dt>Action</dt><dd>{result.action}</dd></div>
                  <div><dt>Active mode</dt><dd>{result.mode}</dd></div>
                  <div><dt>Resolved model profile</dt><dd>{result.adapter.effective}</dd></div>
                  <div><dt>Configured model ID</dt><dd>{result.configured_model}</dd></div>
                  <div><dt>Prompt contract</dt><dd>{result.prompt_contract_version}</dd></div>
                  <div><dt>Request shape</dt><dd>{result.request_shape_version}</dd></div>
                  <div><dt>Status</dt><dd class="preview-status">Preview only</dd></div>
                </dl>
              </section>

              <section class="result-section" aria-labelledby="budget-title">
                <h4 id="budget-title">Budget</h4>
                <dl class="metadata-grid">
                  <div><dt>Configured context · Estimate</dt><dd>{result.budget.context_limit}</dd></div>
                  <div><dt>Reserved output · Estimate</dt><dd>{result.budget.configured_max_output}</dd></div>
                  <div><dt>Safety margin · Estimate</dt><dd>{result.budget.safety_margin}</dd></div>
                  <div><dt>Input budget · Estimate</dt><dd>{result.budget.input_budget}</dd></div>
                  <div><dt>Input tokens · Estimate</dt><dd>{result.budget.estimated_input_tokens}</dd></div>
                  <div><dt>History kept / dropped</dt><dd>{result.budget.included_history_count} / {result.budget.dropped_history_count}</dd></div>
                  <div><dt>Example groups kept / dropped</dt><dd>{result.budget.included_example_group_count} / {result.budget.dropped_example_group_count}</dd></div>
                </dl>
              </section>

              <section class="result-section ordered-section" aria-labelledby="ordered-messages-title">
                <h4 id="ordered-messages-title">Ordered messages</h4>
                <div class="ordered-spine">
                  {#each result.wire_messages as message, index (message.order)}
                    {@const relatedSections = sectionForMessage(message, result)}
                    <article class="message-card">
                      <div class="message-heading">
                        <span class="message-number">{index + 1}</span>
                        <strong>{message.role}</strong>
                      </div>
                      <dl class="message-metadata">
                        <div><dt>Section</dt><dd>{message.section_ids.join(', ') || 'None'}</dd></div>
                        <div><dt>Source</dt><dd>{relatedSections.map((section) => displaySource(section.source)).join(', ') || 'Adapter merge'}</dd></div>
                        <div><dt>Override</dt><dd>{relatedSections.map((section) => displaySource(section.override_state)).join(', ') || 'Unchanged'}</dd></div>
                      </dl>
                      <pre>{message.content}</pre>
                    </article>
                  {/each}
                </div>
              </section>

              <section class="result-section" aria-labelledby="request-fields-title">
                <h4 id="request-fields-title">Request fields</h4>
                <dl class="metadata-grid">
                  <div><dt>model</dt><dd>{result.effective_request.model}</dd></div>
                  <div><dt>stream</dt><dd>{String(result.effective_request.stream)}</dd></div>
                  <div><dt>max_tokens</dt><dd>{result.effective_request.max_tokens}</dd></div>
                  <div><dt>temperature</dt><dd>{result.effective_request.temperature}</dd></div>
                  <div><dt>top_p</dt><dd>{result.effective_request.top_p}</dd></div>
                  <div><dt>presence_penalty</dt><dd>{result.effective_request.presence_penalty}</dd></div>
                  <div><dt>frequency_penalty</dt><dd>{result.effective_request.frequency_penalty}</dd></div>
                  {#if result.effective_request.extra_body}
                    <div class="wide"><dt>extra_body</dt><dd><pre>{JSON.stringify(result.effective_request.extra_body, null, 2)}</pre></dd></div>
                  {/if}
                  <div><dt>seed</dt><dd>Generated at send time</dd></div>
                </dl>
                {#if result.effective_request.omitted_fields.length}
                  <p class="omissions">Omitted: {result.effective_request.omitted_fields.join(', ')}</p>
                {/if}
              </section>

              <section class="result-section" aria-labelledby="request-json-title">
                <details>
                  <summary id="request-json-title">Credential-free request JSON</summary>
                  <pre class="request-json">{requestJson(result)}</pre>
                </details>
              </section>

              <section class="result-section" aria-labelledby="refusal-policy-title">
                <h4 id="refusal-policy-title">Refusal policy</h4>
                <dl class="metadata-grid">
                  <div><dt>Prefix ceiling</dt><dd>{result.refusal_policy.prefix_max_characters} characters / {result.refusal_policy.prefix_max_estimated_tokens} Estimate tokens</dd></div>
                  <div><dt>Attempts</dt><dd>{result.refusal_policy.max_attempts} maximum ({result.refusal_policy.max_retries} retries)</dd></div>
                  <div><dt>Late retry correction</dt><dd>{result.refusal_policy.retry_correction_present ? 'Present' : 'Absent'}</dd></div>
                  <div><dt>Terminal outcome</dt><dd>{result.refusal_policy.exhausted_error_code}</dd></div>
                </dl>
                <p>Rejected prose is not displayed, spoken, persisted, or copied into retries.</p>
              </section>

              <section class="result-section" aria-labelledby="refusal-activity-title">
                <h4 id="refusal-activity-title">Recent refusal activity</h4>
                {#if result.recent_refusal_activity.length === 0}
                  <p>No refusal retries recorded for this thread.</p>
                {:else}
                  <div class="activity-list">
                    {#each result.recent_refusal_activity as activity, index (`${activity.timestamp}-${index}`)}
                      <article class="activity-row">
                        <strong>{displaySource(activity.action)} · attempt {activity.attempt}</strong>
                        <dl class="message-metadata">
                          <div><dt>Reason</dt><dd>{activity.reason_code}</dd></div>
                          <div><dt>Prefix</dt><dd>{activity.prefix_characters} characters / {activity.prefix_estimated_tokens} Estimate tokens</dd></div>
                          <div><dt>Retries</dt><dd>{activity.retry_count}</dd></div>
                          <div><dt>Release</dt><dd>{activity.release_ms === null ? 'Not released' : `${activity.release_ms} ms`}</dd></div>
                          <div><dt>Outcome</dt><dd>{activity.terminal_outcome}</dd></div>
                        </dl>
                      </article>
                    {/each}
                  </div>
                {/if}
              </section>
            </div>
          {/if}

          {#if loading}
            <div class="loading-state" role="status" aria-live="polite">
              <p>Building request preview…</p>
              <div class="skeleton-row"></div>
              <div class="skeleton-row"></div>
              <div class="skeleton-row"></div>
            </div>
          {/if}
        </section>
      </div>

      <footer class="drawer-footer">
        <button class="secondary" type="button" onclick={() => closeDrawer()}>Close</button>
        <button class="primary" type="button" disabled={previewDisabled} onclick={requestPreview}>
          Preview Request
        </button>
      </footer>
    </div>
  </div>
{/if}

<style>
  .inspector-backdrop {
    position: fixed;
    inset: 0;
    z-index: 120;
    display: flex;
    justify-content: flex-end;
    background: rgba(6, 14, 32, 0.48);
  }

  .inspector-drawer {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    width: min(760px, calc(100vw - 48px));
    height: 100vh;
    overflow: hidden;
    padding: 0 var(--space-lg);
    background: rgba(25, 37, 64, 0.6);
    box-shadow: var(--shadow-float);
    color: var(--color-text);
    backdrop-filter: blur(20px);
  }

  .drawer-header,
  .drawer-footer {
    position: sticky;
    z-index: 2;
    display: flex;
    gap: var(--space-md);
    background: rgba(25, 37, 64, 0.84);
    backdrop-filter: blur(20px);
  }

  .drawer-header {
    top: 0;
    align-items: flex-start;
    justify-content: space-between;
    padding: var(--space-lg) 0 var(--space-md);
  }

  .drawer-footer {
    bottom: 0;
    justify-content: flex-end;
    padding: var(--space-md) 0 var(--space-lg);
  }

  .drawer-body {
    display: grid;
    align-content: start;
    gap: var(--space-lg);
    min-width: 0;
    overflow-y: auto;
    padding: var(--space-md) 0 var(--space-xl);
  }

  .eyebrow,
  h2,
  h3,
  h4,
  p,
  dl,
  dd {
    margin: 0;
  }

  .eyebrow,
  dt,
  legend,
  .field > span {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h2,
  h3,
  h4 {
    color: var(--color-text);
    font-weight: 600;
  }

  h2 { margin-top: var(--space-xs); font-size: var(--font-heading); line-height: var(--line-heading); }
  h3 { font-size: var(--font-heading); line-height: var(--line-heading); }
  h4 { font-size: var(--font-body); line-height: var(--line-body); }

  #prompt-inspector-intro,
  #prompt-inspector-privacy,
  .result-section p,
  .empty-state p,
  .preview-error p,
  .loading-state p {
    margin-top: var(--space-xs);
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  #prompt-inspector-privacy { color: var(--color-active); }

  .icon-button,
  button,
  select,
  summary,
  input {
    min-width: 44px;
    min-height: 44px;
  }

  button,
  select {
    border: 0;
    border-radius: var(--radius-md);
    color: var(--color-text);
    font: inherit;
  }

  button { padding: 0 var(--space-md); font-size: var(--font-label); font-weight: 600; }
  .icon-button { display: inline-grid; flex: 0 0 44px; place-items: center; padding: 0; background: rgba(20, 31, 56, 0.82); }
  .primary { background: rgba(182, 160, 255, 0.84); color: var(--color-surface); }
  .secondary { background: rgba(20, 31, 56, 0.82); }
  button:disabled { cursor: not-allowed; opacity: 0.48; }

  .controls,
  .result-section,
  .empty-state,
  .preview-error,
  .loading-state {
    display: grid;
    gap: var(--space-md);
    min-width: 0;
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(9, 19, 40, 0.86);
  }

  fieldset { display: flex; gap: var(--space-sm); margin: 0; border: 0; padding: 0; }
  legend { margin-bottom: var(--space-sm); }
  .radio-card { display: inline-flex; min-height: 44px; align-items: center; gap: var(--space-sm); border-radius: var(--radius-md); padding: 0 var(--space-md); background: rgba(20, 31, 56, 0.82); }
  .radio-card input { min-width: 20px; min-height: 20px; }
  .field { display: grid; gap: var(--space-sm); }
  select { width: 100%; padding: 0 var(--space-md); background: rgba(20, 31, 56, 0.82); }
  .guidance { color: var(--color-text-muted); font-size: var(--font-body); line-height: var(--line-body); }

  .result-region,
  .result-stack { display: grid; gap: var(--space-lg); min-width: 0; }
  .result-stack.stale { opacity: 0.78; }
  .stale-banner { border-radius: var(--radius-sm); padding: var(--space-sm) var(--space-md); background: rgba(158, 170, 213, 0.12); color: var(--color-text-muted); font-size: var(--font-label); font-weight: 600; }
  .preview-error { background: rgba(255, 113, 108, 0.1); }
  .preview-error p { color: var(--color-danger); }
  .preview-error button { justify-self: start; background: rgba(255, 113, 108, 0.18); }

  .metadata-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-md); }
  .metadata-grid > div,
  .message-metadata > div { display: grid; min-width: 0; gap: var(--space-xs); }
  dd { overflow-wrap: anywhere; color: var(--color-text); font-size: var(--font-body); line-height: var(--line-body); }
  .metadata-grid .wide { grid-column: 1 / -1; }
  .preview-status { color: var(--color-active); font-weight: 600; }

  .ordered-spine { display: grid; gap: var(--space-md); border-left: 4px solid var(--color-accent); padding-left: var(--space-md); }
  .message-card,
  .activity-row { display: grid; gap: var(--space-sm); min-width: 0; border-radius: var(--radius-md); padding: var(--space-md); background: rgba(20, 31, 56, 0.84); }
  .message-heading { display: flex; align-items: center; gap: var(--space-sm); text-transform: capitalize; }
  .message-number { display: inline-grid; width: 28px; height: 28px; place-items: center; border-radius: 50%; background: rgba(182, 160, 255, 0.2); font-size: var(--font-label); font-weight: 600; }
  .message-metadata { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-sm); }

  pre {
    max-width: 100%;
    margin: 0;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  details { min-width: 0; }
  summary { display: flex; cursor: pointer; align-items: center; font-size: var(--font-body); font-weight: 600; }
  .request-json { margin-top: var(--space-md); overflow-x: auto; overflow-wrap: normal; white-space: pre; }
  .omissions { overflow-wrap: anywhere; }
  .activity-list { display: grid; max-height: 480px; gap: var(--space-sm); overflow-y: auto; }
  .loading-state { margin-top: var(--space-md); }
  .skeleton-row { height: 52px; border-radius: var(--radius-sm); background: rgba(20, 31, 56, 0.72); }

  @media (max-width: 639px) {
    .inspector-drawer {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      padding-right: max(var(--space-md), env(safe-area-inset-right));
      padding-left: max(var(--space-md), env(safe-area-inset-left));
    }
    .drawer-header { padding-top: max(var(--space-md), env(safe-area-inset-top)); }
    .drawer-footer { padding-bottom: max(var(--space-md), env(safe-area-inset-bottom)); }
    .controls,
    .result-section,
    .empty-state,
    .preview-error,
    .loading-state { padding: var(--space-md); }
    .metadata-grid,
    .message-metadata { grid-template-columns: 1fr; }
  }

  @media (prefers-reduced-motion: reduce) {
    .inspector-drawer { scroll-behavior: auto; }
  }
</style>
