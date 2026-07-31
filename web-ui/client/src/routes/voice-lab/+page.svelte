<script lang="ts">
  import { RefreshCw, Save } from 'lucide-svelte';
  import { onDestroy, onMount } from 'svelte';

  import { toApiPath } from '$lib/api/client';
  import { getSettings } from '$lib/api/settings';
  import {
    deleteVoice,
    getVoicePreparationStatus,
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
    TtsModelReadiness,
    TtsPromptReadiness,
    VoiceAsset,
    VoiceMetadata,
    VoiceSummary,
    VoiceTestPlayPayload,
    VoxCpm2EngineSettings,
    VoiceSynthesisResult
  } from '$lib/api/types';
  import AudioSampleDropzone from '$lib/components/voice/AudioSampleDropzone.svelte';
  import SynthPreviewPanel from '$lib/components/voice/SynthPreviewPanel.svelte';
  import TranscriptEditor from '$lib/components/voice/TranscriptEditor.svelte';
  import TtsEnginePicker from '$lib/components/voice/TtsEnginePicker.svelte';
  import VoxCpm2Controls from '$lib/components/voice/VoxCpm2Controls.svelte';
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
      id: 'qwen3_1_7b',
      label: 'Qwen3-TTS 1.7B-Base',
      caveat_chips: ['1.7B Base', 'Requires transcript', 'Native streaming'],
      requires_transcript: true,
      supports_streaming: true,
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
  const QWEN3_ENGINE_ID = 'qwen3_1_7b';
  const QWEN3_LAN_SCOPE = 'rayme_lan_call_testing';
  const QWEN3_FAILURE_COPY: Record<string, string> = {
    qwen3_transcript_required: 'Add the matching reference transcript before using Qwen3-TTS 1.7B.',
    qwen3_transcript_mismatch: 'This transcript does not appear to match the voice sample. Review the transcript or choose a different sample, then try again.',
    qwen3_alignment_failed: 'This transcript does not appear to match the voice sample. Review the transcript or choose a different sample, then try again.',
    qwen3_prompt_failed: 'RayMe could not prepare this voice. Retry preparation. Your sample, transcript, name, and engine selection are still here.',
    qwen3_prompt_not_ready: 'RayMe could not prepare this voice. Retry preparation. Your sample, transcript, name, and engine selection are still here.',
    qwen3_generation_ceiling: 'RayMe stopped this voice because the generated audio exceeded its safe limit. Check the transcript and try again.',
    qwen3_worker_protocol: 'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.',
    qwen3_worker_timeout: 'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.',
    qwen3_worker_stopped: 'Qwen3-TTS 1.7B is unavailable right now. Choose another voice or check AI backend status in Settings.'
  };
  const DEFAULT_VOXCPM2_SETTINGS: Required<VoxCpm2EngineSettings> = {
    cloning_mode: 'reference_only',
    style_prompt: '',
    cfg_value: 2.0,
    inference_timesteps: 10,
    normalize: false,
    denoise: false
  };

  let voiceName = '';
  let selectedFile: File | null = null;
  let asset: VoiceAsset | null = null;
  let transcript = '';
  let selectedEngine = 'f5';
  let previewText = 'The line is open. This is how the saved RayMe voice will sound.';
  let useDefaultEngine = true;
  let speechSpeed = 0.85;
  let voiceDataSteward = '';
  let authorizationBasis = '';
  let useScope = '';
  let authorizationError = '';
  let voiceDataStewardInput: HTMLInputElement;
  let authorizationBasisInput: HTMLInputElement;
  let useScopeSelect: HTMLSelectElement;
  let engineSettings = {
    voxcpm2: { ...DEFAULT_VOXCPM2_SETTINGS }
  };
  let engines: TtsEngineMetadata[] = DEFAULT_TTS_ENGINES;
  let uploadState: 'idle' | 'uploading' | 'ready' | 'error' = 'idle';
  let transcriptState: 'idle' | 'pending' | 'ready' | 'error' = 'idle';
  let previewState: 'idle' | 'preparing' | 'synthesizing' | 'ready' | 'error' = 'idle';
  let modelReadiness: TtsModelReadiness = { state: 'idle', engine_id: null };
  let promptReadiness: TtsPromptReadiness = { state: 'none' };
  let preparationPollToken = 0;
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

  $: selectedEngineMetadata = engines.find((engine) => engine.id === selectedEngine);
  $: isQwenSelected = selectedEngine === QWEN3_ENGINE_ID;
  $: transcriptRequired = selectedEngineMetadata?.requires_transcript === true;
  $: hasRequiredTranscript = !transcriptRequired || Boolean(transcript.trim());
  $: hasQwenAuthorization =
    !isQwenSelected || Boolean(voiceDataSteward.trim() && authorizationBasis.trim() && useScope);
  $: canPreview = Boolean(asset && hasRequiredTranscript && hasQwenAuthorization && selectedEngine && previewText.trim());
  $: canSave = Boolean(asset && voiceName.trim() && hasRequiredTranscript && hasQwenAuthorization && selectedEngine);
  $: uploadedSampleUrl = asset ? toApiPath(`/voices/assets/${encodeURIComponent(asset.asset_id)}/sample`) : null;
  $: if (transcriptState === 'error' && transcript.trim()) {
    transcriptState = 'ready';
    transcriptError = '';
  }

  onMount(() => {
    void loadEngineMetadata();
    void loadVoiceLibrary();
  });

  onDestroy(() => {
    preparationPollToken += 1;
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
    const returnedIds = new Set<string>();
    for (const item of value) {
      if (typeof item === 'string') {
        returnedIds.add(item);
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
      returnedIds.add(id);

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

    const returned = [...returnedIds]
      .map((id) => byId.get(id))
      .filter((engine): engine is TtsEngineMetadata => Boolean(engine));
    const missingFallbacks = DEFAULT_TTS_ENGINES.filter((engine) => !returnedIds.has(engine.id)).map(
      (engine) => ({
        ...engine,
        availability: {
          available: false,
          state: 'unavailable',
          unavailable_reason: 'Engine was not reported by the AI backend.'
        }
      })
    );
    return [...returned, ...missingFallbacks];
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
    if (!focusFirstInvalidQwenField() || !asset || !canPreview) {
      return;
    }

    const qwenOperation = selectedEngine === QWEN3_ENGINE_ID;
    const pollToken = qwenOperation ? beginPreparationMonitoring() : 0;
    previewState = qwenOperation ? 'preparing' : 'synthesizing';
    previewError = '';
    previewAudioUrl = null;

    try {
      const result: VoiceSynthesisResult = await previewVoice({
        asset_id: asset.asset_id,
        name: voiceName.trim(),
        default_engine: selectedEngine,
        reference_transcript: transcript.trim(),
        ...(qwenOperation
          ? {
              voice_data_steward: voiceDataSteward.trim(),
              authorization_basis: authorizationBasis.trim(),
              use_scope: useScope
            }
          : {}),
        preview_text: previewText,
        use_default_engine: useDefaultEngine,
        engine: useDefaultEngine ? null : selectedEngine,
        speech_speed: speechSpeed,
        ...(selectedEngine === 'voxcpm2' ? { metadata: buildVoiceMetadata() } : {})
      });
      previewState = 'synthesizing';
      if (result.error || result.status === 'tts_failed') {
        previewState = 'error';
        previewError = qwenOperation
          ? qwenFailureMessage(errorCodeFrom(result))
          : 'Preview failed. You can retry or save this voice anyway.';
        return;
      }
      previewAudioUrl = synthesisAudioUrl(result);
      previewState = previewAudioUrl ? 'ready' : 'error';
      previewError = previewAudioUrl
        ? ''
        : 'Preview did not return playable audio. You can retry or save this voice anyway.';
    } catch {
      previewState = 'error';
      previewError = qwenOperation
        ? qwenFailureMessage(promptReadiness.error_code)
        : 'Preview failed. You can retry or save this voice anyway.';
    } finally {
      if (pollToken) {
        preparationPollToken += 1;
      }
    }
  }

  async function saveCurrentVoice() {
    if (!focusFirstInvalidQwenField() || !asset || !canSave) {
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
        ...(isQwenSelected
          ? {
              voice_data_steward: voiceDataSteward.trim(),
              authorization_basis: authorizationBasis.trim(),
              use_scope: useScope
            }
          : {}),
        metadata: {
          ...buildVoiceMetadata(),
          sample_filename: selectedFile?.name ?? null
        }
      });
      saveState = 'saved';
      libraryStatus = 'Voice Library refreshed.';
      await loadVoiceLibrary();
    } catch {
      saveState = 'error';
      saveError = isQwenSelected
        ? qwenFailureMessage(promptReadiness.error_code)
        : 'RayMe could not save this voice. Check the required fields and try again.';
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

  function focusFirstInvalidQwenField(): boolean {
    if (!isQwenSelected) {
      authorizationError = '';
      return true;
    }
    if (!asset) {
      document.querySelector<HTMLInputElement>('input[type="file"]')?.focus();
      return false;
    }
    if (!transcript.trim()) {
      transcriptError = 'Add the matching reference transcript before using Qwen3-TTS 1.7B.';
      document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Reference transcript"]')?.focus();
      return false;
    }
    if (!voiceDataSteward.trim()) {
      authorizationError = 'Add the reference source, authorization basis, and use scope before using this voice.';
      voiceDataStewardInput?.focus();
      return false;
    }
    if (!authorizationBasis.trim()) {
      authorizationError = 'Add the reference source, authorization basis, and use scope before using this voice.';
      authorizationBasisInput?.focus();
      return false;
    }
    if (!useScope) {
      authorizationError = 'Add the reference source, authorization basis, and use scope before using this voice.';
      useScopeSelect?.focus();
      return false;
    }
    authorizationError = '';
    return true;
  }

  function beginPreparationMonitoring(): number {
    const token = ++preparationPollToken;
    modelReadiness = { state: 'loading', engine_id: QWEN3_ENGINE_ID };
    promptReadiness = { state: 'prewarming' };
    void monitorPreparation(token);
    return token;
  }

  async function monitorPreparation(token: number) {
    for (let attempt = 0; attempt < 480 && token === preparationPollToken; attempt += 1) {
      try {
        const status = await getVoicePreparationStatus();
        if (token !== preparationPollToken) return;
        modelReadiness = status.model;
        promptReadiness = status.prompt;
        if (status.prompt.state === 'ready') {
          previewState = 'synthesizing';
          return;
        }
        if (status.model.state === 'failed' || status.model.state === 'unavailable' || status.prompt.state === 'failed') {
          return;
        }
      } catch {
        // The synthesis request remains authoritative; a transient status miss does not erase form state.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
  }

  function errorCodeFrom(result: VoiceSynthesisResult): string | null {
    const error = result.error;
    return error && typeof error === 'object' && typeof (error as Record<string, unknown>).code === 'string'
      ? String((error as Record<string, unknown>).code)
      : null;
  }

  function qwenFailureMessage(code: string | null | undefined): string {
    return code && QWEN3_FAILURE_COPY[code]
      ? QWEN3_FAILURE_COPY[code]
      : 'RayMe could not prepare this voice. Retry preparation. Your sample, transcript, name, and engine selection are still here.';
  }

  function voiceNameFromFilename(filename: string) {
    return filename.replace(/\.[^.]+$/, '').trim();
  }

  function buildVoiceMetadata(): VoiceMetadata {
    if (selectedEngine === 'voxcpm2') {
      return {
        source: 'voice-lab',
        speech_speed: speechSpeed,
        engine_settings: {
          voxcpm2: {
            cloning_mode: engineSettings.voxcpm2.cloning_mode,
            style_prompt: engineSettings.voxcpm2.style_prompt,
            cfg_value: engineSettings.voxcpm2.cfg_value,
            inference_timesteps: engineSettings.voxcpm2.inference_timesteps,
            normalize: engineSettings.voxcpm2.normalize,
            denoise: engineSettings.voxcpm2.denoise
          }
        }
      };
    }

    return {
      source: 'voice-lab',
      speech_speed: speechSpeed,
      engine_settings: {
        [selectedEngine || 'f5']: {
          speech_speed: speechSpeed
        }
      }
    };
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

      {#if selectedEngine === 'qwen3_1_7b'}
        <section class="authorization-panel" aria-labelledby="reference-authorization-title">
          <div>
            <h2 id="reference-authorization-title">Reference authorization</h2>
            <p>Add where this recording came from, why you are authorized to use it, and its permitted RayMe scope.</p>
          </div>
          <label>
            <span>Reference source</span>
            <input
              bind:this={voiceDataStewardInput}
              bind:value={voiceDataSteward}
              name="voice_data_steward"
              type="text"
              autocomplete="off"
              aria-invalid={Boolean(authorizationError && !voiceDataSteward.trim())}
            />
          </label>
          <label>
            <span>Authorization basis</span>
            <input
              bind:this={authorizationBasisInput}
              bind:value={authorizationBasis}
              name="authorization_basis"
              type="text"
              autocomplete="off"
              aria-invalid={Boolean(authorizationError && !authorizationBasis.trim())}
            />
          </label>
          <label>
            <span>Use scope</span>
            <select
              bind:this={useScopeSelect}
              bind:value={useScope}
              name="use_scope"
              aria-invalid={Boolean(authorizationError && !useScope)}
            >
              <option value="">Choose permitted scope</option>
              <option value={QWEN3_LAN_SCOPE}>RayMe LAN call testing</option>
            </select>
          </label>
          {#if authorizationError}
            <p class="error" role="alert">{authorizationError}</p>
          {/if}

          <div class="readiness" aria-label="Qwen voice readiness">
            <div>
              <span>Model</span>
              {#if modelReadiness.state === 'loading'}
                <p role="status"><RefreshCw class="progress-icon" size={16} strokeWidth={1.8} aria-hidden="true" /> Loading Qwen3-TTS 1.7B…</p>
              {:else if modelReadiness.state === 'resident'}
                <p class="ready" role="status">Qwen3-TTS 1.7B loaded</p>
              {:else if modelReadiness.state === 'failed' || modelReadiness.state === 'unavailable'}
                <p class="error" role="alert">Qwen3-TTS 1.7B unavailable</p>
              {:else}
                <p>Model not loaded</p>
              {/if}
            </div>
            <div>
              <span>Selected voice</span>
              {#if promptReadiness.state === 'prewarming'}
                <p role="status"><RefreshCw class="progress-icon" size={16} strokeWidth={1.8} aria-hidden="true" /> Preparing saved voice…</p>
              {:else if promptReadiness.state === 'ready'}
                <p class="ready" role="status">Saved voice ready</p>
              {:else if promptReadiness.state === 'failed'}
                <p class="error" role="alert">Voice preparation failed</p>
              {:else}
                <p>Voice not prepared</p>
              {/if}
            </div>
          </div>
        </section>
      {/if}

      {#if selectedEngine === 'voxcpm2'}
        <VoxCpm2Controls bind:settings={engineSettings.voxcpm2} {transcript} />
      {/if}

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
          <p>
            {isQwenSelected
              ? 'Save Voice needs a sample, name, matching transcript, authorization details, and engine. Preview success is not required.'
              : 'Save Voice is available once sample, name, transcript, and engine are valid. Preview success is not required.'}
          </p>
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
  .save-panel,
  .authorization-panel,
  .readiness {
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

  .authorization-panel {
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    background: rgba(20, 31, 56, 0.78);
  }

  .authorization-panel h2 {
    margin: 0;
    color: var(--color-text);
    font-size: var(--font-heading);
    font-weight: 600;
    line-height: var(--line-heading);
  }

  .authorization-panel p {
    color: var(--color-text-muted);
    font-size: var(--font-body);
    line-height: var(--line-body);
  }

  select {
    width: 100%;
    min-height: 44px;
    border: 0;
    border-radius: var(--radius-md);
    padding: 0 var(--space-md);
    background: rgba(6, 14, 32, 0.78);
    box-shadow: inset 0 0 0 1px rgba(64, 72, 93, 0.28);
    color: var(--color-text);
    font-size: var(--font-body);
  }

  .readiness {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .readiness > div {
    min-width: 0;
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    background: rgba(9, 19, 40, 0.56);
  }

  .readiness span {
    color: var(--color-text-muted);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .readiness p {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    margin-top: var(--space-xs);
    overflow-wrap: anywhere;
    color: var(--color-text);
    font-size: var(--font-label);
    font-weight: 600;
  }

  .readiness p.ready {
    color: var(--color-secondary);
  }

  :global(.progress-icon) {
    flex: 0 0 auto;
    animation: readiness-spin 1s linear infinite;
  }

  @keyframes readiness-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.progress-icon) {
      animation: none;
    }
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

    .authorization-panel {
      padding: var(--space-md);
    }

    .readiness {
      grid-template-columns: 1fr;
    }
  }

  @media (min-width: 1060px) {
    .workspace {
      grid-template-columns: minmax(520px, 760px) minmax(320px, 420px);
      align-items: start;
    }
  }
</style>
