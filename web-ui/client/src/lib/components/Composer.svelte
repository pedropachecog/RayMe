<script lang="ts">
  import { SendHorizontal } from 'lucide-svelte';

  interface Props {
    disabled?: boolean;
    placeholder?: string;
    value?: string;
    onDraftChange?: (content: string) => void;
    onSend: (content: string) => void | Promise<void>;
  }

  let {
    disabled = false,
    placeholder = 'Type a message',
    value = '',
    onDraftChange,
    onSend
  }: Props = $props();
  let draft = $state('');
  const canSend = $derived(!disabled && draft.trim().length > 0);

  $effect(() => {
    if (value !== draft) {
      draft = value;
    }
  });

  function setDraft(nextDraft: string) {
    draft = nextDraft;
    onDraftChange?.(nextDraft);
  }

  async function submit() {
    const content = draft.trim();
    if (!content || disabled) {
      return;
    }

    setDraft('');
    await onSend(content);
  }

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    void submit();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key !== 'Enter' || event.shiftKey) {
      return;
    }

    event.preventDefault();
    void submit();
  }

  function handleInput(event: Event) {
    setDraft((event.currentTarget as HTMLTextAreaElement).value);
  }
</script>

<form class="composer" aria-label="Chat composer" onsubmit={handleSubmit}>
  <textarea
    value={draft}
    {placeholder}
    disabled={disabled}
    rows="1"
    aria-label="Message"
    oninput={handleInput}
    onkeydown={handleKeydown}
  ></textarea>
  <button type="submit" disabled={!canSend} aria-label="Send message">
    <SendHorizontal size={18} strokeWidth={1.8} aria-hidden="true" />
    <span>Send</span>
  </button>
</form>

<style>
  .composer {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    gap: var(--space-sm);
    min-height: 56px;
    border: 1px solid rgba(182, 160, 255, 0.2);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(25, 37, 64, 0.72);
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.26);
    backdrop-filter: blur(20px);
  }

  textarea {
    width: 100%;
    max-height: 168px;
    min-height: 40px;
    resize: none;
    border: 0;
    outline: 0;
    padding: 10px 12px;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    line-height: var(--line-body);
  }

  textarea::placeholder {
    color: var(--color-text-muted);
  }

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    min-height: 44px;
    gap: var(--space-xs);
    border: 0;
    border-radius: var(--radius-sm);
    padding: 0 14px;
    background: var(--pulse-gradient);
    color: var(--color-surface);
    font-size: var(--font-label);
    font-weight: 600;
  }

  button:disabled {
    cursor: not-allowed;
    background: rgba(64, 72, 93, 0.32);
    color: var(--color-text-muted);
  }

  @media (max-width: 520px) {
    button span {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
  }
</style>
