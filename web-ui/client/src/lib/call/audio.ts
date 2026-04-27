export const INPUT_PICKER_UNAVAILABLE_COPY =
  'Input selection is not available in this browser. RayMe will use the current microphone.';

export const OUTPUT_PICKER_UNAVAILABLE_COPY =
  'Output selection is not available in this browser. RayMe will use the browser default output.';

interface UnlockableAudioContext {
  state: AudioContextState;
  sampleRate?: number;
  destination: AudioDestinationNode | unknown;
  resume: () => Promise<void>;
  createBuffer: (numberOfChannels: number, length: number, sampleRate: number) => AudioBuffer;
  createBufferSource: () => AudioBufferSourceNode & { buffer?: AudioBuffer };
}

export interface CallAudioUnlockResult {
  state: AudioContextState;
}

export interface RmsSnapshot {
  listeningRms: number;
  speakingRms: number;
}

export interface CallRmsMeter {
  pushMicrophoneSamples: (samples: Float32Array) => void;
  pushAiOutputSamples: (samples: Float32Array) => void;
  read: () => RmsSnapshot;
}

export interface AudioInputDevice {
  deviceId: string;
  label: string;
  kind: 'audioinput';
}

export interface OutputSelectionResult {
  supported: boolean;
  selected: boolean;
  message?: string;
}

type SinkSelectableAudio = HTMLMediaElement & {
  setSinkId?: (deviceId: string) => Promise<void>;
};

export async function unlockCallAudioContext(
  providedAudioContext?: UnlockableAudioContext
): Promise<CallAudioUnlockResult> {
  const AudioContextCtor =
    typeof AudioContext !== 'undefined'
      ? AudioContext
      : (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
  if (!providedAudioContext && !AudioContextCtor) {
    throw new Error('AudioContext is not available in this browser.');
  }
  const audioContext = providedAudioContext ?? new AudioContextCtor!();

  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }

  const silentBuffer = audioContext.createBuffer(1, 1, audioContext.sampleRate ?? 48000);
  const source = audioContext.createBufferSource();
  source.buffer = silentBuffer;
  source.connect(audioContext.destination as AudioNode);
  source.start();

  return { state: audioContext.state };
}

export async function requestCallMicrophone(): Promise<MediaStream> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    throw new DOMException('Microphone capture is not available in this browser.', 'NotAllowedError');
  }

  return navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
  });
}

export function ensureRemoteCallAudioAudible(audio: Pick<HTMLMediaElement, 'muted'>): boolean {
  if (!audio.muted) {
    return false;
  }
  audio.muted = false;
  return true;
}

export function createRmsMeter(): {
  pushSamples: (samples: Float32Array) => void;
  read: () => number;
} {
  let rms = 0;
  return {
    pushSamples(samples: Float32Array) {
      rms = calculateRms(samples);
    },
    read() {
      return rms;
    }
  };
}

export function createCallRmsMeter(): CallRmsMeter {
  const micListeningMeter = createRmsMeter();
  const aiSpeakingMeter = createRmsMeter();

  return {
    pushMicrophoneSamples(samples: Float32Array) {
      micListeningMeter.pushSamples(samples);
    },
    pushAiOutputSamples(samples: Float32Array) {
      aiSpeakingMeter.pushSamples(samples);
    },
    read() {
      return {
        listeningRms: micListeningMeter.read(),
        speakingRms: aiSpeakingMeter.read()
      };
    }
  };
}

export async function listAudioInputDevices(): Promise<AudioInputDevice[]> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) {
    return [];
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((device): device is MediaDeviceInfo => device.kind === 'audioinput')
    .map((device) => ({
      deviceId: device.deviceId,
      label: device.label,
      kind: 'audioinput'
    }));
}

export async function selectAudioOutputIfSupported(
  audio: SinkSelectableAudio,
  deviceId: string
): Promise<OutputSelectionResult> {
  if (typeof audio.setSinkId !== 'function') {
    return {
      supported: false,
      selected: false,
      message: OUTPUT_PICKER_UNAVAILABLE_COPY
    };
  }

  await audio.setSinkId(deviceId);
  return { supported: true, selected: true };
}

export function getInputPickerUnavailableCopy(): string {
  return INPUT_PICKER_UNAVAILABLE_COPY;
}

export function getOutputPickerUnavailableCopy(): string {
  return OUTPUT_PICKER_UNAVAILABLE_COPY;
}

function calculateRms(samples: Float32Array): number {
  if (samples.length === 0) {
    return 0;
  }

  let sumSquares = 0;
  for (const sample of samples) {
    sumSquares += sample * sample;
  }
  return Math.sqrt(sumSquares / samples.length);
}
