<script lang="ts">
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import type { VoiceSummary } from '$lib/api/types';

  export let open = false;
  export let voice: VoiceSummary | null = null;
  export let referents: Array<Record<string, string>> = [];
  export let submitting = false;
  export let onForceConfirm: () => void = () => {};
  export let onCancel: () => void = () => {};

  $: readableReferents = referents
    .map((referent) => referent.name || referent.title || referent.id)
    .filter(Boolean);
  $: targetName = voice?.name ?? 'this voice';
  $: body = readableReferents.length
    ? `${targetName} is still referenced. Characters or chats using it must be reassigned first. Referents: ${readableReferents.join(', ')}.`
    : `${targetName} may be used by characters or chats. Characters or chats using it must be reassigned first.`;
</script>

<ConfirmDialog
  {open}
  title="Delete voice: Delete this voice?"
  {body}
  confirmLabel="Force Delete Voice"
  cancelLabel="Cancel"
  {submitting}
  onConfirm={onForceConfirm}
  {onCancel}
/>
