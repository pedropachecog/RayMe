<script lang="ts">
  import { MessageSquarePlus, MoreHorizontal, SlidersHorizontal, Upload, UserRoundPlus } from 'lucide-svelte';

  const actions = [
    { label: 'Start Chat', icon: MessageSquarePlus, primary: true },
    { label: 'Import Character', icon: Upload, primary: false },
    { label: 'Create Character', icon: UserRoundPlus, primary: false },
    { label: 'Settings', icon: SlidersHorizontal, primary: false }
  ];
</script>

<section class="home">
  <div class="heading">
    <div>
      <p class="eyebrow">Home</p>
      <h1>RayMe</h1>
    </div>

    <div class="actions" aria-label="Primary actions">
      {#each actions as action}
        <button class:primary={action.primary} type="button">
          <svelte:component this={action.icon} size={18} strokeWidth={1.8} />
          <span>{action.label}</span>
        </button>
      {/each}
    </div>
  </div>

  <div class="dashboard-grid">
    <section class="threads-panel" aria-labelledby="recent-threads-title">
      <div class="panel-heading">
        <div>
          <h2 id="recent-threads-title">Recent threads</h2>
          <p>Conversations will appear here after characters are added.</p>
        </div>
        <button aria-label="Thread actions" class="icon-button" type="button">
          <MoreHorizontal size={20} strokeWidth={1.8} />
        </button>
      </div>

      <div class="empty-state">
        <h3>No conversations yet</h3>
        <p>Import a SillyTavern card or create a character to start your first chat.</p>
        <button class="primary empty-action" type="button">
          <MessageSquarePlus size={18} strokeWidth={1.8} />
          <span>Start Chat</span>
        </button>
      </div>
    </section>

    <aside class="status-panel" aria-labelledby="readiness-title">
      <h2 id="readiness-title">Readiness</h2>
      <div class="readiness-list">
        <div>
          <span class="dot"></span>
          <span>Web UI status pending</span>
        </div>
        <div>
          <span class="dot"></span>
          <span>AI backend pending</span>
        </div>
        <div>
          <span class="dot"></span>
          <span>LLM endpoint pending</span>
        </div>
      </div>
    </aside>
  </div>
</section>

<style>
  .home {
    display: grid;
    gap: 32px;
  }

  .heading {
    display: grid;
    gap: 24px;
  }

  .eyebrow {
    margin: 0 0 8px;
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h1,
  h2,
  h3,
  p {
    margin: 0;
  }

  h1 {
    color: var(--color-text);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: var(--line-display);
  }

  h2 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  h3 {
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    gap: 8px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 14px;
    background: rgba(20, 31, 56, 0.78);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    cursor: pointer;
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  .dashboard-grid {
    display: grid;
    gap: 24px;
  }

  .threads-panel,
  .status-panel {
    border-radius: var(--radius-md);
    background: rgba(9, 19, 40, 0.76);
    backdrop-filter: blur(20px);
  }

  .threads-panel {
    min-height: 440px;
    padding: 24px;
  }

  .panel-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }

  .panel-heading p {
    margin-top: 8px;
  }

  .icon-button {
    width: 44px;
    min-width: 44px;
    padding: 0;
    color: #9eaad5;
  }

  .empty-state {
    display: grid;
    min-height: 300px;
    place-items: center;
    align-content: center;
    gap: 12px;
    text-align: center;
  }

  .empty-state p {
    max-width: 360px;
  }

  .empty-action {
    margin-top: 8px;
  }

  .status-panel {
    padding: 24px;
  }

  .readiness-list {
    display: grid;
    gap: 16px;
    margin-top: 24px;
  }

  .readiness-list div {
    display: flex;
    align-items: center;
    min-height: 44px;
    gap: 12px;
    border-radius: var(--radius-md);
    padding: 0 12px;
    background: rgba(20, 31, 56, 0.64);
    color: var(--color-text);
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-secondary);
    box-shadow: 0 0 18px rgba(0, 227, 253, 0.28);
  }

  @media (min-width: 960px) {
    .heading {
      grid-template-columns: 1fr auto;
      align-items: end;
    }

    .dashboard-grid {
      grid-template-columns: minmax(0, 1fr) 320px;
    }
  }
</style>
