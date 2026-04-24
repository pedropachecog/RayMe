export interface BrowserReadiness {
  secureContext: boolean;
  mediaDevicesAvailable: boolean;
  protocol: string;
  href: string;
}

export interface BrowserReadinessText {
  secureContext: string;
  mediaDevicesAvailable: string;
}

export function getBrowserReadiness(): BrowserReadiness {
  const hasWindow = typeof window !== 'undefined';
  const hasNavigator = typeof navigator !== 'undefined';
  const hasLocation = typeof location !== 'undefined';

  return {
    secureContext: hasWindow ? window.isSecureContext === true : false,
    mediaDevicesAvailable: hasNavigator ? Boolean(navigator.mediaDevices) : false,
    protocol: hasLocation ? location.protocol : '',
    href: hasLocation ? location.href : ''
  };
}

export function getBrowserReadinessText(readiness: BrowserReadiness): BrowserReadinessText {
  return {
    secureContext: readiness.secureContext ? 'Secure context' : 'Insecure context',
    mediaDevicesAvailable: readiness.mediaDevicesAvailable
      ? 'Media devices available'
      : 'Media devices unavailable'
  };
}
