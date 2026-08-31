import { afterEach, describe, expect, it, vi } from 'vitest';

import { previewPrompt } from '../../src/lib/api/promptPreview';
import drawerSource from '../../src/lib/components/PromptInspectorDrawer.svelte?raw';
import routeSource from '../../src/routes/chat/[threadId]/+page.svelte?raw';

const sendPreview = {
  action: 'send',
  variant: 'text',
  mode: 'roleplay',
  prompt_contract_version: 'rayme-prompt-contract-v1',
  request_shape_version: 'rayme-generation-request-v1',
  thread_id: 'thread-1',
  configured_model: 'Qwen/Qwen3.5-27B',
  adapter: {
    configured: 'auto',
    effective: 'qwen_llama_server',
    name: 'qwen_llama_server',
    version: 'rayme-generation-request-v1'
  },
  configured_sampler: {
    max_tokens: 512,
    temperature: 0.8,
    top_p: 0.95,
    min_p: 0.05,
    top_k: 40,
    repetition_penalty: 1.05,
    presence_penalty: 0,
    frequency_penalty: 0
  },
  sections: [
    {
      order: 0,
      section_id: 'main',
      logical_role: 'system',
      content: 'Stay <img src=x onerror="globalThis.PRIVACY_CANARY=1"> in character.\nExactly.',
      source: 'global_preset',
      override_state: 'inherited',
      mandatory: true,
      estimated_tokens: 17,
      atomic_group_id: null,
      included: true
    }
  ],
  wire_messages: [
    {
      order: 0,
      role: 'system',
      content: 'Stay <img src=x onerror="globalThis.PRIVACY_CANARY=1"> in character.\nExactly.',
      section_ids: ['main']
    }
  ],
  effective_request: {
    model: 'Qwen/Qwen3.5-27B',
    messages: [
      {
        role: 'system',
        content: 'Stay <img src=x onerror="globalThis.PRIVACY_CANARY=1"> in character.\nExactly.'
      }
    ],
    stream: true,
    max_tokens: 512,
    temperature: 0.8,
    top_p: 0.95,
    presence_penalty: 0,
    frequency_penalty: 0,
    extra_body: {
      top_k: 40,
      min_p: 0.05,
      repeat_penalty: 1.05,
      chat_template_kwargs: { enable_thinking: false }
    },
    seed_policy: 'generated_at_send_time',
    omitted_fields: []
  },
  budget: {
    context_limit: 16384,
    configured_max_output: 512,
    safety_margin: 820,
    input_budget: 15052,
    estimator_version: 'rayme-token-estimate-v1',
    estimated_input_tokens: 17,
    included_history_count: 0,
    dropped_history_count: 0,
    included_example_group_count: 0,
    dropped_example_group_count: 0,
    max_messages: null,
    max_content_length: null,
    content_truncated: false
  },
  warnings: [],
  refusal_policy: {
    max_attempts: 3,
    max_retries: 2,
    prefix_max_characters: 640,
    prefix_max_estimated_tokens: 192,
    safe_sentence_min_visible_characters: 24,
    estimator_version: 'rayme-refusal-estimate-v1',
    retry_correction_present: true,
    correction_role: 'user',
    seed_policy: 'fresh_at_send_time_per_attempt',
    correction_prose_exposed: false,
    rejected_prose_exposed: false,
    exhausted_error_code: 'llm_refusal_exhausted'
  },
  recent_refusal_activity: []
} as const;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Prompt Inspector Task 1 contracts', () => {
  it('posts the exact Send preview through the same-origin wrapper and forwards AbortSignal', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(sendPreview), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await previewPrompt(
      { action: 'send', thread_id: 'thread-1', composer_text: '  exact draft  ' },
      { signal: controller.signal }
    );

    expect(result).toEqual(sendPreview);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/prompt-preview');
    expect(init).toMatchObject({ method: 'POST', signal: controller.signal });
    expect(JSON.parse(String(init?.body))).toEqual({
      action: 'send',
      thread_id: 'thread-1',
      composer_text: '  exact draft  '
    });
  });

  it('defines the real dialog, exact initial/loading/privacy copy, and all seven result sections', () => {
    expect(drawerSource).toContain('role="dialog"');
    expect(drawerSource).toContain('aria-modal="true"');
    expect(drawerSource).toContain('Prompt Inspector');
    expect(drawerSource).toContain(
      'Preview the exact credential-free request RayMe would build. This does not generate, save, or change anything.'
    );
    expect(drawerSource).toContain('Credentials and runtime seeds are never included.');
    expect(drawerSource).toContain('No request preview yet');
    expect(drawerSource).toContain(
      'Choose a variant and action, then preview the request RayMe would send.'
    );
    expect(drawerSource).toContain('Building request preview…');
    expect(drawerSource).toContain('Enter a composer draft to inspect Send.');
    expect(drawerSource).toContain('Preview Request');

    const headings = [
      'Request summary',
      'Budget',
      'Ordered messages',
      'Request fields',
      'Credential-free request JSON',
      'Refusal policy',
      'Recent refusal activity'
    ];
    let priorIndex = -1;
    for (const heading of headings) {
      const nextIndex = drawerSource.indexOf(heading);
      expect(nextIndex, heading).toBeGreaterThan(priorIndex);
      priorIndex = nextIndex;
    }
  });

  it('keeps prompt rendering escaped and owns abort, Escape, focus trap, scroll lock, and focus return', () => {
    expect(drawerSource).not.toContain('{@html');
    expect(drawerSource).not.toContain('innerHTML');
    expect(drawerSource).not.toContain('marked(');
    expect(drawerSource).toContain('white-space: pre-wrap');
    expect(drawerSource).toContain('overflow-wrap: anywhere');
    expect(drawerSource).toContain("event.key === 'Escape'");
    expect(drawerSource).toContain("event.key !== 'Tab'");
    expect(drawerSource).toContain('.abort()');
    expect(drawerSource).toContain('document.body.style.overflow');
    expect(drawerSource).toContain('.focus()');
    expect(drawerSource).toContain('aria-label="Close Prompt Inspector"');
  });

  it('wires a 44px header trigger and the typed failure intent without submitting the composer', () => {
    expect(routeSource).toContain('PromptInspectorDrawer');
    expect(routeSource).toContain('aria-label="Inspect Prompt"');
    expect(routeSource).toContain('aria-haspopup="dialog"');
    expect(routeSource).toContain('aria-expanded={promptInspectorOpen}');
    expect(routeSource).toContain('composerDraft={composerDraft}');
    expect(routeSource).toContain('promptInspectorOpen = true');
    expect(routeSource).toContain('min-height: 44px');
    expect(routeSource).not.toContain('PRIVACY_CANARY');
  });
});

describe('Prompt Inspector Task 2 action and state matrix', () => {
  it('offers all text and call actions with exact eligibility guidance', () => {
    for (const option of ['Send', 'Regenerate', 'Swipe', 'Continue', 'Call offer', 'Call turn']) {
      expect(drawerSource).toContain(`>${option}<`);
    }
    expect(drawerSource).toContain('Target turn');
    expect(drawerSource).toContain('Preview user transcript');
    expect(drawerSource).toContain(
      'No assistant turns are available on the selected branch. Choose another action or add an assistant turn first.'
    );
    expect(drawerSource).toContain('Enter a preview user transcript to inspect Call turn.');
    expect(drawerSource).toContain('target_message_id');
    expect(drawerSource).toContain("action: 'call_offer'");
    expect(drawerSource).toContain("action: 'call_turn'");
  });

  it('keeps call-offer transport ceilings separate from normal Call turn budgeting', () => {
    expect(drawerSource).toContain("result.action === 'call_offer'");
    expect(drawerSource).toContain('AI-backend transport messages');
    expect(drawerSource).toContain('AI-backend transport characters');
    expect(drawerSource).toContain('Configured context · Estimate');
    expect(drawerSource).toContain('Reserved output · Estimate');
  });

  it('implements stale, error, budget, zero-one-many, long-content, and metadata-only states', () => {
    expect(drawerSource).toContain('Preview out of date');
    expect(drawerSource).toContain('RayMe could not preview this request.');
    expect(drawerSource).toContain('This request does not fit the configured context.');
    expect(drawerSource).toContain('No refusal retries recorded for this thread.');
    expect(drawerSource).toContain('activity-list');
    expect(drawerSource).toContain('ordered-spine');
    expect(drawerSource).toContain('max-height: 480px');
    expect(drawerSource).toContain('overflow-x: auto');
    expect(drawerSource).toContain('textSummary(target.content, 80)');
  });

  it('clears local call transcript and keeps mobile header priority with a 44px Reload overflow', () => {
    expect(drawerSource).toContain("callTranscript = ''");
    expect(routeSource).toContain('MoreHorizontal');
    expect(routeSource).toContain('header-overflow');
    expect(routeSource).toContain('Reload thread');
    expect(routeSource).toContain('@media (max-width: 519px)');
    expect(routeSource).toContain('min-width: 44px');
    expect(routeSource).not.toMatch(/barge.?in/i);
  });
});
