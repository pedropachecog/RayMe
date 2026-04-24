import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const sourceFiles = [
  'src/routes/voice-lab/+page.svelte',
  'src/lib/components/VoiceLabPage.svelte',
  'src/lib/components/AudioSampleDropzone.svelte',
  'src/lib/components/TranscriptEditor.svelte',
  'src/lib/components/TtsEnginePicker.svelte',
  'src/lib/components/SynthPreviewPanel.svelte',
  'src/lib/components/VoiceLibraryList.svelte',
  'src/lib/components/VoiceLibraryRow.svelte',
  'src/lib/components/VoiceRenameDialog.svelte',
  'src/lib/components/VoiceDeleteDialog.svelte',
  'src/lib/components/VoiceAssignmentSelect.svelte',
  'src/lib/components/VoiceStateBadge.svelte',
  'src/lib/api/voices.ts',
  'src/lib/api/types.ts',
  'src/routes/gallery/+page.svelte',
  'src/routes/characters/[id]/+page.svelte'
];

const voiceLabSources = sourceFiles
  .filter((path) => existsSync(path))
  .map((path) => `\n/* ${path} */\n${readFileSync(path, 'utf8')}`)
  .join('\n');

const requiredVoiceLabCopy = [
  'Voice Lab',
  'Upload Sample',
  'Transcribe Sample',
  'Use default engine',
  'Preview Voice',
  'Save Voice',
  'No voices yet',
  'Rename Voice',
  'Delete Voice',
  'Test Voice',
  'Default voice',
  'No voice',
  'Voice unavailable'
];

const engineLabels = [
  'F5-TTS',
  'XTTS v2',
  'Qwen3-TTS 0.6B-Base',
  'LuxTTS',
  'Chatterbox Turbo',
  'TADA 1B'
];

describe('Voice Lab Phase 2 source contract', () => {
  it('has concrete Voice Lab and Voice Library source files', () => {
    expect(
      sourceFiles.filter((path) => existsSync(path)),
      'Voice Lab implementation sources should exist before this contract can pass'
    ).toEqual(expect.arrayContaining(['src/routes/voice-lab/+page.svelte', 'src/lib/api/voices.ts']));
  });

  it('renders the required Voice Lab, Voice Library, and assignment labels', () => {
    for (const copy of requiredVoiceLabCopy) {
      expect(voiceLabSources).toContain(copy);
    }
  });

  it('exposes the full six-engine roster from metadata-driven picker sources', () => {
    for (const label of engineLabels) {
      expect(voiceLabSources).toContain(label);
    }

    for (const metadataTerm of ['caveat', 'caveats', 'metadata', 'default_engine']) {
      expect(voiceLabSources).toMatch(new RegExp(metadataTerm, 'i'));
    }

    expect(voiceLabSources).not.toContain("['F5-TTS', 'XTTS v2', 'Qwen3-TTS 0.6B-Base']");
  });

  it('allows saving a voice without a successful preview gate', () => {
    expect(voiceLabSources).toContain('Save Voice');
    expect(voiceLabSources).toContain('Preview Voice');
    expect(voiceLabSources).toContain('Use default engine');
    expect(voiceLabSources).not.toMatch(/disabled=\{[^}]*preview[^}]*\}/i);
    expect(voiceLabSources).not.toMatch(/preview\s*(?:Succeeded|Complete|Ready)\s*&&\s*canSave/i);
  });

  it('preserves user input and preview text when preview synthesis fails', () => {
    for (const stateTerm of ['voiceName', 'transcript', 'selectedEngine', 'previewText']) {
      expect(voiceLabSources).toMatch(new RegExp(stateTerm, 'i'));
    }

    expect(voiceLabSources).toMatch(/preview.*(?:error|failed|failure)/i);
  });
});
