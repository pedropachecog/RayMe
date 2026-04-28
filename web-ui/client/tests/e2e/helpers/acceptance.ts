import { expect, type ConsoleMessage, type Page, type Request, type Route } from '@playwright/test';

const PLAYWRIGHT_APP_ORIGIN = 'http://127.0.0.1:4173';
const OPENAI_PROVIDER_ORIGIN = 'https://api.openai.com';

type BrowserErrorGuardOptions = {
  allowConsoleErrors?: RegExp[];
};

export function installBrowserErrorGuard(page: Page, options: BrowserErrorGuardOptions = {}) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (message: ConsoleMessage) => {
    if (message.type() !== 'error') {
      return;
    }

    const text = message.text();
    const allowed = (options.allowConsoleErrors ?? []).some((matcher) => {
      matcher.lastIndex = 0;
      return matcher.test(text);
    });

    if (!allowed) {
      consoleErrors.push(`console.error: ${text}`);
    }
  });

  page.on('pageerror', (error: Error) => {
    pageErrors.push(`pageerror: ${error.message}`);
  });

  return () => {
    expect([...consoleErrors, ...pageErrors]).toEqual([]);
  };
}

export async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export async function installEmptyVoiceLibraryRoute(page: Page) {
  await page.route('**/api/voices', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [] });
      return;
    }

    await route.fallback();
  });
}

export async function fulfillSse(route: Route, events: unknown[]) {
  await route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
    body: events
      .map((event) => {
        const payload = typeof event === 'string' ? event : JSON.stringify(event);
        return `data: ${payload}\n\n`;
      })
      .join('')
  });
}

export async function installCallDebugEventRoute(page: Page) {
  await page.route('**/api/calls/*/_debug/event', async (route) => {
    await fulfillJson(route, { status: 'ok' });
  });
}

export async function installMockCallMedia(page: Page) {
  await page.addInitScript(() => {
    type MockPeerWindow = Window & {
      __raymeMockPeerConnections?: MockRTCPeerConnection[];
      __raymeMockDataChannels?: MockRTCDataChannel[];
      __raymeMockRemoteAudioStreams?: MediaStream[];
    };

    const mediaDevices = {
      async getUserMedia() {
        return new MediaStream();
      },
      async enumerateDevices() {
        return [];
      }
    };
    Object.defineProperty(Navigator.prototype, 'mediaDevices', {
      configurable: true,
      get() {
        return mediaDevices;
      }
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: mediaDevices
    });

    let nextPeerId = 1;
    let nextDataChannelId = 1;

    class MockRTCDataChannel {
      readonly id = nextDataChannelId++;
      readonly label: string;
      readonly ownerPeerId: number;
      readyState: RTCDataChannelState = 'open';
      sentMessages: string[] = [];
      closeCount = 0;
      onopen: (() => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;

      constructor(label: string, ownerPeerId: number) {
        this.label = label;
        this.ownerPeerId = ownerPeerId;
        const target = window as MockPeerWindow;
        target.__raymeMockDataChannels = target.__raymeMockDataChannels ?? [];
        target.__raymeMockDataChannels.push(this);
      }

      send(message: string) {
        this.sentMessages.push(message);
      }

      close() {
        if (this.readyState === 'closed') {
          return;
        }

        this.readyState = 'closed';
        this.closeCount += 1;
        this.onclose?.();
      }

      emitMockMessage(data: string) {
        this.onmessage?.(new MessageEvent('message', { data }));
      }
    }

    class MockRTCPeerConnection {
      readonly id = nextPeerId++;
      iceGatheringState = 'complete';
      iceConnectionState = 'new';
      connectionState = 'new';
      signalingState = 'stable';
      localDescription: RTCSessionDescriptionInit | null = null;
      remoteDescription: RTCSessionDescriptionInit | null = null;
      createdOfferCount = 0;
      closed = false;
      dataChannels: MockRTCDataChannel[] = [];
      remoteStream: MediaStream | null = null;
      ondatachannel: ((event: RTCDataChannelEvent) => void) | null = null;
      ontrack: ((event: RTCTrackEvent) => void) | null = null;
      private listeners = new Map<string, Array<(event: Event) => void>>();

      constructor() {
        const target = window as MockPeerWindow;
        target.__raymeMockPeerConnections = target.__raymeMockPeerConnections ?? [];
        target.__raymeMockPeerConnections.push(this);
      }

      createDataChannel(label = 'rayme-events') {
        const channel = new MockRTCDataChannel(label, this.id);
        this.dataChannels.push(channel);
        return channel;
      }

      addTrack() {
        return {};
      }

      async createOffer() {
        this.createdOfferCount += 1;
        return {
          type: 'offer' as RTCSdpType,
          sdp: [
            'v=0',
            `s=RayMe test peer ${this.id}`,
            'm=audio 9 UDP/TLS/RTP/SAVPF 111',
            `a=ice-ufrag:test-${this.id}`,
            `a=x-rayme-mock-peer-id:${this.id}`,
            ''
          ].join('\r\n')
        };
      }

      async setLocalDescription(description: RTCSessionDescriptionInit) {
        this.localDescription = description;
      }

      async setRemoteDescription(description: RTCSessionDescriptionInit) {
        this.remoteDescription = description;
        this.dispatchRemoteTrack();
      }

      addEventListener(eventName: string, handler: (event: Event) => void) {
        const handlers = this.listeners.get(eventName) ?? [];
        handlers.push(handler);
        this.listeners.set(eventName, handlers);
      }

      close() {
        if (this.closed) {
          return;
        }

        this.closed = true;
        for (const channel of this.dataChannels) {
          channel.close();
        }
        this.connectionState = 'closed';
        this.iceConnectionState = 'closed';
        this.dispatchMockEvent('connectionstatechange');
        this.dispatchMockEvent('iceconnectionstatechange');
      }

      setMockConnectionState(connectionState: RTCPeerConnectionState, iceConnectionState = this.iceConnectionState) {
        this.connectionState = connectionState;
        this.iceConnectionState = iceConnectionState;
        this.dispatchMockEvent('connectionstatechange');
      }

      setMockIceConnectionState(iceConnectionState: RTCIceConnectionState) {
        this.iceConnectionState = iceConnectionState;
        this.dispatchMockEvent('iceconnectionstatechange');
      }

      private dispatchRemoteTrack() {
        if (!this.ontrack) {
          return;
        }

        const stream = createMockRemoteAudioStream();
        this.remoteStream = stream;
        const target = window as MockPeerWindow;
        target.__raymeMockRemoteAudioStreams = target.__raymeMockRemoteAudioStreams ?? [];
        target.__raymeMockRemoteAudioStreams.push(stream);
        const track = stream.getAudioTracks()[0] ?? ({ kind: 'audio', id: `mock-track-${this.id}`, readyState: 'live' } as MediaStreamTrack);
        this.ontrack({
          track,
          streams: [stream],
          receiver: null,
          transceiver: null
        } as unknown as RTCTrackEvent);
      }

      private dispatchMockEvent(eventName: string) {
        const event = new Event(eventName);
        for (const handler of this.listeners.get(eventName) ?? []) {
          handler(event);
        }
      }
    }

    function createMockRemoteAudioStream() {
      const AudioContextCtor =
        typeof AudioContext !== 'undefined'
          ? AudioContext
          : (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext })
              .webkitAudioContext;

      if (AudioContextCtor) {
        try {
          const context = new AudioContextCtor();
          const destination = context.createMediaStreamDestination();
          const oscillator = context.createOscillator();
          oscillator.connect(destination);
          oscillator.start();
          return destination.stream;
        } catch {
          return new MediaStream();
        }
      }

      return new MediaStream();
    }

    const originalPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function play() {
      if (this.srcObject instanceof MediaStream) {
        return Promise.resolve();
      }

      return originalPlay.call(this);
    };

    Object.defineProperty(window, 'RTCPeerConnection', {
      configurable: true,
      value: MockRTCPeerConnection
    });
  });
}

export async function installBlockedCallMicrophone(page: Page) {
  await page.addInitScript(() => {
    const mediaDevices = {
      async getUserMedia() {
        throw new DOMException('Permission denied', 'NotAllowedError');
      },
      async enumerateDevices() {
        return [];
      }
    };
    Object.defineProperty(Navigator.prototype, 'mediaDevices', {
      configurable: true,
      get() {
        return mediaDevices;
      }
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: mediaDevices
    });
  });
}

export function expectRayMeApiRequest(request: Request) {
  const rawUrl = request.url();
  const url = new URL(rawUrl);

  if (url.search.includes('sk-')) {
    throw new Error(`Browser request includes a raw API key query string: ${rawUrl}`);
  }

  const currentPageOrigin = getCurrentPageOrigin(request);
  const isRayMeRelativeApi = url.pathname.startsWith('/api/');
  const isPlaywrightAppOrigin = url.origin === PLAYWRIGHT_APP_ORIGIN;
  const isCurrentPageOrigin = currentPageOrigin !== null && url.origin === currentPageOrigin;
  const isAllowedAppRequest = isRayMeRelativeApi || isPlaywrightAppOrigin || isCurrentPageOrigin;

  if (isAllowedAppRequest) {
    return;
  }

  if (isDirectProviderUrl(url)) {
    throw new Error(`Browser made a direct provider request instead of using RayMe /api: ${rawUrl}`);
  }
}

function getCurrentPageOrigin(request: Request) {
  try {
    const pageUrl = request.frame().page().url();
    return pageUrl ? new URL(pageUrl).origin : null;
  } catch {
    return null;
  }
}

function isDirectProviderUrl(url: URL) {
  if (isKnownLocalLlmProvider(url) || url.origin === OPENAI_PROVIDER_ORIGIN) {
    return true;
  }

  const providerHostname = /(openai|anthropic|mistral|groq|openrouter|generativelanguage)/i;
  const providerPath = url.pathname.startsWith('/v1') || url.pathname.includes('/chat/completions');
  return providerHostname.test(url.hostname) || providerPath;
}

function isKnownLocalLlmProvider(url: URL) {
  return url.hostname === '192.168.1.190' && url.port === '8001' && url.pathname.startsWith('/v1');
}
