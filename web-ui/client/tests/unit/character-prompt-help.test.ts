import { mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import PromptMacroHelp, {
  promptSourceGuidance
} from '../../src/lib/components/PromptMacroHelp.svelte';
import promptHelpSource from '../../src/lib/components/PromptMacroHelp.svelte?raw';
import editorSource from '../../src/routes/characters/[id]/+page.svelte?raw';

const EXAMPLE_HELP =
  'Separate example scenes with <START>. Prefix turns with {{user}}: and {{char}}:. RayMe keeps each scene together when context is trimmed.';
const BLANK_HELP = 'Blank: inherits the active global prompt.';
const OVERRIDE_HELP =
  'Overrides the active global prompt. Add {{original}} to include it.';
const ORIGINAL_HELP = 'Includes the active global prompt at {{original}}.';
const PHI_HELP =
  'Runs after the selected conversation history as the late post-history instruction (PHI), sometimes called a jailbreak.';

const mounted: ReturnType<typeof mount>[] = [];

afterEach(async () => {
  await Promise.all(mounted.splice(0).map((component) => unmount(component)));
  document.body.replaceChildren();
});

function renderHelp(props: Record<string, unknown>) {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(PromptMacroHelp, { target, props });
  mounted.push(component);
  return target;
}

describe('Character Editor prompt guidance', () => {
  it('shows the exact complete-scene example syntax as persistent escaped text', () => {
    const target = renderHelp({ variant: 'examples' });

    expect(target.textContent?.trim()).toBe(EXAMPLE_HELP);
    expect(target.querySelector('start')).toBeNull();
    expect(promptHelpSource).not.toContain('{@html}');
    expect(promptHelpSource).not.toContain('innerHTML');
    expect(promptHelpSource).not.toContain('marked(');
  });

  it('defines every macro, the one-pass contract, and the phase-local User value', () => {
    const hostileName = '<img src=x onerror=alert(1)> 🐉'.repeat(12);
    const target = renderHelp({
      variant: 'macros',
      characterName: hostileName,
      activeMode: 'custom',
      modelProfile: 'qwen_llama_server'
    });
    const text = target.textContent ?? '';

    expect(target.querySelector('h3')?.textContent).toBe('Prompt macros');
    expect(Array.from(target.querySelectorAll('code')).map((node) => node.textContent)).toEqual([
      '{{char}}',
      '{{user}}',
      '{{original}}'
    ]);
    expect(text).toContain('Current character name.');
    expect(text).toContain(hostileName);
    expect(text).toContain('Current user name. In this phase, it resolves to User.');
    expect(text).toContain(
      'Active global Main or post-history prompt; expanded before the name macros.'
    );
    expect(text).toContain('Macros expand once. Unknown macros remain unchanged.');
    expect(text).toContain('Active global prompt: Custom mode with Qwen / llama-server profile.');
    expect(target.querySelector('img')).toBeNull();
    expect(target.innerHTML).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });

  it('derives blank, replacement, and includes-original guidance without changing card text', () => {
    const cases = [
      { value: '', expected: BLANK_HELP, state: 'inherits' },
      { value: '  \n\t', expected: BLANK_HELP, state: 'inherits' },
      {
        value: 'Stay fiercely in character. Unknown {{future}} remains.',
        expected: OVERRIDE_HELP,
        state: 'overrides'
      },
      {
        value: 'Before\n{{original}}\nafter {{char}} with {{user}}',
        expected: ORIGINAL_HELP,
        state: 'includes-original'
      }
    ] as const;

    for (const fixture of cases) {
      const before = fixture.value;
      expect(promptSourceGuidance(fixture.value)).toEqual({
        state: fixture.state,
        text: fixture.expected
      });
      expect(fixture.value).toBe(before);
    }
  });

  it('keeps PHI meaning visible alongside each reactive source state', () => {
    for (const [value, expected] of [
      ['', BLANK_HELP],
      ['Replace it.', OVERRIDE_HELP],
      ['Keep {{original}} here.', ORIGINAL_HELP]
    ] as const) {
      const target = renderHelp({ variant: 'source', fieldValue: value, postHistory: true });
      expect(target.textContent).toContain(expected);
      expect(target.textContent).toContain(PHI_HELP);
    }
  });

  it('integrates saved profile context and help in create, review, and edit without changing editor actions', () => {
    for (const contract of [
      "type EditorMode = 'create' | 'review' | 'edit'",
      "requestedMode === 'create'",
      "requestedMode === 'review'",
      "import PromptMacroHelp from '$lib/components/PromptMacroHelp.svelte'",
      "import { getSettings } from '$lib/api/settings'",
      'activePromptMode = settings.prompt_generation.mode',
      'activeModelProfile = settings.prompt_generation.model_profile',
      'variant="examples"',
      'variant="macros"',
      'fieldValue={form.system_prompt}',
      'fieldValue={form.post_history_instructions}',
      'Discard Edits',
      'Save Character',
      '<PortraitDropzone',
      '<VoiceAssignmentSelect'
    ]) {
      expect(editorSource).toContain(contract);
    }

    expect(editorSource).not.toContain('updateSettings');
    expect(editorSource).not.toContain('character_snapshot_mes_example');
    expect(editorSource.match(/await updateCharacter\(characterId, payload\)/g)).toHaveLength(1);
  });

  it('keeps long Unicode and macro help selectable and contained at 320px', () => {
    const target = renderHelp({
      variant: 'macros',
      characterName: '龍🐉'.repeat(512),
      activeMode: 'roleplay',
      modelProfile: 'auto'
    });

    expect(target.textContent).toContain('龍🐉'.repeat(512));
    expect(promptHelpSource).toContain('overflow-wrap: anywhere');
    expect(promptHelpSource).toContain('min-width: 0');
    expect(promptHelpSource).toContain('max-width: 100%');
    expect(promptHelpSource).toContain('@media (max-width: 400px)');
    expect(promptHelpSource).not.toContain('overflow: hidden');
    expect(promptHelpSource).not.toContain('text-overflow: ellipsis');
  });
});
