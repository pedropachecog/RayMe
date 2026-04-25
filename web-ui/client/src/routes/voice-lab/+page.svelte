<script lang="ts">
  import { Save } from 'lucide-svelte';
  import { onMount } from 'svelte';

  import { getSettings } from '$lib/api/settings';
  import {
    previewVoice,
    saveVoice,
    transcribeVoiceAsset,
    uploadVoiceAsset
  } from '$lib/api/voices';
  import type {
    AiBackendEngineStatus,
    TtsEngineMetadata,
    VoiceAsset,
    VoiceSynthesisResult
  } from '$lib/api/types';
  import AudioSampleDropzone from '$lib/components/voice/AudioSampleDropzone.svelte';
  import SynthPreviewPanel from '$lib/components/voice/SynthPreviewPanel.svelte';
  import TranscriptEditor from '$lib/components/voice/TranscriptEditor.svelte';
  import TtsEnginePicker from '$lib/components/voice/TtsEnginePicker.svelte';

  const DEFAULT_TTS_ENGINES: TtsEngineMetadata[] = [
    {
      id: 'f5',
      label: 'F5-TTS',
      is_default: true,
      caveat_chips: ['Default', 'Requires transcript'],
      requires_transcript: true,
      availability: { available: true, state: 'resident' }
    },
    {
      id: 'xtts_v2',
      label: 'XTTS v2',
      caveat_chips: ['Transcript portable', 'Native streaming'],
      requires_transcript: true,
      availability: { available: true, state: 'idle' }
    },
    {
      id: 'qwen3_0_6b',
      label: 'Qwen3-TTS 0.6B-Base',
      caveat_chips: ['Opt-in', 'Latency caveat', 'Accent caveat'],
      availability: { available: true, state: 'idle' }
    },
    {
      id: 'luxtts',
      label: 'LuxTTS',
      caveat_chips: ['Quality caveat', 'Retest references'],
      availability: { available: true, state: 'idle' }
    },
    {
      id: 'chatterbox_turbo',
      label: 'Chatterbox Turbo',
      caveat_chips: ['Experimental', 'Avoid baseline long-form'],
      availability: { available: true, state: 'idle' }
    },
    {
      id: 'tada_1b',
      label: 'TADA 1B',
      caveat_chips: ['Experimental', 'High VRAM', 'WSL caution'],
      availability: { available: true, state: 'idle' }
    }
  ];

  const validSampleExtension = /\.(wav|mp3|flac)$/i;

  let voiceName = '';
  let selectedFile: File | null = null;
  let asset: VoiceAsset | null = null;
  let transcript = '';
  let selectedEngine = 'f5';
  let previewText = 'The line is open. This is how the saved RayMe voice will sound.';
  let useDefaultEngine = true;
  let engines: TtsEngineMetadata[] = DEFAULT_TTS_ENGINES;
  let uploadState: 'idle' | 'uploading' | 'ready' | 'error' = 'idle';
  let transcriptState: 'idle' | 'pending' | 'ready' | 'error' = 'idle';
  let previewState: 'idle' | 'synthesizing' | 'ready' | 'error' = 'idle';
  let saveState: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
  let uploadError = '';
  let transcriptError = '';
  let previewError = '';
  let saveError = '';
  let previewAudioUrl: string | null = null;

  $: canPreview = Boolean(asset && voiceName.trim() && transcript.trim() && selectedEngine);
  $: canSave = Boolean(asset && voiceName.trim() && transcript.trim() && selectedEngine);

  onMount(() => {
    void loadEngineMetadata();
  });

  async function loadEngineMetadata() {
    try {
      const settings = await getSettings();
      engines = normalizeEngines(settings.ai_backend_status?.available_engines);
      selectedEngine = settings.tts_default_engine || engines.find((engine) => engine.is_default)?.id || 'f5';
    } catch {
      engines = DEFAULT_TTS_ENGINES;
    }
  }

  function normalizeEngines(value: unknown): TtsEngineMetadata[] {
    if (!Array.isArray(value) || value.length === 0) {
      return DEFAULT_TTS_ENGINES;
    }

    const byId = new Map(DEFAULT_TTS_ENGINES.map((engine) => [engine.id, engine]));
    for (const item of value) {
      if (typeof item === 'string') {
        const fallback = byId.get(item);
        if (fallback) {
          byId.set(item, fallback);
        }
        continue;
      }

      const engine = item as AiBackendEngineStatus;
      const id = engine.id ?? engine.engine_id;
      if (!id) {
        continue;
      }

      const fallback = byId.get(id);
      byId.set(id, {
        ...(fallback ?? {
          id,
          label: engine.label || id,
          caveat_chips: [],
          availability: { available: true, state: 'idle' }
        }),
        label: engine.label || fallback?.label || id,
        availability: {
          available: engine.available !== false,
          state: engine.state ?? (engine.resident ? 'resident' : 'idle'),
          unavailable_reason: engine.unavailable_reason
        }
      });
    }

    return DEFAULT_TTS_ENGINES.map((engine) => byId.get(engine.id) ?? engine);
  }

  async function handleSampleSelected(file: File) {
    selectedFile = file;
    asset = null;
    transcript = '';
    uploadError = '';
    transcriptError = '';
    previewError = '';
    saveError = '';
    previewState = 'idle';
    saveState = 'idle';

    if (!validSampleExtension.test(file.name)) {
      uploadState = 'error';
      uploadError = 'Unsupported file type. Upload a WAV, MP3, or FLAC sample.';
      return;
    }

    uploadState = 'uploading';
    try {
      asset = await uploadVoiceAsset(file);
      uploadState = 'ready';
    } catch {
      uploadState = 'error';
      uploadError = 'RayMe could not upload this sample. Check the file format and try again.';
    }
  }

  async function transcribeSample() {
    if (!asset) {
      return;
    }

    transcriptState = 'pending';
    transcriptError = '';

    try {
      const result = await transcribeVoiceAsset(asset.asset_id);
      transcript = result.reference_transcript ?? '';
      transcriptState = 'ready';
    } catch {
      transcriptState = 'error';
      transcriptError = 'Transcription failed. Retry or enter the transcript manually without re-uploading.';
    }
  }

  async function previewCurrentVoice() {
    if (!asset || !canPreview) {
      return;
    }

    previewState = 'synthesizing';
    previewError = '';
    previewAudioUrl = null;

    try {
      const result: VoiceSynthesisResult = await previewVoice({
        asset_id: asset.asset_id,
        name: voiceName.trim(),
        default_engine: selectedEngine,
        reference_transcript: transcript.trim(),
        preview_text: previewText,
        use_default_engine: useDefaultEngine,
        engine: useDefaultEngine ? null : selectedEngine
      });
      previewAudioUrl = result.audio_url ?? result.preview_url ?? null;
      previewState = 'ready';
    } catch {
      previewState = 'error';
      previewError = 'Preview failed. You can retry or save this voice anyway.';
    }
  }

  async function saveCurrentVoice() {
    if (!asset || !canSave) {
      return;
    }

    saveState = 'saving';
    saveError = '';

    try {
      await saveVoice({
        asset_id: asset.asset_id,
        name: voiceName.trim(),
        default_engine: selectedEngine,
        reference_transcript: transcript.trim(),
        metadata: { source: 'voice-lab', sample_filename: selectedFile?.name ?? null }
      });
      saveState = 'saved';
    } catch {
      saveState = 'error';
      saveError = 'RayMe could not save this voice. Check the required fields and try again.';
    }
  }
</script>

<section class="voice-lab" aria-labelledby="voice-lab-title">
  <div class="heading">
    <div>
      <p class="eyebrow">Voice Lab</p>
      <h1 id="voice-lab-title">Voice Lab</h1>
    </div>
  </div>

  <ol class="steps" aria-label="Voice Lab steps">
    <li>1 Upload</li>
    <li>2 Transcript</li>
    <li>3 Engine</li>
    <li>4 Preview</li>
    <li>5 Save</li>
  </ol>

  <div class="workspace">
    <div class="creation-flow">
      <AudioSampleDropzone
        {asset}
        busy={uploadState === 'uploading'}
        errorMessage={uploadError}
        onFileSelected={handleSampleSelected}
      />

      <TranscriptEditor
        bind:transcript
        disabled={!asset}
        state={transcriptState}
        errorMessage={transcriptError}
        onTranscribe={transcribeSample}
      />

      <TtsEnginePicker bind:selectedEngine {engines} />

      <SynthPreviewPanel
        bind:previewText
        bind:useDefaultEngine
        disabled={!canPreview}
        state={previewState}
        audioUrl={previewAudioUrl}
        errorMessage={previewError}
        onPreview={previewCurrentVoice}
      />
    </div>

    <aside class="save-panel" aria-label="Save voice">
      <label>
        <span>Voice name</span>
        <input aria-label="Voice name" type="text" bind:value={voiceName} autocomplete="off" />
      </label>

      <div class="save-state">
        <p>Save Voice is available once sample, name, transcript, and engine are valid. Preview success is not required.</p>
        {#if saveState === 'saved'}
          <p class="success" role="status">Voice saved.</p>
        {:else if saveError}
          <p class="error" role="alert">{saveError}</p>
        {/if}
      </div>

      <button class="primary" type="button" disabled={!canSave || saveState === 'saving'} on:click={saveCurrentVoice}>
        <Save size={16} strokeWidth={1.8} aria-hidden="true" />
        <span>{saveState === 'saving' ? 'Saving...' : 'Save Voice'}</span>
      </button>
    </aside>
  </div>
</section>

<style>
  .voice-lab {
    display: grid;
    min-width: 0;
    gap: var(--space-xl);
  }

  .heading {
    display: grid;
    gap: var(--space-sm);
  }

  .eyebrow,
  h1,
  p {
    margin: 0;
  }

  .eyebrow {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  h1 {
    color: var(--color-text);
    font-size: var(--font-display);
    font-weight: 600;
    line-height: var(--line-display);
  }

  .steps {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--space-sm);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .steps li {
    display: grid;
    min-height: 40px;
    place-items: center;
    border-radius: var(--radius-md);
    padding: 0 var(--space-sm);
    background: rgba(182, 160, 255, 0.14);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
    text-align: center;
  }

  .workspace {
    display: grid;
    min-width: 0;
    gap: var(--space-xl);
  }

  .creation-flow {
    display: grid;
    min-width: 0;
    gap: var(--space-lg);
  }

  .save-panel {
    display: grid;
    align-content: start;
    gap: var(--space-md);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.78);
  }

  label {
    display: grid;
    min-width: 0;
    gap: var(--space-xs);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  input {
    width: 100%;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(6, 14, 32, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    font-size: var(--font-body);
    font-weight: 400;
    line-height: var(--line-body);
  }

  .save-state {
    display: grid;
    gap: var(--space-sm);
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  .success,
  .error {
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  .success {
    background: rgba(0, 227, 253, 0.08);
    color: var(--color-text);
  }

  .error {
    background: rgba(255, 113, 108, 0.1);
    color: var(--color-danger);
  }

  button {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(9, 19, 40, 0.82);
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
    line-height: var(--line-label);
  }

  button.primary {
    background: var(--color-primary);
    color: var(--color-surface);
  }

  @media (max-width: 520px) {
    .steps {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .save-panel {
      padding: var(--space-md);
    }
  }

  @media (min-width: 1060px) {
    .workspace {
      grid-template-columns: minmax(520px, 760px) minmax(320px, 420px);
      align-items: start;
    }
  }
</style>
