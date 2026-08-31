<script context="module" lang="ts">
  export type PromptSourceState = 'inherits' | 'overrides' | 'includes-original';

  export function promptSourceGuidance(value: string): {
    state: PromptSourceState;
    text: string;
  } {
    if (!value.trim()) {
      return {
        state: 'inherits',
        text: 'Blank: inherits the active global prompt.'
      };
    }

    if (value.includes('{{original}}')) {
      return {
        state: 'includes-original',
        text: 'Includes the active global prompt at {{original}}.'
      };
    }

    return {
      state: 'overrides',
      text: 'Overrides the active global prompt. Add {{original}} to include it.'
    };
  }
</script>

<script lang="ts">
  import type { ModelProfile, PromptMode } from '$lib/api/types';

  export let variant: 'examples' | 'macros' | 'source';
  export let characterName = '';
  export let activeMode: PromptMode = 'roleplay';
  export let modelProfile: ModelProfile = 'auto';
  export let fieldValue = '';
  export let postHistory = false;

  const modeLabels: Record<PromptMode, string> = {
    roleplay: 'Roleplay',
    assistant: 'Assistant',
    custom: 'Custom'
  };

  const profileLabels: Record<ModelProfile, string> = {
    auto: 'Auto (recommended)',
    qwen_llama_server: 'Qwen / llama-server',
    generic_openai_compatible: 'Generic OpenAI-compatible'
  };

  $: sourceGuidance = promptSourceGuidance(fieldValue);
</script>

{#if variant === 'examples'}
  <p class="prompt-help example-help">
    Separate example scenes with {'<START>'}. Prefix turns with {'{{user}}:'} and {'{{char}}:'}.
    RayMe keeps each scene together when context is trimmed.
  </p>
{:else if variant === 'macros'}
  <aside class="prompt-help macro-callout" aria-label="Prompt macros">
    <h3>Prompt macros</h3>

    <dl class="macro-definitions">
      <div>
        <dt><code>{'{{char}}'}</code></dt>
        <dd>
          <span>Current character name.</span>
          <span class="current-value">
            {characterName || 'The character name field is currently blank.'}
          </span>
        </dd>
      </div>
      <div>
        <dt><code>{'{{user}}'}</code></dt>
        <dd>Current user name. In this phase, it resolves to <strong>User</strong>.</dd>
      </div>
      <div>
        <dt><code>{'{{original}}'}</code></dt>
        <dd>Active global Main or post-history prompt; expanded before the name macros.</dd>
      </div>
    </dl>

    <p>Macros expand once. Unknown macros remain unchanged.</p>
    <p class="profile-context">
      Active global prompt: {modeLabels[activeMode]} mode with {profileLabels[modelProfile]} profile.
    </p>
  </aside>
{:else}
  <div class="prompt-help source-help" data-source-state={sourceGuidance.state}>
    <p>{sourceGuidance.text}</p>
    {#if postHistory}
      <p>
        Runs after the selected conversation history as the late post-history instruction (PHI),
        sometimes called a jailbreak.
      </p>
    {/if}
  </div>
{/if}

<style>
  .prompt-help {
    min-width: 0;
    max-width: 100%;
    color: var(--color-text-muted);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
    overflow-wrap: anywhere;
    user-select: text;
  }

  .example-help,
  .source-help,
  .macro-callout p,
  h3,
  dl,
  dd {
    margin: 0;
  }

  .example-help,
  .source-help {
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.62);
    padding: var(--space-sm) var(--space-md);
  }

  .source-help {
    display: grid;
    gap: var(--space-sm);
  }

  .macro-callout {
    display: grid;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.78);
    padding: var(--space-md);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.14);
  }

  h3 {
    color: var(--color-text);
    font-family: var(--font-family-heading);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .macro-definitions {
    display: grid;
    gap: var(--space-sm);
  }

  .macro-definitions > div {
    display: grid;
    grid-template-columns: minmax(112px, auto) minmax(0, 1fr);
    gap: var(--space-md);
    align-items: start;
  }

  dt,
  dd,
  .current-value {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  code {
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  dd {
    display: grid;
    gap: var(--space-xs);
  }

  strong {
    color: var(--color-text);
    font-weight: 600;
  }

  .current-value,
  .profile-context {
    color: var(--color-text);
  }

  @media (max-width: 400px) {
    .macro-definitions > div {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-xs);
    }
  }
</style>
