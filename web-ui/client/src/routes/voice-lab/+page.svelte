<script lang="ts">
  import { Save } from 'lucide-svelte';
  import { onMount } from 'svelte';

  import { toApiPath } from '$lib/api/client';
  import { getSettings } from '$lib/api/settings';
  import {
    deleteVoice,
    listVoices,
    previewVoice,
    renameVoice,
    saveVoice,
    testPlayVoice,
    transcribeVoiceAsset,
    uploadVoiceAsset
  } from '$lib/api/voices';
  import type {
    AiBackendEngineStatus,
    TtsEngineMetadata,
    VoiceAsset,
    VoiceSummary,
    VoiceTestPlayPayload,
    VoiceSynthesisResult
  } from '$lib/api/types';
  import AudioSampleDropzone from '$lib/components/voice/AudioSampleDropzone.svelte';
  import SynthPreviewPanel from '$lib/components/voice/SynthPreviewPanel.svelte';
  import TranscriptEditor from '$lib/components/voice/TranscriptEditor.svelte';
  import TtsEnginePicker from '$lib/components/voice/TtsEnginePicker.svelte';
  import VoiceDeleteDialog from '$lib/components/voice/VoiceDeleteDialog.svelte';
  import VoiceLibraryList from '$lib/components/voice/VoiceLibraryList.svelte';
  import VoiceRenameDialog from '$lib/components/voice/VoiceRenameDialog.svelte';

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
      caveat_chips: ['No transcript required', 'Native streaming'],
      requires_transcript: false,
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'engine synthesis is not implemented in Phase 02'
      }
    },
    {
      id: 'qwen3_0_6b',
      label: 'Qwen3-TTS 0.6B-Base',
      caveat_chips: ['Opt-in', 'Latency caveat', 'Accent caveat'],
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'engine synthesis is not implemented in Phase 02'
      }
    },
    {
      id: 'luxtts',
      label: 'LuxTTS',
      caveat_chips: ['Quality caveat', 'Retest references'],
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'engine synthesis is not implemented in Phase 02'
      }
    },
    {
      id: 'chatterbox_turbo',
      label: 'Chatterbox Turbo',
      caveat_chips: ['Experimental', 'Avoid baseline long-form'],
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'engine synthesis is not implemented in Phase 02'
      }
    },
    {
      id: 'tada_1b',
      label: 'TADA 1B',
      caveat_chips: ['Experimental', 'High VRAM', 'WSL caution'],
      availability: {
        available: false,
        state: 'unavailable',
        unavailable_reason: 'engine synthesis is not implemented in Phase 02'
      }
    },
    {
      id: 'voxcpm2',
      label: 'VoxCPM2',
      caveat_chips: ['Candidate', '48 kHz', 'RTX 3060 gate pending'],
      requires_transcript: false,
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
  let speechSpeed = 0.85;
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
  let libraryVoices: VoiceSummary[] = [];
  let libraryLoading = true;
  let libraryError = '';
  let libraryStatus = '';
  let testingVoiceId: string | null = null;
  let testAudioByVoiceId: Record<string, string> = {};
  let renamingVoice: VoiceSummary | null = null;
  let deletingVoice: VoiceSummary | null = null;
  let deleteReferents: Array<Record<string, string>> = [];
  let renameState: 'idle' | 'saving' = 'idle';
  let deleteState: 'idle' | 'deleting' = 'idle';
  let activeAudio: HTMLAudioElement | null = null;

  $: canPreview = Boolean(asset && transcript.trim() && selectedEngine && previewText.trim());
  $: canSave = Boolean(asset && voiceName.trim() && transcript.trim() && selectedEngine);
  $: uploadedSampleUrl = asset ? toApiPath(`/voices/assets/${encodeURIComponent(asset.asset_id)}/sample`) : null;
  $: if (transcriptState === 'error' && transcript.trim()) {
    transcriptState = 'ready';
    transcriptError = '';
  }

  onMount(() => {
    void loadEngineMetadata();
    void loadVoiceLibrary();
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
    voiceName = voiceNameFromFilename(file.name);
    uploadError = '';
    transcriptError = '';
    previewError = '';
    saveError = '';
    testAudioByVoiceId = {};
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
        engine: useDefaultEngine ? null : selectedEngine,
        speech_speed: speechSpeed
      });
      previewAudioUrl = synthesisAudioUrl(result);
      previewState = previewAudioUrl ? 'ready' : 'error';
      previewError = previewAudioUrl
        ? ''
        : 'Preview did not return playable audio. You can retry or save this voice anyway.';
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
        metadata: {
          source: 'voice-lab',
          sample_filename: selectedFile?.name ?? null,
          speech_speed: speechSpeed,
          engine_settings: {
            [selectedEngine]: {
              speech_speed: speechSpeed
            }
          }
        }
      });
      saveState = 'saved';
      libraryStatus = 'Voice Library refreshed.';
      await loadVoiceLibrary();
    } catch {
      saveState = 'error';
      saveError = 'RayMe could not save this voice. Check the required fields and try again.';
    }
  }

  async function loadVoiceLibrary() {
    libraryLoading = true;
    libraryError = '';

    try {
      libraryVoices = await listVoices();
    } catch {
      libraryError = 'RayMe could not load the Voice Library. Try again after checking the Web UI server.';
    } finally {
      libraryLoading = false;
    }
  }

  function openRenameDialog(voice: VoiceSummary) {
    renamingVoice = voice;
    libraryStatus = '';
  }

  async function saveRename(name: string) {
    if (!renamingVoice) {
      return;
    }

    const voiceId = renamingVoice.voice_id;
    renameState = 'saving';
    libraryStatus = '';

    try {
      const renamed = await renameVoice(voiceId, name);
      libraryVoices = libraryVoices.map((voice) => (voice.voice_id === voiceId ? renamed : voice));
      renamingVoice = null;
      libraryStatus = 'Voice renamed.';
    } catch {
      libraryError = 'RayMe could not rename this voice. Check the name and try again.';
    } finally {
      renameState = 'idle';
    }
  }

  async function playLibraryVoice(voice: VoiceSummary, payload: VoiceTestPlayPayload) {
    pauseActiveAudio();
    testingVoiceId = voice.voice_id;
    libraryStatus = '';

    try {
      const result = await testPlayVoice(voice.voice_id, {
        ...payload,
        text: payload.text.trim() || 'The line is open. This is the saved RayMe voice.'
      });
      const audioUrl = synthesisAudioUrl(result);
      if (audioUrl) {
        testAudioByVoiceId = { ...testAudioByVoiceId, [voice.voice_id]: audioUrl };
        activeAudio = new Audio(audioUrl);
        void activeAudio.play().catch(() => {
          libraryStatus = 'Test voice ready.';
        });
      }
      libraryStatus = 'Test voice ready.';
    } catch {
      libraryError = 'RayMe could not test this voice. Try a different phrase or engine.';
    } finally {
      testingVoiceId = null;
    }
  }

  async function deleteLibraryVoice(voice: VoiceSummary) {
    libraryStatus = '';
    libraryError = '';
    deleteState = 'deleting';

    try {
      const result = await deleteVoice(voice.voice_id, false);
      if (result.referents?.length) {
        deletingVoice = voice;
        deleteReferents = result.referents;
        return;
      }

      removeVoiceFromLibrary(voice.voice_id);
      libraryStatus = 'Voice deleted.';
    } catch {
      libraryError = 'RayMe could not delete this voice. Try again after checking current assignments.';
    } finally {
      deleteState = 'idle';
    }
  }

  async function forceDeleteLibraryVoice() {
    if (!deletingVoice) {
      return;
    }

    const voiceId = deletingVoice.voice_id;
    deleteState = 'deleting';
    libraryError = '';

    try {
      await deleteVoice(voiceId, true);
      removeVoiceFromLibrary(voiceId);
      deletingVoice = null;
      deleteReferents = [];
      libraryStatus = 'Referenced characters will show Voice unavailable.';
    } catch {
      libraryError = 'RayMe could not force delete this voice. Try again after checking current assignments.';
    } finally {
      deleteState = 'idle';
    }
  }

  function cancelDeleteDialog() {
    deletingVoice = null;
    deleteReferents = [];
    deleteState = 'idle';
  }

  function removeVoiceFromLibrary(voiceId: string) {
    libraryVoices = libraryVoices.filter((voice) => voice.voice_id !== voiceId);
  }

  function pauseActiveAudio() {
    if (activeAudio) {
      activeAudio.pause();
      activeAudio = null;
    }
  }

  function synthesisAudioUrl(result: VoiceSynthesisResult) {
    const url = result.audio_url ?? result.preview_url;
    if (url) {
      return url;
    }
    if (result.audio_base64) {
      return `data:${result.content_type || 'audio/wav'};base64,${result.audio_base64}`;
    }
    return null;
  }

  function voiceNameFromFilename(filename: string) {
    return filename.replace(/\.[^.]+$/, '').trim();
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
        sampleUrl={uploadedSampleUrl}
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
        bind:speechSpeed
        disabled={!canPreview}
        state={previewState}
        audioUrl={previewAudioUrl}
        errorMessage={previewError}
        onPreview={previewCurrentVoice}
      />
    </div>

    <aside class="side-rail" aria-label="Voice Lab side rail">
      <div class="save-panel" aria-label="Save voice">
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
      </div>

      <VoiceLibraryList
        voices={libraryVoices}
        {engines}
        loading={libraryLoading}
        errorMessage={libraryError}
        {testingVoiceId}
        testAudioByVoiceId={testAudioByVoiceId}
        onTestPlay={playLibraryVoice}
        onRename={openRenameDialog}
        onDelete={deleteLibraryVoice}
      />

      {#if libraryStatus}
        <p class="success" role="status">{libraryStatus}</p>
      {/if}
    </aside>
  </div>
</section>

<VoiceRenameDialog
  open={Boolean(renamingVoice)}
  voice={renamingVoice}
  submitting={renameState === 'saving'}
  onSave={saveRename}
  onCancel={() => (renamingVoice = null)}
/>

<VoiceDeleteDialog
  open={Boolean(deletingVoice)}
  voice={deletingVoice}
  referents={deleteReferents}
  submitting={deleteState === 'deleting'}
  onForceConfirm={forceDeleteLibraryVoice}
  onCancel={cancelDeleteDialog}
/>

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

  .side-rail,
  .save-panel {
    display: grid;
    min-width: 0;
    gap: var(--space-md);
  }

  .save-panel {
    align-content: start;
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
