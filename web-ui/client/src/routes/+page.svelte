<script lang="ts">
  import { MessageSquarePlus, Upload, UserRoundPlus, SlidersHorizontal, MoreHorizontal } from 'lucide-svelte';

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
      <p class="eyebrow">Local workspace</p>
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
          <span>Web UI pending</span>
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
    color: #9eaad5;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.3;
  }

  h1,
  h2,
  h3,
  p {
    margin: 0;
  }

  h1 {
    color: #dee5ff;
    font-size: 28px;
    font-weight: 600;
    line-height: 1.15;
  }

  h2 {
    color: #dee5ff;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
  }

  h3 {
    color: #dee5ff;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
  }

  p {
    color: #9eaad5;
    font-size: 14px;
    font-weight: 400;
    line-height: 1.5;
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
    border-radius: 8px;
    padding: 0 14px;
    background: rgba(20, 31, 56, 0.78);
    color: #dee5ff;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.3;
    cursor: pointer;
  }

  button:focus-visible {
    outline: 2px solid #b6a0ff;
    outline-offset: 2px;
  }

  button.primary {
    background: #b6a0ff;
    color: #060e20;
  }

  .dashboard-grid {
    display: grid;
    gap: 24px;
  }

  .threads-panel,
  .status-panel {
    border-radius: 8px;
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
    border-radius: 8px;
    padding: 0 12px;
    background: rgba(20, 31, 56, 0.64);
    color: #dee5ff;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #00e3fd;
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
