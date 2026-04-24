import { afterEach, describe, expect, it, vi } from 'vitest';

import { getBrowserReadiness, getBrowserReadinessText } from '../../src/lib/browser/environment';

afterEach(() => {
  vi.unstubAllGlobals();
});

function installBrowserState({
  secureContext,
  mediaDevices,
  protocol,
  href
}: {
  secureContext: boolean;
  mediaDevices: MediaDevices | undefined;
  protocol: string;
  href: string;
}) {
  vi.stubGlobal('window', { isSecureContext: secureContext });
  vi.stubGlobal('navigator', { mediaDevices });
  vi.stubGlobal('location', { protocol, href });
}

describe('getBrowserReadiness', () => {
  it('reports secure context and media-device availability', () => {
    installBrowserState({
      secureContext: true,
      mediaDevices: {} as MediaDevices,
      protocol: 'https:',
      href: 'https://192.168.1.199:8443/'
    });

    expect(getBrowserReadiness()).toEqual({
      secureContext: true,
      mediaDevicesAvailable: true,
      protocol: 'https:',
      href: 'https://192.168.1.199:8443/'
    });
  });

  it('reports insecure context and unavailable media devices', () => {
    installBrowserState({
      secureContext: false,
      mediaDevices: undefined,
      protocol: 'http:',
      href: 'http://192.168.1.199:5173/'
    });

    expect(getBrowserReadiness()).toEqual({
      secureContext: false,
      mediaDevicesAvailable: false,
      protocol: 'http:',
      href: 'http://192.168.1.199:5173/'
    });
  });

  it('returns text states that consumers can distinguish without color', () => {
    installBrowserState({
      secureContext: false,
      mediaDevices: undefined,
      protocol: 'http:',
      href: 'http://192.168.1.199:5173/'
    });

    expect(getBrowserReadinessText(getBrowserReadiness())).toEqual({
      secureContext: 'Insecure context',
      mediaDevicesAvailable: 'Media devices unavailable'
    });

    installBrowserState({
      secureContext: true,
      mediaDevices: {} as MediaDevices,
      protocol: 'https:',
      href: 'https://192.168.1.199:8443/'
    });

    expect(getBrowserReadinessText(getBrowserReadiness())).toEqual({
      secureContext: 'Secure context',
      mediaDevicesAvailable: 'Media devices available'
    });
  });

  it('uses guarded defaults outside a browser', () => {
    vi.stubGlobal('window', undefined);
    vi.stubGlobal('navigator', undefined);
    vi.stubGlobal('location', undefined);

    expect(getBrowserReadiness()).toEqual({
      secureContext: false,
      mediaDevicesAvailable: false,
      protocol: '',
      href: ''
    });
  });
});
