import { describe, expect, it, vi } from 'vitest';

import { createCallStore } from '../../src/lib/call/store.svelte';

const callId = 'call-01';
const threadId = 'thread-01';

function createDeferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('call state machine', () => {
  it('moves through connecting, listening, thinking, speaking, interrupted, ended, and failed states', async () => {
    const store = createCallStore({ callId, threadId });

    expect(store.state).toBe('connecting');

    store.connected();
    expect(store.state).toBe('listening');

    store.userSpeechFinalized({ text: 'Are you there?' });
    expect(store.state).toBe('thinking');

    store.aiSpeechStarted({ text: 'I am here.' });
    expect(store.state).toBe('speaking');

    store.interrupt();
    expect(store.state).toBe('interrupted');

    await store.flushTransientState();
    expect(store.state).toBe('listening');

    store.fail({ publicMessage: 'The call ended because the connection dropped. Your transcript so far was saved.' });
    expect(store.state).toBe('failed');

    store.end();
    expect(store.state).toBe('ended');
  });

  it('cancels AI generation and playback on button interrupt before returning to listening', async () => {
    const generation = createDeferred();
    const abortGeneration = vi.fn();
    const stopPlayback = vi.fn();
    const store = createCallStore({
      callId,
      threadId,
      generation: {
        promise: generation.promise,
        abort: abortGeneration
      },
      playback: {
        stop: stopPlayback
      }
    });

    store.connected();
    store.userSpeechFinalized({ text: 'Say something long.' });
    store.aiSpeechStarted({ text: 'This is the first chunk.' });
    expect(store.state).toBe('speaking');

    store.interrupt({ source: 'button' });

    expect(abortGeneration).toHaveBeenCalledTimes(1);
    expect(stopPlayback).toHaveBeenCalledTimes(1);
    expect(store.state).toBe('interrupted');

    await store.flushTransientState();
    expect(store.state).toBe('listening');
  });

  it('stops active work and moves to ended when the call ends', () => {
    const abortGeneration = vi.fn();
    const stopPlayback = vi.fn();
    const stopMedia = vi.fn();
    const store = createCallStore({
      callId,
      threadId,
      generation: { abort: abortGeneration },
      playback: { stop: stopPlayback },
      media: { stop: stopMedia }
    });

    store.connected();
    store.userSpeechFinalized({ text: 'Please answer.' });
    store.aiSpeechStarted({ text: 'Answering now.' });
    store.end();

    expect(abortGeneration).toHaveBeenCalledTimes(1);
    expect(stopPlayback).toHaveBeenCalledTimes(1);
    expect(stopMedia).toHaveBeenCalledTimes(1);
    expect(store.state).toBe('ended');
  });

  it('toggles serverMuted independently from the local microphone track enabled state', () => {
    const localTrack = { enabled: true };
    const store = createCallStore({
      callId,
      threadId,
      media: {
        localTrack
      }
    });

    expect(store.serverMuted).toBe(false);
    expect(localTrack.enabled).toBe(true);

    store.setServerMuted(true);
    expect(store.serverMuted).toBe(true);
    expect(localTrack.enabled).toBe(true);

    localTrack.enabled = false;
    expect(store.serverMuted).toBe(true);
    expect(localTrack.enabled).toBe(false);

    store.setServerMuted(false);
    expect(store.serverMuted).toBe(false);
    expect(localTrack.enabled).toBe(false);
  });
});
