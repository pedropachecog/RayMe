<script lang="ts">
  import { Home, Image, Settings, ShieldCheck, Wifi } from 'lucide-svelte';

  const navigation = [
    { label: 'Home', href: '/', icon: Home, active: true },
    { label: 'Gallery', href: '/', icon: Image, active: false },
    { label: 'Settings', href: '/', icon: Settings, active: false }
  ];

  const statusChips = [
    { label: 'Secure pending', icon: ShieldCheck },
    { label: 'Endpoints pending', icon: Wifi }
  ];
</script>

<svelte:head>
  <title>RayMe</title>
  <meta
    name="description"
    content="RayMe local chat workspace for character conversations."
  />
</svelte:head>

<div class="shell">
  <aside class="rail" aria-label="Primary">
    <a class="brand" href="/" aria-label="RayMe Home">
      <span class="brand-mark">R</span>
      <span>RayMe</span>
    </a>

    <nav class="rail-nav">
      {#each navigation as item}
        <a class:active={item.active} class="nav-item" href={item.href}>
          <svelte:component this={item.icon} size={20} strokeWidth={1.8} />
          <span>{item.label}</span>
        </a>
      {/each}
    </nav>
  </aside>

  <div class="workspace">
    <header class="topbar">
      <a class="mobile-brand" href="/" aria-label="RayMe Home">
        <span class="brand-mark">R</span>
        <span>RayMe</span>
      </a>

      <div class="status-row" aria-label="System status">
        {#each statusChips as chip}
          <span class="status-chip">
            <svelte:component this={chip.icon} size={14} strokeWidth={1.8} />
            {chip.label}
          </span>
        {/each}
      </div>
    </header>

    <main>
      <slot />
    </main>
  </div>

  <nav class="bottom-nav" aria-label="Primary mobile">
    {#each navigation as item}
      <a class:active={item.active} class="bottom-item" href={item.href}>
        <svelte:component this={item.icon} size={20} strokeWidth={1.8} />
        <span>{item.label}</span>
      </a>
    {/each}
  </nav>
</div>

<style>
  :global(*) {
    box-sizing: border-box;
  }

  :global(html) {
    background: #060e20;
    color: #dee5ff;
    font-family:
      Inter,
      ui-sans-serif,
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
    font-size: 14px;
    letter-spacing: 0;
  }

  :global(body) {
    min-width: 320px;
    min-height: 100vh;
    margin: 0;
    background:
      radial-gradient(circle at top left, rgba(112, 170, 255, 0.14), transparent 34rem),
      #060e20;
  }

  :global(button),
  :global(a) {
    font: inherit;
  }

  .shell {
    min-height: 100vh;
  }

  .rail {
    position: fixed;
    inset: 0 auto 0 0;
    display: none;
    width: 240px;
    padding: 24px 16px;
    background: rgba(9, 19, 40, 0.88);
    backdrop-filter: blur(20px);
  }

  .brand,
  .mobile-brand {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    gap: 12px;
    color: #dee5ff;
    font-weight: 600;
    text-decoration: none;
  }

  .brand-mark {
    display: inline-grid;
    width: 36px;
    height: 36px;
    place-items: center;
    border-radius: 8px;
    background: linear-gradient(135deg, #b6a0ff 0%, #70aaff 100%);
    color: #060e20;
    font-weight: 600;
  }

  .rail-nav {
    display: grid;
    gap: 8px;
    margin-top: 40px;
  }

  .nav-item,
  .bottom-item {
    display: flex;
    align-items: center;
    min-height: 44px;
    gap: 12px;
    color: #9eaad5;
    text-decoration: none;
  }

  .nav-item {
    padding: 0 12px;
    border-radius: 8px;
  }

  .nav-item.active,
  .bottom-item.active {
    color: #dee5ff;
    background: rgba(182, 160, 255, 0.12);
  }

  .workspace {
    min-height: 100vh;
    padding: 16px 16px 88px;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    max-width: 1440px;
    min-height: 56px;
    margin: 0 auto 24px;
  }

  .status-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
  }

  .status-chip {
    display: inline-flex;
    align-items: center;
    min-height: 32px;
    gap: 6px;
    border-radius: 8px;
    padding: 0 10px;
    background: rgba(25, 37, 64, 0.68);
    color: #9eaad5;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.3;
  }

  main {
    max-width: 1440px;
    margin: 0 auto;
  }

  .bottom-nav {
    position: fixed;
    inset: auto 0 0;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    min-height: 64px;
    padding: 6px 8px 8px;
    background: rgba(9, 19, 40, 0.92);
    backdrop-filter: blur(20px);
  }

  .bottom-item {
    flex-direction: column;
    justify-content: center;
    gap: 4px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.3;
  }

  @media (min-width: 800px) {
    .rail {
      display: block;
    }

    .workspace {
      margin-left: 240px;
      padding: 24px 32px 48px;
    }

    .mobile-brand,
    .bottom-nav {
      display: none;
    }
  }
</style>
