import { sendCallOffer } from '$lib/api/calls';
import type { CallEvent } from '$lib/api/types';

export const RAYME_EVENTS_CHANNEL = 'rayme-events';

const CALL_EVENT_TYPES = new Set<CallEvent['type']>([
  'user_final',
  'ai_audio_started',
  'muted',
  'interrupted',
  'ended',
  'failed'
]);

export interface CallPeer {
  pc: RTCPeerConnection;
  eventsChannel: RTCDataChannel;
  localStream: MediaStream;
}

export interface CreateCallPeerOptions {
  localStream: MediaStream;
  onRemoteStream?: (stream: MediaStream) => void;
  onDataEvent?: (event: CallEvent) => void;
  rtcConfiguration?: RTCConfiguration;
}

export function createCallPeer(options: CreateCallPeerOptions): CallPeer {
  const pc = new RTCPeerConnection(options.rtcConfiguration);
  const eventsChannel = pc.createDataChannel(RAYME_EVENTS_CHANNEL);
  const remoteStream = new MediaStream();

  attachDataChannel(eventsChannel, options.onDataEvent);
  attachMicrophoneTracks({ pc } satisfies Pick<CallPeer, 'pc'>, options.localStream);

  pc.ondatachannel = (event) => {
    if (event.channel.label === RAYME_EVENTS_CHANNEL) {
      attachDataChannel(event.channel, options.onDataEvent);
    }
  };

  pc.ontrack = (event) => {
    for (const track of event.streams[0]?.getTracks() ?? [event.track]) {
      if (!remoteStream.getTracks().some((existing) => existing.id === track.id)) {
        remoteStream.addTrack(track);
      }
    }
    options.onRemoteStream?.(remoteStream);
  };

  return { pc, eventsChannel, localStream: options.localStream };
}

export function attachMicrophoneTracks(
  peer: Pick<CallPeer, 'pc'>,
  stream: MediaStream
): RTCRtpSender[] {
  return stream.getAudioTracks().map((track) => peer.pc.addTrack(track, stream));
}

export async function negotiateCall(peer: CallPeer, callId: string): Promise<CallPeer> {
  const offer = await peer.pc.createOffer();
  await peer.pc.setLocalDescription(offer);
  const response = await sendCallOffer(callId, offer);

  if (response.answer) {
    await peer.pc.setRemoteDescription(response.answer);
  }

  return peer;
}

export function closeCallPeer(peer: CallPeer): void {
  peer.localStream.getTracks().forEach((track) => track.stop());
  if (peer.eventsChannel.readyState !== 'closed') {
    peer.eventsChannel.close();
  }
  peer.pc.close();
}

function attachDataChannel(
  channel: RTCDataChannel,
  onDataEvent: CreateCallPeerOptions['onDataEvent']
): void {
  channel.onmessage = (message) => {
    const event = parseCallEvent(message.data);
    if (event) {
      onDataEvent?.(event);
    }
  };
}

function parseCallEvent(data: unknown): CallEvent | null {
  if (typeof data !== 'string') {
    return null;
  }

  try {
    const parsed = JSON.parse(data) as Partial<CallEvent>;
    if (parsed && typeof parsed.type === 'string' && CALL_EVENT_TYPES.has(parsed.type)) {
      return parsed as CallEvent;
    }
  } catch {
    return null;
  }

  return null;
}
