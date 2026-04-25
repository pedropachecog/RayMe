import { describe, expect, it, vi } from 'vitest';

import {
  createCallRmsMeter,
  getOutputPickerUnavailableCopy,
  unlockCallAudioContext
} from '../../src/lib/call/audio';

const outputPickerUnavailableCopy =
  'Output selection is not available in this browser. RayMe will use the browser default output.';

describe('call audio helpers', () => {
  it('unlocks the call AudioContext with resume and a one-sample silent buffer', async () => {
    const source = {
      connect: vi.fn(),
      start: vi.fn()
    };
    const audioContext = {
      state: 'suspended',
      destination: {},
      resume: vi.fn(async () => {
        audioContext.state = 'running';
      }),
      createBuffer: vi.fn(() => ({ length: 1 })),
      createBufferSource: vi.fn(() => source)
    };

    const result = await unlockCallAudioContext(audioContext);

    expect(audioContext.resume).toHaveBeenCalledTimes(1);
    expect(audioContext.createBuffer).toHaveBeenCalledWith(1, 1, audioContext.sampleRate ?? 48000);
    expect(source.connect).toHaveBeenCalledWith(audioContext.destination);
    expect(source.start).toHaveBeenCalledTimes(1);
    expect(result.state).toBe('running');
  });

  it('exposes unsupported output picker copy from the UI contract', () => {
    expect(getOutputPickerUnavailableCopy()).toBe(outputPickerUnavailableCopy);
  });

  it('raises listeningRms for non-zero microphone samples and returns near zero for silence', () => {
    const meter = createCallRmsMeter();

    meter.pushMicrophoneSamples(new Float32Array([0, 0.25, -0.25, 0.5, -0.5]));
    expect(meter.read()).toMatchObject({
      speakingRms: 0
    });
    expect(meter.read().listeningRms).toBeGreaterThan(0.1);

    meter.pushMicrophoneSamples(new Float32Array([0, 0, 0, 0]));
    expect(meter.read().listeningRms).toBeLessThan(0.001);
  });

  it('tracks AI output speakingRms separately from microphone listeningRms', () => {
    const meter = createCallRmsMeter();

    meter.pushMicrophoneSamples(new Float32Array([0, 0, 0, 0]));
    meter.pushAiOutputSamples(new Float32Array([0.4, -0.4, 0.2, -0.2]));

    expect(meter.read().listeningRms).toBeLessThan(0.001);
    expect(meter.read().speakingRms).toBeGreaterThan(0.1);

    meter.pushAiOutputSamples(new Float32Array([0, 0, 0, 0]));
    expect(meter.read().speakingRms).toBeLessThan(0.001);
  });
});
