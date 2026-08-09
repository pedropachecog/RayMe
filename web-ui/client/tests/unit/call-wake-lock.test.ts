import { describe, expect, it, vi } from 'vitest';

import {
  createCallScreenWakeLock,
  type CallScreenWakeLockEnvironment,
  type CallScreenWakeLockFallback,
  type ScreenWakeLockSentinel
} from '../../src/lib/call/wakeLock';

class FakeSentinel implements ScreenWakeLockSentinel {
  released = false;
  readonly release = vi.fn(async () => {
    this.emitRelease();
  });

  private readonly releaseListeners = new Set<() => void>();

  addEventListener(type: 'release', listener: () => void): void {
    if (type === 'release') {
      this.releaseListeners.add(listener);
    }
  }

  removeEventListener(type: 'release', listener: () => void): void {
    if (type === 'release') {
      this.releaseListeners.delete(listener);
    }
  }

  emitRelease(): void {
    if (this.released) return;
    this.released = true;
    for (const listener of this.releaseListeners) {
      listener();
    }
  }
}

function createEnvironment(initialVisibility: 'visible' | 'hidden' = 'visible') {
  let visibilityState = initialVisibility;
  const visibilityListeners = new Set<() => void>();
  const sentinels: FakeSentinel[] = [];
  const request = vi.fn(async () => {
    const sentinel = new FakeSentinel();
    sentinels.push(sentinel);
    return sentinel;
  });
  const environment: CallScreenWakeLockEnvironment = {
    navigator: { wakeLock: { request } },
    document: {
      get visibilityState() {
        return visibilityState;
      },
      addEventListener(type, listener) {
        if (type === 'visibilitychange') {
          visibilityListeners.add(listener);
        }
      },
      removeEventListener(type, listener) {
        if (type === 'visibilitychange') {
          visibilityListeners.delete(listener);
        }
      }
    }
  };

  return {
    environment,
    request,
    sentinels,
    setVisibility(nextVisibility: 'visible' | 'hidden') {
      visibilityState = nextVisibility;
      for (const listener of visibilityListeners) {
        listener();
      }
    }
  };
}

describe('call screen wake lock lifecycle', () => {
  it('requests one screen wake lock for an active visible call without duplicate requests', async () => {
    const fake = createEnvironment();
    const lifecycle = createCallScreenWakeLock(fake.environment);

    await lifecycle.activate();
    await lifecycle.activate();

    expect(fake.request).toHaveBeenCalledTimes(1);
    expect(fake.request).toHaveBeenCalledWith('screen');
  });

  it('reacquires after the browser releases a hidden call lock and the page becomes visible again', async () => {
    const fake = createEnvironment();
    const lifecycle = createCallScreenWakeLock(fake.environment);

    await lifecycle.activate();
    fake.setVisibility('hidden');
    fake.sentinels[0].emitRelease();
    fake.setVisibility('visible');
    await vi.waitFor(() => expect(fake.request).toHaveBeenCalledTimes(2));

    expect(fake.request).toHaveBeenNthCalledWith(2, 'screen');
  });

  it('retries when a stale request resolves after the call is reactivated', async () => {
    const fake = createEnvironment();
    let resolveFirstRequest: ((sentinel: ScreenWakeLockSentinel) => void) | null = null;
    const firstSentinel = new FakeSentinel();
    const secondSentinel = new FakeSentinel();
    const request = vi.fn(() => {
      if (request.mock.calls.length === 1) {
        return new Promise<ScreenWakeLockSentinel>((resolve) => {
          resolveFirstRequest = resolve;
        });
      }
      return Promise.resolve(secondSentinel);
    });
    fake.environment.navigator = { wakeLock: { request } };
    const lifecycle = createCallScreenWakeLock(fake.environment);

    const firstActivation = lifecycle.activate();
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    await lifecycle.deactivate();
    const secondActivation = lifecycle.activate();
    resolveFirstRequest?.(firstSentinel);
    await firstActivation;
    await secondActivation;

    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(firstSentinel.release).toHaveBeenCalledTimes(1);
    expect(secondSentinel.released).toBe(false);
  });

  it('does not request while hidden and releases when the call ends or the route is disposed', async () => {
    const fake = createEnvironment('hidden');
    const lifecycle = createCallScreenWakeLock(fake.environment);

    await lifecycle.activate();
    expect(fake.request).not.toHaveBeenCalled();

    fake.setVisibility('visible');
    await vi.waitFor(() => expect(fake.request).toHaveBeenCalledTimes(1));
    await lifecycle.deactivate();
    await lifecycle.dispose();

    expect(fake.sentinels[0].release).toHaveBeenCalledTimes(1);
  });

  it('bounds persistent rejections until a new visible lifecycle event requests again', async () => {
    const fake = createEnvironment();
    const fallbacks: Array<CallScreenWakeLockFallback | null> = [];
    const request = vi.fn(() => {
      if (request.mock.calls.length < 4) {
        return Promise.reject(new DOMException('Wake lock denied', 'NotAllowedError'));
      }
      return new Promise<ScreenWakeLockSentinel>(() => undefined);
    });
    fake.environment.navigator = { wakeLock: { request } };
    const lifecycle = createCallScreenWakeLock(fake.environment, (fallback) => {
      fallbacks.push(fallback);
    });

    void lifecycle.activate();
    await vi.waitFor(() => expect(fallbacks).toEqual(['rejected']));
    for (let attempt = 0; attempt < 8; attempt += 1) {
      await Promise.resolve();
    }

    expect(request).toHaveBeenCalledTimes(1);
    fake.setVisibility('hidden');
    fake.setVisibility('visible');
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  });

  it('degrades safely when the browser does not implement Screen Wake Lock', async () => {
    const fallbacks: Array<CallScreenWakeLockFallback | null> = [];
    const lifecycle = createCallScreenWakeLock({
      navigator: {},
      document: createEnvironment().environment.document
    }, (fallback) => {
      fallbacks.push(fallback);
    });

    await expect(lifecycle.activate()).resolves.toBeUndefined();
    await expect(lifecycle.dispose()).resolves.toBeUndefined();
    expect(fallbacks).toEqual(['unsupported']);
  });
});
