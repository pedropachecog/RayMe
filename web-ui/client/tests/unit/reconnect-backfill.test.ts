import { describe, expect, it } from 'vitest';

import { selectReconnectAudioBackfill, type LocalMicPcmChunk } from '../../src/lib/call/reconnectBackfill';

const sampleRate = 16000;

function chunk(startMs: number, endMs: number, sample: number): LocalMicPcmChunk {
  const sampleCount = Math.round((endMs - startMs) * sampleRate / 1000);
  return {
    startMs,
    endMs,
    samples: new Int16Array(sampleCount).fill(sample)
  };
}

function chunksEverySecond(totalMs: number, sampleForStart: (startMs: number) => number) {
  const chunks: LocalMicPcmChunk[] = [];
  for (let startMs = 0; startMs < totalMs; startMs += 1000) {
    chunks.push(chunk(startMs, startMs + 1000, sampleForStart(startMs)));
  }
  return chunks;
}

describe('reconnect backfill selection', () => {
  it('keeps delayed tail selection contiguous with the previous backfill end', () => {
    const chunks = chunksEverySecond(100000, (startMs) => startMs < 70000 ? 1000 : 1);

    const selection = selectReconnectAudioBackfill(chunks, {
      endMs: 99412,
      startMs: 35256,
      maxDurationMs: 30000,
      sampleRate,
      limitToMaxWindow: false
    });

    expect(selection?.startMs).toBe(35000);
    expect(selection?.endMs).toBe(100000);
    expect(selection?.durationMs).toBe(65000);
    expect(selection?.rms).toBeGreaterThan(700);
  });

  it('keeps the initial reconnect selection capped to the latest pre-roll window', () => {
    const chunks = chunksEverySecond(40000, () => 1000);

    const selection = selectReconnectAudioBackfill(chunks, {
      endMs: 35256,
      startMs: 0,
      maxDurationMs: 30000,
      sampleRate
    });

    expect(selection?.startMs).toBe(5000);
    expect(selection?.endMs).toBe(36000);
    expect(selection?.durationMs).toBe(31000);
  });
});
