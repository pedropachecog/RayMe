import { describe, expect, it } from 'vitest';

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

describe('Character Editor prompt guidance', () => {
  it('shows the exact complete-scene example syntax as persistent escaped text', () => {
    expect(promptHelpSource).toContain('Separate example scenes with');
    expect(promptHelpSource).toContain("{'<START>'}");
    expect(promptHelpSource).toContain("{'{{user}}:'}");
    expect(promptHelpSource).toContain("{'{{char}}:'}");
    expect(promptHelpSource.replace(/\s+/g, ' ')).toContain(
      EXAMPLE_HELP.replace('<START>', "{'<START>'}")
        .replace('{{user}}:', "{'{{user}}:'}")
        .replace('{{char}}:', "{'{{char}}:'}")
    );
    expect(promptHelpSource).not.toContain('{@html}');
    expect(promptHelpSource).not.toContain('innerHTML');
    expect(promptHelpSource).not.toContain('marked(');
  });

  it('defines every macro, the one-pass contract, and the phase-local User value', () => {
    expect(promptHelpSource).toContain('<h3>Prompt macros</h3>');
    for (const token of ["{'{{char}}'}", "{'{{user}}'}", "{'{{original}}'}"]) {
      expect(promptHelpSource).toContain(`<code>${token}</code>`);
    }
    expect(promptHelpSource).toContain('Current character name.');
    expect(promptHelpSource).toContain(
      "{characterName || 'The character name field is currently blank.'}"
    );
    expect(promptHelpSource).toContain(
      'Current user name. In this phase, it resolves to <strong>User</strong>.'
    );
    expect(promptHelpSource).toContain(
      'Active global Main or post-history prompt; expanded before the name macros.'
    );
    expect(promptHelpSource).toContain('Macros expand once. Unknown macros remain unchanged.');
    expect(promptHelpSource).toContain(
      'Active global prompt: {modeLabels[activeMode]} mode with {profileLabels[modelProfile]} profile.'
    );
    expect(promptHelpSource).not.toContain('<img');
    expect(promptHelpSource).not.toContain('onerror');
  });

  it('derives blank, replacement, and includes-original guidance without changing card text', () => {
    for (const contract of [
      'if (!value.trim())',
      "state: 'inherits'",
      BLANK_HELP,
      "if (value.includes('{{original}}'))",
      "state: 'includes-original'",
      ORIGINAL_HELP,
      "state: 'overrides'",
      OVERRIDE_HELP,
      '$: sourceGuidance = promptSourceGuidance(fieldValue);',
      'data-source-state={sourceGuidance.state}',
      '<p>{sourceGuidance.text}</p>'
    ]) {
      expect(promptHelpSource).toContain(contract);
    }

    expect(promptHelpSource).not.toContain('fieldValue = fieldValue');
    expect(promptHelpSource).not.toContain('characterName = characterName');
    expect(editorSource).not.toContain('form.system_prompt =');
    expect(editorSource).not.toContain('form.post_history_instructions =');
  });

  it('keeps PHI meaning visible alongside each reactive source state', () => {
    expect(promptHelpSource.replace(/\s+/g, ' ')).toContain(PHI_HELP);
    expect(promptHelpSource).toContain('{#if postHistory}');
    expect(editorSource).toContain('fieldValue={form.system_prompt}');
    expect(editorSource).toContain('fieldValue={form.post_history_instructions}');
    expect(editorSource).toContain('postHistory');
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
    expect(promptHelpSource).toContain('{characterName ||');
    expect(promptHelpSource).toContain('overflow-wrap: anywhere');
    expect(promptHelpSource).toContain('user-select: text');
    expect(promptHelpSource).toContain('min-width: 0');
    expect(promptHelpSource).toContain('max-width: 100%');
    expect(promptHelpSource).toContain('@media (max-width: 400px)');
    expect(promptHelpSource).not.toContain('overflow: hidden');
    expect(promptHelpSource).not.toContain('text-overflow: ellipsis');
  });
});
