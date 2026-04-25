<script lang="ts">
  import { browser } from '$app/environment';
  import { page } from '$app/state';
  import type { Snippet } from 'svelte';
  import { FileAudio, Home, Images, Settings } from 'lucide-svelte';

  import StatusChip from './StatusChip.svelte';

  let { children }: { children?: Snippet } = $props();

  const navigation = [
    { label: 'Home', href: '/', icon: Home },
    { label: 'Gallery', href: '/gallery', icon: Images },
    { label: 'Voice Lab', href: '/voice-lab', icon: FileAudio },
    { label: 'Settings', href: '/settings', icon: Settings }
  ] as const;

  const currentPath = $derived(page.url.pathname);
  let secureContext = $state<boolean | null>(null);
  let mediaDevicesAvailable = $state<boolean | null>(null);

  const secureLabel = $derived(
    secureContext === null ? 'Secure check pending' : secureContext ? 'Secure context' : 'Insecure context'
  );
  const secureTone = $derived(secureContext === null ? 'neutral' : secureContext ? 'healthy' : 'danger');
  const mediaLabel = $derived(
    mediaDevicesAvailable === null ? 'Media check pending' : mediaDevicesAvailable ? 'Media devices ready' : 'Media devices unavailable'
  );
  const mediaTone = $derived(
    mediaDevicesAvailable === null ? 'neutral' : mediaDevicesAvailable ? 'healthy' : 'warning'
  );

  $effect(() => {
    if (!browser) {
      return;
    }

    secureContext = window.isSecureContext;
    mediaDevicesAvailable = Boolean(navigator.mediaDevices);
  });

  function isActive(href: string) {
    return href === '/' ? currentPath === '/' : currentPath.startsWith(href);
  }
</script>

<div class="shell">
  <aside class="rail" aria-label="Primary">
    <a class="brand" href="/" aria-label="RayMe Home">
      <span class="brand-mark" aria-hidden="true">R</span>
      <span class="brand-copy">
        <span class="brand-name">RayMe</span>
        <span class="brand-subtitle">Local chat workspace</span>
      </span>
    </a>

    <nav class="rail-nav" aria-label="Top-level">
      {#each navigation as item}
        {@const Icon = item.icon}
        <a class:active={isActive(item.href)} class="nav-item" href={item.href} aria-current={isActive(item.href) ? 'page' : undefined}>
          <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
          <span>{item.label}</span>
        </a>
      {/each}
    </nav>
  </aside>

  <div class="workspace">
    <header class="topbar">
      <a class="mobile-brand" href="/" aria-label="RayMe Home">
        <span class="brand-mark" aria-hidden="true">R</span>
        <span>RayMe</span>
      </a>

      <div class="status-row" aria-label="System status">
        <StatusChip label={secureLabel} tone={secureTone} description="Browser secure context status" />
        <StatusChip label={mediaLabel} tone={mediaTone} description="Browser media device readiness" />
        <StatusChip label="Endpoint checks pending" description="Endpoint health checks pending" />
      </div>
    </header>

    <main id="main-content" tabindex="-1">
      {#if children}
        {@render children()}
      {/if}
    </main>
  </div>

  <nav class="bottom-nav" aria-label="Primary mobile" data-testid="bottom-navigation">
    {#each navigation as item}
      {@const Icon = item.icon}
      <a class:active={isActive(item.href)} class="bottom-item" href={item.href} aria-current={isActive(item.href) ? 'page' : undefined}>
        <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
        <span>{item.label}</span>
      </a>
    {/each}
  </nav>
</div>

<style>
  .shell {
    min-height: 100vh;
    background:
      linear-gradient(180deg, rgba(9, 19, 40, 0.32) 0%, rgba(6, 14, 32, 0) 320px),
      var(--color-surface);
  }

  .rail {
    position: fixed;
    inset: 0 auto 0 0;
    display: none;
    width: 240px;
    padding: var(--space-lg) var(--space-md);
    background: rgba(9, 19, 40, 0.94);
    backdrop-filter: blur(20px);
  }

  .brand,
  .mobile-brand {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    max-width: 100%;
    gap: 12px;
    color: var(--color-text);
    font-weight: 600;
    text-decoration: none;
  }

  .brand-mark {
    display: inline-grid;
    width: 36px;
    height: 36px;
    flex: 0 0 auto;
    place-items: center;
    border-radius: var(--radius-md);
    background: var(--pulse-gradient);
    color: var(--color-surface);
    font-weight: 600;
  }

  .brand-copy {
    display: grid;
    min-width: 0;
    gap: 2px;
  }

  .brand-name {
    color: var(--color-text);
    font-size: var(--font-body);
    line-height: var(--line-label);
  }

  .brand-subtitle {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 400;
    line-height: var(--line-label);
  }

  .rail-nav {
    display: grid;
    gap: var(--space-sm);
    margin-top: var(--space-2xl);
  }

  .nav-item,
  .bottom-item {
    display: flex;
    align-items: center;
    min-height: 44px;
    gap: 12px;
    color: var(--color-text-muted);
    text-decoration: none;
  }

  .nav-item {
    border-radius: var(--radius-md);
    padding: 0 12px;
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .nav-item:hover,
  .bottom-item:hover {
    color: var(--color-text);
    background: rgba(20, 31, 56, 0.72);
  }

  .nav-item.active,
  .bottom-item.active {
    color: var(--color-text);
    background: rgba(182, 160, 255, 0.14);
  }

  .workspace {
    min-height: 100vh;
    padding: var(--space-md) var(--space-md) calc(64px + var(--space-lg));
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-md);
    max-width: 1440px;
    min-height: 56px;
    margin: 0 auto var(--space-lg);
  }

  .status-row {
    display: flex;
    min-width: 0;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-sm);
  }

  main {
    max-width: 1440px;
    margin: 0 auto;
  }

  .bottom-nav {
    position: fixed;
    inset: auto 0 0;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    min-height: 64px;
    padding: 6px var(--space-sm) var(--space-sm);
    background: rgba(9, 19, 40, 0.96);
    backdrop-filter: blur(20px);
  }

  .bottom-item {
    flex-direction: column;
    justify-content: center;
    gap: var(--space-xs);
    border-radius: var(--radius-md);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    overflow: hidden;
    text-align: center;
  }

  .bottom-item span {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 520px) {
    .topbar {
      display: grid;
      grid-template-columns: 1fr;
      align-items: start;
    }

    .status-row {
      justify-content: flex-start;
    }
  }

  @media (min-width: 800px) {
    .rail {
      display: block;
    }

    .workspace {
      margin-left: 240px;
      padding: var(--space-lg) var(--space-xl) var(--space-2xl);
    }

    .mobile-brand,
    .bottom-nav {
      display: none;
    }
  }
</style>
