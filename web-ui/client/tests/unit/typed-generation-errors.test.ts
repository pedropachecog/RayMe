import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiFetch, GenerationApiError } from '../../src/lib/api/client';
import { sendChatMessage } from '../../src/lib/api/chat';
import { CallApiError, startCall } from '../../src/lib/api/calls';
import { readChatStream } from '../../src/lib/api/stream';
import {
  decodeGenerationFailure,
  decodeRefusalActivity,
  type GenerationFailure,
  type RefusalActivity
} from '../../src/lib/api/types';

const PRIVATE_CANARIES = {
  message: 'REJECTED_PROSE_CANARY',
  prompt: 'PROMPT_CANARY',
  history: 'HISTORY_CANARY',
  credential: 'sk-private-credential-canary',
  seed: 918273645,
  endpoint: 'https://user:pass@private.example/v1'
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function serialized(value: unknown): string {
  return JSON.stringify(value);
}

function expectNoPrivateCanary(value: unknown): void {
  const text = serialized(value);
  for (const canary of Object.values(PRIVATE_CANARIES)) {
    expect(text).not.toContain(String(canary));
  }
}

function fragmentedResponse(parts: Array<string | Uint8Array>): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        for (const part of parts) {
          controller.enqueue(typeof part === 'string' ? encoder.encode(part) : part);
        }
        controller.close();
      }
    }),
    { headers: { 'Content-Type': 'text/event-stream' } }
  );
}

describe('typed generation failure decoding', () => {
  it.each([
    'llm_refusal_exhausted',
    'prompt_budget_exceeded',
    'provider_evidence_mismatch',
    'invalid_model_profile',
    'invalid_generation_request',
    'llm_empty_output',
    'llm_stream_failed',
    'call_generation_failed'
  ] as const)('keeps allowlisted code %s and drops every private field', (code) => {
    const failure = decodeGenerationFailure({
      detail: {
        code,
        ...PRIVATE_CANARIES,
        traceback: 'Traceback: PRIVATE_PATH_CANARY',
        nested: { rejected_text: PRIVATE_CANARIES.message }
      }
    });

    expect(failure).toEqual({ type: 'generation_failure', code });
    expectNoPrivateCanary(failure);
  });

  it('maps malformed, unknown, and FastAPI validation bodies to one sanitized generic code', () => {
    for (const payload of [
      null,
      PRIVATE_CANARIES.message,
      { code: 'private_internal_code', ...PRIVATE_CANARIES },
      { detail: [{ msg: PRIVATE_CANARIES.message, input: PRIVATE_CANARIES.prompt }] }
    ]) {
      const failure = decodeGenerationFailure(payload);
      expect(failure).toEqual({ type: 'generation_failure', code: 'llm_generation_failed' });
      expectNoPrivateCanary(failure);
    }
  });

  it('accepts only bounded refusal activity metadata and rejects private or invalid rows', () => {
    const activity = decodeRefusalActivity({
      type: 'refusal_activity',
      action: 'send',
      attempt: 2,
      reason_code: 'policy_or_safety',
      prefix_characters: 61,
      prefix_estimated_tokens: 17,
      retry_count: 1,
      release_ms: 312.5,
      decision_ms: 3.5,
      terminal_outcome: 'retry',
      timestamp: '2026-08-31T00:00:02Z',
      ...PRIVATE_CANARIES,
      rejected_text: PRIVATE_CANARIES.message
    });

    expect(activity).toEqual({
      type: 'refusal_activity',
      action: 'send',
      attempt: 2,
      reason_code: 'policy_or_safety',
      prefix_characters: 61,
      prefix_estimated_tokens: 17,
      retry_count: 1,
      release_ms: 312.5,
      decision_ms: 3.5,
      terminal_outcome: 'retry',
      timestamp: '2026-08-31T00:00:02Z'
    });
    expectNoPrivateCanary(activity);
    expect(decodeRefusalActivity({ type: 'refusal_activity', attempt: 4 })).toBeNull();
    expect(decodeRefusalActivity({ type: 'refusal_activity', attempt: 2, action: 'private' })).toBeNull();
  });
});

describe('typed HTTP generation failures', () => {
  it('throws an allowlisted GenerationApiError without retaining the response detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: { code: 'prompt_budget_exceeded', ...PRIVATE_CANARIES }
          }),
          { status: 502, statusText: PRIVATE_CANARIES.message }
        )
      )
    );

    const rejection = apiFetch('/messages/ai-1/regenerate', { method: 'POST' });
    await expect(rejection).rejects.toMatchObject({
      name: 'GenerationApiError',
      status: 502,
      failure: { type: 'generation_failure', code: 'prompt_budget_exceeded' }
    });
    try {
      await rejection;
    } catch (error) {
      expect(error).toBeInstanceOf(GenerationApiError);
      expectNoPrivateCanary(error);
      expect(String(error)).not.toContain(PRIVATE_CANARIES.message);
    }
  });

  it('uses the same sanitized generic error for malformed HTTP and chat-stream bodies', async () => {
    const responses = [
      new Response('<not-json>' + PRIVATE_CANARIES.message, { status: 500 }),
      new Response(JSON.stringify({ detail: PRIVATE_CANARIES }), { status: 500 })
    ];
    vi.stubGlobal('fetch', vi.fn(async () => responses.shift() as Response));

    await expect(apiFetch('/settings')).rejects.toMatchObject({
      failure: { code: 'llm_generation_failed' }
    });
    await expect(sendChatMessage('thread-1', 'Hello', {})).rejects.toMatchObject({
      failure: { code: 'llm_generation_failed' }
    });
  });

  it('keeps same-origin enforcement and propagates AbortError unchanged', async () => {
    await expect(apiFetch('https://private.example/v1')).rejects.toThrow(/RayMe backend routes/);

    const abortError = new DOMException('The operation was aborted.', 'AbortError');
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(abortError)));
    const controller = new AbortController();
    controller.abort();

    await expect(
      sendChatMessage('thread-1', 'Hello', {}, { signal: controller.signal })
    ).rejects.toBe(abortError);
  });

  it('maps call HTTP generation failures into the same union without retaining server prose', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: {
              code: 'llm_refusal_exhausted',
              ...PRIVATE_CANARIES
            }
          }),
          { status: 502 }
        )
      )
    );

    try {
      await startCall({ thread_id: 'thread-1' });
      throw new Error('expected startCall to fail');
    } catch (error) {
      expect(error).toBeInstanceOf(CallApiError);
      expect(error).toMatchObject({
        code: 'llm_refusal_exhausted',
        generationFailure: {
          type: 'generation_failure',
          code: 'llm_refusal_exhausted'
        }
      });
      expectNoPrivateCanary(error);
    }
  });
});

describe('fragmented typed chat SSE', () => {
  it('keeps accepted Unicode byte-equivalent and separates activity/error frames', async () => {
    const accepted = 'Cafe\u0301 — 你好 — مرحبا — 👩🏽‍🚀';
    const activityEvent = JSON.stringify({
      type: 'refusal_activity',
      action: 'send',
      attempt: 2,
      reason_code: 'policy_or_safety',
      prefix_characters: 72,
      prefix_estimated_tokens: 19,
      retry_count: 1,
      release_ms: null,
      decision_ms: 4.25,
      terminal_outcome: 'retry',
      timestamp: '2026-08-31T00:00:02Z',
      ...PRIVATE_CANARIES
    });
    const tokenEvent = JSON.stringify({ type: 'token', text: accepted });
    const errorEvent = JSON.stringify({
      type: 'error',
      code: 'llm_refusal_exhausted',
      ...PRIVATE_CANARIES
    });
    const wire = `data: ${activityEvent}\n\ndata: ${tokenEvent}\n\ndata: ${errorEvent}\n\n`;
    const bytes = new TextEncoder().encode(wire);
    const fragments = Array.from(bytes, (byte) => Uint8Array.of(byte));
    const tokens: string[] = [];
    const activities: RefusalActivity[] = [];
    const failures: GenerationFailure[] = [];

    await readChatStream(fragmentedResponse(fragments), {
      onToken: (text) => tokens.push(text),
      onActivity: (activity) => activities.push(activity),
      onFailure: (failure) => failures.push(failure)
    });

    expect(tokens.join('')).toBe(accepted);
    expect(new TextEncoder().encode(tokens.join(''))).toEqual(new TextEncoder().encode(accepted));
    expect(activities).toHaveLength(1);
    expect(failures).toEqual([
      { type: 'generation_failure', code: 'llm_refusal_exhausted' }
    ]);
    expectNoPrivateCanary({ activities, failures });
  });

  it('turns malformed and unknown error events into one sanitized terminal failure', async () => {
    const failures: GenerationFailure[] = [];
    await readChatStream(
      fragmentedResponse([
        `data: {"type":"error","code":"private_code","message":"${PRIVATE_CANARIES.message}"}\n\n`,
        `data: {not-json-${PRIVATE_CANARIES.prompt}}\n\n`
      ]),
      { onFailure: (failure) => failures.push(failure) }
    );

    expect(failures).toEqual([
      { type: 'generation_failure', code: 'llm_generation_failed' },
      { type: 'generation_failure', code: 'llm_generation_failed' }
    ]);
    expectNoPrivateCanary(failures);
  });
});
