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
    const chunks = [
      chunk(5226, 15226, 1000),
      chunk(15226, 25226, 1000),
      chunk(25226, 35226, 1000),
      chunk(35226, 35256, 1000),
      chunk(35256, 45256, 1000),
      chunk(45256, 55256, 1000),
      chunk(55256, 65256, 1000),
      chunk(65256, 69467, 1000),
      chunk(69467, 79467, 1),
      chunk(79467, 89467, 1),
      chunk(89467, 99412, 1)
    ];

    const selection = selectReconnectAudioBackfill(chunks, {
      endMs: 99412,
      startMs: 35256,
      maxDurationMs: 30000,
      sampleRate
    });

    expect(selection?.startMs).toBe(35256);
    expect(selection?.startMs).not.toBe(69467);
    expect(selection?.endMs).toBe(99412);
    expect(selection?.durationMs).toBeGreaterThan(30000);
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
