import { describe, expect, it, vi } from 'vitest';

import type { CallTurnStreamEvent } from '../../src/lib/api/types';
import {
  dispatchCallTurnStreamEvent,
  existingTurnDisposition
} from '../../src/lib/call/turnStream';

describe('call turn stream duplicate contract', () => {
  it.each([
    ['reserved', 'thinking', null],
    ['running', 'rehearsing', null],
    [
      'cancelled',
      'listening',
      'That turn was cancelled. RayMe is listening for you to try again.'
    ],
    ['failed', 'listening', 'That turn did not finish. Please try again.']
  ] as const)('maps %s to an explicit recoverable UI disposition', (state, callState, notice) => {
    expect(existingTurnDisposition(state)).toEqual({ state: callState, notice });
  });

  it('dispatches a completed retry with its canonical assistant message', () => {
    const completed = vi.fn();
    const event: CallTurnStreamEvent = {
      type: 'ai_done',
      turn_id: 'turn-retry-completed',
      existing: true,
      message: {
        id: 'message-existing-assistant',
        thread_id: 'thread-1',
        message_kind: 'ai_speech',
        role: 'assistant',
        sequence: 2,
        content_text: 'The durable answer is restored.',
        created_at: null,
        updated_at: null
      }
    };

    dispatchCallTurnStreamEvent(event, { ai_done: completed });

    expect(completed).toHaveBeenCalledOnce();
    expect(completed).toHaveBeenCalledWith(event);
  });

  it('dispatches every non-completed duplicate state through the typed handler', () => {
    const existing = vi.fn();

    for (const state of ['reserved', 'running', 'cancelled', 'failed'] as const) {
      dispatchCallTurnStreamEvent(
        {
          type: 'turn_existing',
          turn_id: `turn-${state}`,
          state,
          recoverable: state === 'cancelled' || state === 'failed'
        },
        { turn_existing: existing }
      );
    }

    expect(existing).toHaveBeenCalledTimes(4);
  });
});
