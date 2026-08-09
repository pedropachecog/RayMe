export interface ScreenWakeLockSentinel {
  readonly released: boolean;
  release: () => Promise<void>;
  addEventListener: (type: 'release', listener: () => void) => void;
  removeEventListener: (type: 'release', listener: () => void) => void;
}

export interface CallScreenWakeLockEnvironment {
  navigator?: {
    wakeLock?: {
      request: (type: 'screen') => Promise<ScreenWakeLockSentinel>;
    };
  };
  document?: {
    readonly visibilityState: 'visible' | 'hidden' | 'prerender' | 'unloaded';
    addEventListener: (type: 'visibilitychange', listener: () => void) => void;
    removeEventListener: (type: 'visibilitychange', listener: () => void) => void;
  };
}

export interface CallScreenWakeLock {
  activate: () => Promise<void>;
  deactivate: () => Promise<void>;
  dispose: () => Promise<void>;
}

export type CallScreenWakeLockFallback = 'unsupported' | 'rejected';

export function createCallScreenWakeLock(
  environment: CallScreenWakeLockEnvironment = browserEnvironment(),
  onFallbackChange?: (fallback: CallScreenWakeLockFallback | null) => void
): CallScreenWakeLock {
  const document = environment.document;
  const wakeLock = environment.navigator?.wakeLock;
  let active = false;
  let disposed = false;
  let requestGeneration = 0;
  let sentinel: ScreenWakeLockSentinel | null = null;
  let requestInFlight: Promise<void> | null = null;
  let retryAfterInFlight = false;
  let fallback: CallScreenWakeLockFallback | null = null;

  const setFallback = (nextFallback: CallScreenWakeLockFallback | null) => {
    if (fallback === nextFallback) return;
    fallback = nextFallback;
    onFallbackChange?.(fallback);
  };

  const handleVisibilityChange = () => {
    if (document?.visibilityState === 'visible') {
      void requestIfNeeded();
    }
  };

  document?.addEventListener('visibilitychange', handleVisibilityChange);

  async function requestIfNeeded(): Promise<void> {
    if (
      disposed ||
      !active ||
      document?.visibilityState !== 'visible' ||
      (sentinel && !sentinel.released)
    ) {
      return;
    }
    if (!wakeLock) {
      setFallback('unsupported');
      return;
    }
    if (requestInFlight) {
      return requestInFlight;
    }

    const generation = ++requestGeneration;
    let pendingRequest: Promise<void>;
    pendingRequest = wakeLock.request('screen')
      .then(async (nextSentinel) => {
        if (
          disposed ||
          !active ||
          document?.visibilityState !== 'visible' ||
          generation !== requestGeneration
        ) {
          await nextSentinel.release().catch(() => undefined);
          return;
        }

        const handleRelease = () => {
          if (sentinel === nextSentinel) {
            sentinel = null;
            if (active && document?.visibilityState === 'visible') {
              setFallback('rejected');
            }
          }
          nextSentinel.removeEventListener('release', handleRelease);
        };
        sentinel = nextSentinel;
        nextSentinel.addEventListener('release', handleRelease);
        setFallback(null);
      })
      .catch(() => {
        setFallback('rejected');
      })
      .finally(() => {
        const shouldRetryAfterExplicitActivation =
          requestInFlight === pendingRequest && retryAfterInFlight;
        if (requestInFlight === pendingRequest) {
          requestInFlight = null;
        }
        retryAfterInFlight = false;
        if (shouldRetryAfterExplicitActivation) {
          void requestIfNeeded();
        }
      });
    requestInFlight = pendingRequest;
    return pendingRequest;
  }

  async function releaseCurrent(): Promise<void> {
    requestGeneration += 1;
    const current = sentinel;
    sentinel = null;
    if (!current || current.released) {
      return;
    }
    await current.release().catch(() => undefined);
  }

  return {
    async activate() {
      if (disposed) return;
      active = true;
      if (requestInFlight) {
        retryAfterInFlight = true;
        await requestInFlight;
        return;
      }
      await requestIfNeeded();
    },
    async deactivate() {
      active = false;
      await releaseCurrent();
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      document?.removeEventListener('visibilitychange', handleVisibilityChange);
      active = false;
      await releaseCurrent();
    }
  };
}

function browserEnvironment(): CallScreenWakeLockEnvironment {
  return {
    navigator:
      typeof navigator === 'undefined'
        ? undefined
        : (navigator as unknown as CallScreenWakeLockEnvironment['navigator']),
    document:
      typeof document === 'undefined'
        ? undefined
        : (document as unknown as CallScreenWakeLockEnvironment['document'])
  };
}
