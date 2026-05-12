export interface LocalMicPcmChunk {
  startMs: number;
  endMs: number;
  samples: Int16Array;
}

export interface LocalMicPcmSelection {
  startMs: number;
  endMs: number;
  samples: Int16Array;
  durationMs: number;
  rms: number;
  peak: number;
}

export function selectReconnectAudioBackfill(
  chunks: LocalMicPcmChunk[],
  {
    endMs,
    startMs,
    maxDurationMs,
    sampleRate,
    limitToMaxWindow
  }: {
    endMs: number;
    startMs: number;
    maxDurationMs: number;
    sampleRate: number;
    limitToMaxWindow?: boolean;
  }
): LocalMicPcmSelection | null {
  const shouldLimitToMaxWindow = limitToMaxWindow !== false && startMs <= 0;
  const boundedStartMs =
    shouldLimitToMaxWindow ? Math.max(startMs, endMs - maxDurationMs) : startMs;
  const selectedChunks = chunks.filter(
    (chunk) => chunk.endMs > boundedStartMs && chunk.startMs < endMs
  );
  const sampleCount = selectedChunks.reduce((total, chunk) => total + chunk.samples.length, 0);
  if (sampleCount <= 0) {
    return null;
  }
  const samples = new Int16Array(sampleCount);
  let offset = 0;
  let sumSquares = 0;
  let peak = 0;
  for (const chunk of selectedChunks) {
    samples.set(chunk.samples, offset);
    offset += chunk.samples.length;
    for (const sample of chunk.samples) {
      const abs = Math.abs(sample);
      peak = Math.max(peak, abs);
      sumSquares += sample * sample;
    }
  }
  const durationMs = Math.round(samples.length * 1000 / sampleRate);
  return {
    startMs: selectedChunks[0]?.startMs ?? boundedStartMs,
    endMs: selectedChunks[selectedChunks.length - 1]?.endMs ?? endMs,
    samples,
    durationMs,
    rms: Math.sqrt(sumSquares / samples.length),
    peak
  };
}
