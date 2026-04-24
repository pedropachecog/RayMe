<script lang="ts">
  import '../app.css';
  import AppShell from '$lib/components/AppShell.svelte';
</script>

<svelte:head>
  <title>RayMe</title>
  <meta
    name="description"
    content="RayMe local chat workspace for character conversations."
  />
</svelte:head>

<AppShell>
  <slot />
</AppShell>
