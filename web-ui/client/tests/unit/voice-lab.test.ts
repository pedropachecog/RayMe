import { existsSync, readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  deleteVoice,
  getVoice,
  listVoices,
  previewVoice,
  renameVoice,
  saveVoice,
  testPlayVoice,
  transcribeVoiceAsset,
  uploadVoiceAsset
} from '../../src/lib/api/voices';

const sourceFiles = [
  'src/routes/voice-lab/+page.svelte',
  'src/lib/components/voice/AudioSampleDropzone.svelte',
  'src/lib/components/voice/TranscriptEditor.svelte',
  'src/lib/components/voice/TtsEnginePicker.svelte',
  'src/lib/components/voice/SynthPreviewPanel.svelte',
  'src/lib/components/voice/VoiceLibraryList.svelte',
  'src/lib/components/voice/VoiceLibraryRow.svelte',
  'src/lib/components/voice/VoiceRenameDialog.svelte',
  'src/lib/components/voice/VoiceDeleteDialog.svelte',
  'src/lib/api/voices.ts',
  'src/lib/api/types.ts'
];

const voiceLabSources = sourceFiles
  .filter((path) => existsSync(path))
  .map((path) => `\n/* ${path} */\n${readFileSync(path, 'utf8')}`)
  .join('\n');
const routeSource = existsSync('src/routes/voice-lab/+page.svelte')
  ? readFileSync('src/routes/voice-lab/+page.svelte', 'utf8')
  : '';

const requiredVoiceLabCopy = [
  'Voice Lab',
  '1 Upload',
  '2 Transcript',
  '3 Engine',
  '4 Preview',
  '5 Save',
  'Upload Sample',
  'Transcribe Sample',
  'Use default engine',
  'Speech speed',
  'Uploaded sample',
  'Generated test',
  'Preview Voice',
  'Save Voice',
  'No voices yet',
  'Upload a 6-15 second WAV, MP3, or FLAC sample to create the first voice.',
  'Test Voice',
  'Rename Voice',
  'Delete Voice',
  'Type a test phrase',
  'Delete voice: Delete this voice?',
  'Force Delete Voice',
  'Voice unavailable'
];

const engineLabels = [
  'F5-TTS',
  'XTTS v2',
  'Qwen3-TTS 0.6B-Base',
  'LuxTTS',
  'Chatterbox Turbo',
  'TADA 1B',
  'VoxCPM2'
];

const voxcpm2Copy = [
  'VoxCPM2',
  'Candidate',
  '48 kHz',
  'RTX 3060 gate pending',
  'Reference only',
  'Transcript guided',
  'Transcript-guided mode may improve VoxCPM2 results',
  'Style prompt',
  'CFG value',
  'Inference timesteps'
];

afterEach(() => {
  vi.restoreAllMocks();
});

function mockJsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init
  });
}

function installFetch(payload: unknown = {}) {
  const fetchMock = vi.fn(async () => mockJsonResponse(payload));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof installFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url: url as string, init: init as RequestInit };
}

describe('Voice Lab API wrappers', () => {
  it('calls Voice Lab asset, transcript, preview, save, library, delete, and test-play routes', async () => {
    const fetchMock = installFetch({ items: [] });
    const file = new File(['RIFF'], 'sample.wav', { type: 'audio/wav' });

    await uploadVoiceAsset(file);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/assets',
      init: { method: 'POST' }
    });
    expect(lastRequest(fetchMock).init.body).toBeInstanceOf(FormData);

    await transcribeVoiceAsset('asset 1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/assets/asset%201/transcribe',
      init: { method: 'POST' }
    });

    await previewVoice({
      asset_id: 'asset 1',
      name: 'Aster',
      default_engine: 'f5',
      reference_transcript: 'Reference text',
      preview_text: 'Preview this voice.',
      use_default_engine: false,
      engine: 'xtts_v2',
      speech_speed: 0.75
    });
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/preview',
      init: { method: 'POST' }
    });
    expect(JSON.parse(lastRequest(fetchMock).init.body as string)).toMatchObject({
      speech_speed: 0.75
    });

    await saveVoice({
      asset_id: 'asset 1',
      name: 'Aster Voice',
      default_engine: 'f5',
      reference_transcript: 'Reference text',
      metadata: { source: 'voice-lab' }
    });
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices',
      init: { method: 'POST' }
    });

    await listVoices();
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices',
      init: { method: 'GET' }
    });

    await getVoice('voice 1');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/voice%201',
      init: { method: 'GET' }
    });

    await renameVoice('voice 1', 'Renamed Voice');
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/voice%201',
      init: { method: 'PATCH' }
    });
    expect(JSON.parse(lastRequest(fetchMock).init.body as string)).toEqual({
      name: 'Renamed Voice'
    });

    await deleteVoice('voice 1', false);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/voice%201',
      init: { method: 'DELETE' }
    });

    await deleteVoice('voice 1', true);
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/voice%201?force=true',
      init: { method: 'DELETE' }
    });

    await testPlayVoice('voice 1', {
      text: 'Test this voice.',
      use_default_engine: true,
      speech_speed: 0.75
    });
    expect(lastRequest(fetchMock)).toMatchObject({
      url: '/api/voices/voice%201/test-play',
      init: { method: 'POST' }
    });
    expect(JSON.parse(lastRequest(fetchMock).init.body as string)).toMatchObject({
      speech_speed: 0.75
    });
  });

  it('keeps voice wrapper routes behind RayMe-owned /api URLs', async () => {
    await expect(getVoice('https://provider.example/voice')).rejects.toThrow(/RayMe backend routes/);
  });

  it('returns readable referents from blocked delete responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        mockJsonResponse(
          {
            detail: {
              message: 'Voice is referenced',
              referents: [{ kind: 'character', id: 'character-1', name: 'Readable referent' }]
            }
          },
          { status: 409, statusText: 'Conflict' }
        )
      )
    );

    await expect(deleteVoice('voice 1', false)).resolves.toMatchObject({
      voice_id: 'voice 1',
      deleted: false,
      referents: [{ kind: 'character', id: 'character-1', name: 'Readable referent' }]
    });
  });
});

describe('Voice Lab Phase 2 source contract', () => {
  it('has concrete Voice Lab and Voice Library source files', () => {
    expect(
      sourceFiles.filter((path) => existsSync(path)),
      'Voice Lab implementation sources should exist before this contract can pass'
    ).toEqual(
      expect.arrayContaining([
        'src/routes/voice-lab/+page.svelte',
        'src/lib/components/voice/AudioSampleDropzone.svelte',
        'src/lib/components/voice/TranscriptEditor.svelte',
        'src/lib/components/voice/TtsEnginePicker.svelte',
        'src/lib/components/voice/SynthPreviewPanel.svelte',
        'src/lib/components/voice/VoiceLibraryList.svelte',
        'src/lib/components/voice/VoiceLibraryRow.svelte',
        'src/lib/components/voice/VoiceRenameDialog.svelte',
        'src/lib/components/voice/VoiceDeleteDialog.svelte',
        'src/lib/api/voices.ts'
      ])
    );
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

  it('renders VoxCPM2 controls only for VoxCPM2', () => {
    for (const copy of voxcpm2Copy) {
      expect(voiceLabSources).toContain(copy);
    }

    expect(routeSource).toContain("id: 'voxcpm2'");
    expect(routeSource).toMatch(/selectedEngine\s*={3}\s*['"]voxcpm2['"]/);
    expect(routeSource).toMatch(/maxlength={?300}?|maxLength={?300}?|maxlength="300"/);
    expect(routeSource).toMatch(/cfg_value[\s\S]*(?:min="?1(?:\.0)?"?)[\s\S]*(?:max="?3(?:\.0)?"?)/);
    expect(routeSource).toMatch(
      /inference_timesteps[\s\S]*(?:min="?4"?)[\s\S]*(?:max="?30"?)/,
    );
    expect(routeSource).not.toMatch(/Reference only[\s\S]*XTTS v2|Transcript guided[\s\S]*F5-TTS/);
  });

  it('saves VoxCPM2 engine_settings while preserving non-VoxCPM2 UX', async () => {
    const fetchMock = installFetch({ voice_id: 'voice-voxcpm2' });

    await saveVoice({
      asset_id: 'asset-voxcpm2',
      name: 'VoxCPM2 Voice',
      default_engine: 'voxcpm2',
      reference_transcript: 'Editable transcript.',
      metadata: {
        source: 'voice-lab',
        engine_settings: {
          voxcpm2: {
            cloning_mode: 'transcript_guided',
            style_prompt: 'Warm phone-call delivery.',
            cfg_value: 2.2,
            inference_timesteps: 12,
            normalize: true,
            denoise: false
          },
          f5: {
            speech_speed: 0.85
          }
        }
      }
    });

    expect(JSON.parse(lastRequest(fetchMock).init.body as string)).toMatchObject({
      metadata: {
        engine_settings: {
          voxcpm2: {
            cloning_mode: 'transcript_guided',
            style_prompt: 'Warm phone-call delivery.',
            cfg_value: 2.2,
            inference_timesteps: 12,
            normalize: true,
            denoise: false
          }
        }
      }
    });
    expect(routeSource).toMatch(/engine_settings[\s\S]*voxcpm2[\s\S]*cloning_mode/);
    expect(routeSource).toMatch(/selectedEngine[\s\S]*voxcpm2[\s\S]*engine_settings/);
    expect(routeSource).toMatch(/selectedEngine[\s\S]*f5[\s\S]*speech_speed/);
  });

  it('allows saving a voice without a successful preview gate', () => {
    expect(voiceLabSources).toContain('Save Voice');
    expect(voiceLabSources).toContain('Preview Voice');
    expect(voiceLabSources).toContain('Use default engine');
    expect(routeSource).toMatch(/canSave\s*=\s*Boolean\([\s\S]*asset[\s\S]*voiceName[\s\S]*transcript[\s\S]*selectedEngine/i);
    expect(routeSource).not.toMatch(/canSave\s*=\s*Boolean\([^)]*preview/i);
    expect(routeSource).not.toMatch(/preview\s*(?:Succeeded|Complete|Ready)\s*&&\s*canSave/i);
  });

  it('preserves user input and preview text when preview synthesis fails', () => {
    for (const stateTerm of ['voiceName', 'transcript', 'selectedEngine', 'previewText']) {
      expect(voiceLabSources).toMatch(new RegExp(stateTerm, 'i'));
    }

    expect(voiceLabSources).toMatch(/preview.*(?:error|failed|failure)/i);
  });

  it('wires Voice Library list, rename, and test-play through row-scoped sources', () => {
    for (const copy of [
      'Voice Library',
      'Test Voice',
      'Rename Voice',
      'Delete Voice',
      'Type a test phrase',
      'Use default engine',
      'renameVoice',
      'testPlayVoice'
    ]) {
      expect(voiceLabSources).toContain(copy);
    }

    expect(voiceLabSources).toMatch(/listVoices/);
    expect(voiceLabSources).toMatch(/testingVoiceId|testPlayState|row.*loading/i);
  });

  it('wires referenced delete confirmation through explicit force semantics', () => {
    for (const copy of [
      'Delete voice: Delete this voice?',
      'Force Delete Voice',
      'Voice unavailable',
      'referents'
    ]) {
      expect(voiceLabSources).toContain(copy);
    }

    expect(voiceLabSources).toMatch(/deleteVoice\([^)]*false/);
    expect(voiceLabSources).toMatch(/deleteVoice\([^)]*true/);
  });
});
