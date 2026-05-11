---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
stopped_at: Completed 08-05-PLAN.md
last_updated: "2026-05-11T19:07:10.085Z"
progress:
  total_phases: 10
  completed_phases: 5
  total_plans: 87
  completed_plans: 84
  percent: 97
---

## Phase Status

- Phase 0 complete on 2026-04-23.
- Phase 01.1 Wave 1 complete on 2026-04-24: plans 01.1-01 through 01.1-03 passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 2 complete on 2026-04-24: plan 01.1-04 added the guarded full Phase 1 browser path and passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 3 complete on 2026-04-24: live `OMEN-PC` browser verification passed, Android Chrome product-owner acceptance passed after message-action fixes, and deployed runtime reached commit `6f687e9`.
- Phase 1 plan 01-24 completed after Phase 01.1 hardened acceptance and Android checkpoint on 2026-04-24.
- Phase 01.1 complete on 2026-04-24; next phase gate is Phase 2 planning.
- Phase 02 plan 02-01 completed on 2026-04-24: RED Web UI server voice/schema/settings contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-02 completed on 2026-04-24: RED AI backend health/model residency, STT/VAD, and six-engine TTS registry contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-03 completed on 2026-04-24: RED client Voice Lab, Settings, navigation, local Playwright, and opt-in live OMEN-PC contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-04 completed on 2026-04-24: migration-backed voice storage, safe original sample blob validation, and minimal Voice API/service wiring passed server voice contracts.
- Phase 02 plan 02-05 completed on 2026-04-24: typed Web UI AI backend client, sanitized processing/status errors, RayMe-owned `/api/ai-backend/status`, and Settings AI backend probe integration passed health/settings contracts.
- Phase 02 plan 02-06 completed on 2026-04-25: AI backend settings, lifespan-owned model manager, six-engine residency metadata, and expanded `/health` VRAM/headroom payload passed AI backend health/model-manager contracts.
- Phase 02 plan 02-07 completed on 2026-04-25: faster-whisper STT, Silero VAD gating, hallucination/manual transcript fallback, and transient `/stt/transcribe` passed AI backend STT/health contracts.
- Phase 02 plan 02-08 completed on 2026-04-25: six-engine TTS registry metadata, optional TTS runtime pins, import-gated adapter modules, and transient `/tts/synthesize` route passed AI backend TTS/health contracts.
- Phase 02 plan 02-09 completed on 2026-04-25: durable Web UI voice service/API now uploads, transcribes, previews, saves without preview gate, lists, reads, renames, soft-deletes with referents, and test-plays voices.
- Phase 02 plan 02-10 completed on 2026-04-25: Settings now persists audio/VAD/STT/TTS defaults, enforces VAD bounds, and returns compact AI backend residency status.
- Phase 02 plan 02-11 completed on 2026-04-25: character writes now persist validated default voice IDs and character reads hydrate `none`, `assigned`, and `unavailable` voice states.
- Phase 02 plan 02-12 completed on 2026-04-25: client Voice Lab now uploads samples, transcribes editable references, renders the full six-engine picker, previews optionally, and saves voices without a preview gate.
- Phase 02 plan 02-13 completed on 2026-04-25: Voice Library now lists saved voices, supports row-scoped test-play and rename, and requires explicit force confirmation with readable referents before deleting referenced voices.
- Phase 02 plan 02-14 completed on 2026-04-25: Settings UI now exposes audio defaults, VAD values, compact AI backend residency status, and top-level Voice Lab navigation.
- Phase 02 plan 02-15 completed on 2026-04-25: Character Editor now assigns saved default voices through Save Character, and Gallery cards show assigned, no-voice, and unavailable voice states.
- Phase 02 plan 02-16 completed on 2026-04-25: license notices, runtime evidence gates, Voice Lab operations, safe cleanup paths, and OMEN-PC live evidence templates now document Phase 2 handoff rules.
- Phase 02 plan 02-17 completed on 2026-04-25: AI backend now exposes only a non-call `/webrtc` skeleton with explicit non-readiness flags and fixed Phase 3 offer rejection.
- Phase 02 plan 02-18 completed on 2026-04-25: full local acceptance passed, live OMEN-PC Voice Lab Playwright passed with saved evidence, GPU health showed F5 resident with CUDA STT, and Android Chrome product-owner acceptance passed.
- Phase 02 complete on 2026-04-25; next phase is Phase 3 First Working Call (MVP).
- Phase 03 plan 03-01 completed on 2026-04-25: RED AI backend call-session, inbound audio finalization, WebRTC offer/status/control, and sanitized malformed-payload contracts committed; expected implementation failures remain for later Phase 3 plans.
- Phase 03 plan 03-02 completed on 2026-04-25: RED Web UI call bootstrap/control, voice preflight, backend readiness, durable call boundary rows, and sliding-window call prompt contracts committed; expected implementation failures remain for later Phase 3 plans.
- Phase 03 plan 03-03 completed on 2026-04-25: RED client call FSM, audio helper, desktop/mobile browser, and opt-in live LAN acceptance contracts committed; expected implementation failures remain for later Phase 3 plans.
- Phase 03 plan 03-04 completed on 2026-04-25: AI backend now owns live call sessions, typed `rayme-events`, inbound VAD/STT `user_final` finalization, and Phase 3 `/webrtc` offer/mute/interrupt/end controls.
- Phase 03 plan 03-05 completed on 2026-04-25: Web UI server now owns same-origin `/api/calls` start/offer/mute/interrupt/end facade routes, `call_` to `rtc_` mappings, voice preflight, backend readiness checks, and durable call writeback.
- Phase 03 plan 03-06 completed on 2026-04-25: call prompt context was verified to hydrate selected non-stale text and speech rows, exclude call boundary events, and cap the LLM context at 24 recent conversational turns plus the optional system prompt.
- Phase 03 plan 03-07 completed on 2026-04-25: client call API wrappers, WebRTC `rayme-events` helpers, call FSM, AudioContext unlock, device fallback copy, and split mic/AI RMS metering passed RED unit contracts.
- Phase 03 plan 03-08 completed on 2026-04-25: operational call UI route, thread and character Start Call entry points, RMS visualizer, toolbar, live transcript, call row rendering, and mobile control layout passed client unit plus desktop/mobile Playwright contracts.
- Phase 03 plan 03-09 completed on 2026-04-25: full MVP call loop now carries `user_final` turns through server-owned `/turns` SSE orchestration, LLM token streaming, saved-voice TTS playback, durable speech rows, and interrupt-safe cancellation.
- Phase 03 plan 03-10 completed on 2026-04-25: full local Phase 3 automated acceptance passed across AI backend pytest, Web UI server pytest, client unit tests, desktop Chromium call specs, and mobile Chromium call spec with saved Playwright evidence.
- Phase 07 plan 07-01 completed on 2026-05-11: RED AI backend VoxCPM2 contracts now cover roster metadata, CUDA-only adapter loading, bounded synthesis options, 48 kHz output, sanitized errors, and engine-scoped degradation.
- Phase 07 plan 07-02 completed on 2026-05-11: RED Web UI server/client contracts now cover durable VoxCPM2 voice metadata, conditional Voice Lab controls, fallback roster copy, missing-transcript warning, and preview/test-play payload behavior.
- Phase 07 plan 07-03 completed on 2026-05-11: RED call-flow contracts now cover saved VoxCPM2 metadata forwarding into real playback, bounded WebRTC speak options, sanitized `call_tts_failed`, and unchanged interrupt behavior.
- Phase 07 plan 07-04 completed on 2026-05-11: RED scenario matrix contracts now require VoxCPM2 shared chunk planning, short/medium/long rows, `sample_path` evidence, F5-named promotion comparison, and deterministic Phase 07 evidence templates/verifier.
- Phase 07 plan 07-05 completed on 2026-05-11: VoxCPM2 is now metadata-visible with optional `voxcpm==2.0.2`, a CUDA-only standard Python adapter, bounded `/tts/synthesize` options, warning propagation, and the D-17 runtime-path decision artifact.
- Phase 07 plan 07-06 completed on 2026-05-11: Web UI server voice metadata now normalizes and persists bounded VoxCPM2 mode/style settings, reuses saved settings for preview/test-play, and forwards flat `voxcpm2_*` synthesis payload fields only for the VoxCPM2 engine.
- Phase 07 plan 07-07 completed on 2026-05-11: Client Voice Lab now exposes VoxCPM2 fallback roster copy, typed `metadata.engine_settings.voxcpm2` payloads, and conditional mode/style controls that preserve VoxCPM2 state while keeping non-VoxCPM2 preview payloads clean.
- Phase 07 plan 07-08 completed on 2026-05-11: Saved VoxCPM2 cloning/style metadata now reaches real call playback through existing Web UI call and AI backend WebRTC speak APIs with bounded options and sanitized call TTS failures.
- Phase 07 plan 07-09 completed on 2026-05-11: VoxCPM2 scenario matrix support now uses the shared chunk planner with generated sample paths, F5 promotion comparison fields, and stricter matrix/runtime/call-flow/decision-ready evidence verification.
- Phase 07 plan 07-10 completed on 2026-05-11: Canonical OMEN deploy now captures live VoxCPM2 CUDA runtime smoke and VRAM evidence through `scripts/deploy-omen.sh`, with `voxcpm==2.0.2`, `openbmb/VoxCPM2`, 48 kHz output, CUDA torch, model cache path, and 6334 MB peak VRAM recorded.
- Phase 07 plan 07-11 completed on 2026-05-11: Live VoxCPM2/F5 scenario matrix, generated WAV evidence, and real call-flow evidence were regenerated with BeauBrown-s2 (`voice_asset_531ca6a567db4f01a870cdfba8abae96.wav`) and passed matrix/call-flow verification.
- Phase 07 plan 07-12 completed on 2026-05-11: VoxCPM2 final outcome is `selectable_with_caveats`; manual listening judged VoxCPM2 far superior to F5, while live RayMe call TTFA still favors F5 because calls do not yet consume VoxCPM2 streaming chunks.
- Phase 08 planned on 2026-05-11: six verified plans now cover VoxCPM2 streaming adapter work, CallSession streamed playback, `/webrtc` and Web UI call semantics, repeated warm evidence tooling, OMEN dirty-checkout preflight plus canonical deployment evidence, and evidence-gated durable decision writeback.
- Phase 08 plan 08-01 completed on 2026-05-11: the AI backend now exports an internal TTS streaming chunk contract, and VoxCPM2 can yield validated timed WAV chunks from `generate_streaming` without whole-generation fallback.
- Phase 08 plan 08-02 completed on 2026-05-11: CallSession now consumes VoxCPM2 streamed chunks through the existing outbound track, emits immediate first-audio metrics separately from final playback proof fields, and preserves interrupt-safe single-turn completion.
- Phase 08 plan 08-03 completed on 2026-05-11: Existing `/webrtc/speak` and Web UI call SSE surfaces now have tests proving immediate streaming metrics, final playback proof fields, sanitized failures, and one durable AI speech row without a VoxCPM2 public route.
- Phase 08 plan 08-04 completed on 2026-05-11: Phase 8 evidence tooling now records repeated warm F5/VoxCPM2 call samples from immediate `ai_audio_started_event.tts_playback` metrics and rejects fallback, carrier-mixing, raw leaks, or slower-than-F5 medians before decision writeback.
- Phase 08 plan 08-05 completed on 2026-05-11: OMEN dirty Phase 07 evidence changes were preserved on a dedicated branch before canonical deployment, CUDA VoxCPM2 runtime/VRAM evidence was regenerated at commit `6b69aeb98434678f4aa1853953a710f8b9b0f905`, and live repeated warm call-flow evidence proved VoxCPM2 median first-audio `762.7 ms` beat F5 `948.0 ms`.
- Phase 08 completed on 2026-05-11: VoxCPM2 live call playback now consumes streaming chunks and same-run warm median first-audio beat F5; VoxCPM2 is the preferred/default live-call TTS engine.

## Current Decisions

- HTTPS strategy: `mkcert` on LAN, validated on Android Chrome via `https://192.168.1.199:8443`.
- Operating rules: see `.planning/OPERATING-NOTES.md` before backend LAN/Android HTTPS work. Key points: use real backend `OMEN-PC`/`192.168.1.199`, keep Windows artifacts under `C:\Users\pmpg\rayme\`, reuse `.local/phase1-tls/` certs, and do not create throwaway certs.
- STT default: `distil-large-v3` (`int8_float16`), WER `0.0627`.
- TTS v1 default baseline: `f5` from Phase 0; live-call default is `voxcpm2` after Phase 8 evidence.
- TTS live-call default: voxcpm2 (Phase 8 evidence: results/voxcpm2-live-streaming-call-flow.json).
- TTS v1 roster: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, and `VoxCPM2`.
- Phase 08-01 streaming adapter policy: VoxCPM2 streaming stays internal to the AI backend through `TtsAudioChunk` and `TtsStreamingAdapter`.
- Phase 08-01 no-fallback policy: `VoxCpm2TtsAdapter.stream()` calls `generate_streaming()` directly and rejects empty streams instead of falling back to `runtime.generate()`.
- Phase 08-02 call-session streaming policy: VoxCPM2 live call playback uses `adapter.stream()` only for `voxcpm2` adapters with a callable stream method.
- Phase 08-02 playback metric policy: immediate `ai_audio_started_event.tts_playback` fields stay separate from final `tts_playback_final` proof fields.
- Phase 08-02 interrupt policy: streamed chunks check cancellation before outbound enqueue while `interrupt()` keeps cancelling the active speech task and stopping the track.
- Phase 08-03 public surface policy: `/webrtc/sessions/{session_id}/speak` and Web UI `/api/calls` keep forwarding streaming playback metrics through existing response/SSE carriers; no browser-visible VoxCPM2 runtime route is added.
- Phase 08-03 durable turn policy: Web UI call turns forward exactly one nested `ai_audio_started` SSE event and persist one `ai_speech` row for the visible LLM response, not one row per audio chunk.
- Phase 08-04 evidence timing policy: live call-flow TTFA is measured from `ai_audio_started_event.tts_playback.ai_audio_started_ms`, never HTTP request duration.
- Phase 08-04 evidence carrier policy: immediate first-audio metrics and final playback proof fields must stay separate; final-only fields copied into `ai_audio_started_event.tts_playback` cannot satisfy Phase 8 evidence.
- Phase 08-04 decision gate policy: decision-ready verification requires live call-flow evidence plus a separate `voxcpm2-decision.json` artifact.
- Phase 08-05 OMEN preservation policy: dirty OMEN checkout changes are preserved on a named branch and commit before deployment; the preserved Phase 07 evidence branch is `preserve/phase08-omen-dirty-20260511T183300Z` at `2077f8ddb7d50a6cca5f1d14ff26456a781f990a`.
- Phase 08-05 live evidence result: on OMEN commit `6b69aeb98434678f4aa1853953a710f8b9b0f905`, VoxCPM2 warm live call TTFA median was `762.7 ms` versus F5 `948.0 ms`, with `voxcpm2_beats_f5: true`, streaming used, and whole-WAV fallback false.
- Phase 08-05 evidence hygiene policy: live call-flow evidence must use sanitized reference source labels and must not include absolute local reference-audio paths.
- Phase 08-06 final VoxCPM2 live-call decision: VoxCPM2 is promoted as the preferred/default live-call TTS engine, with F5 retained as fallback/comparator, after `--decision-ready` verified Phase 8 same-run live streaming evidence.
- TTS future implementation policy: keep all measured engine paths available, including `LuxTTS`, `Chatterbox Turbo`, and `TADA 1B`; use quality evaluations to choose defaults, labels, warnings, and retesting priorities.
- TTS long-form implementation: shared engine-agnostic chunk planner is now implemented in the scenario harness; raw whole-generation fallback rows are no longer the only comparison.
- TTS quality notes: Spike 003 is closed as `PASS_WITH_CAVEATS`. LuxTTS optimized is very fast but has current user-sample quality failures; Chatterbox Turbo baseline long-form is gibberish, while optimized long-form normal and seed 1337 are fine on the listened long samples; TADA Windows optimized long is acceptable while WSL is caution; XTTS/F5 long samples need sample/tuning caveats.
- Qwen3-TTS: included as an opt-in/non-default engine despite failing the acceptance gate; latency and accent-quality caveats still apply.
- FlashAttention 2: not installed on Windows, so Qwen 1.7B is ineligible for v1.
- VRAM soak: F5 `1990.2 MB`, XTTS `2104.0 MB`, Qwen3 `3010.0 MB`; all stable and within budget.
- Phase 02-01 contract policy: voice APIs use stable internal voice IDs, voice save has no preview gate, voice deletes surface `Voice unavailable`, and Settings owns save-audio/VAD/status fields.
- Phase 02-02 contract policy: AI backend health exposes STT/VAD/TTS residency, VRAM/headroom, one resident TTS engine, typed unavailable reasons without raw exception text, English-only STT defaults, VAD/manual-transcript fallback, and the full six-engine TTS registry with F5 as only default.
- Phase 02-03 contract policy: client Voice Lab tests require the full six-engine roster, optional preview before save, `Use default engine`, `Voice unavailable`, Settings audio/VAD/resident-engine controls, and live OMEN-PC acceptance only through explicit LAN env gates.
- Phase 02-04 storage policy: voice samples are stored under server-generated asset-id blob names, `voice_assets.voice_id` is nullable for pre-save uploads, and soft-deleted voices retain stable IDs for unavailable character default state.
- Phase 02-05 status bridge policy: browser-visible AI backend errors use fixed public code/message fields only; degraded but reachable backend health maps to Settings `Connected`, while `/api/ai-backend/status` exposes the detailed `status: degraded` signal through a RayMe-owned server route.
- Phase 02-06 AI backend residency policy: model health starts from a metadata-driven six-engine roster with F5 as the default resident engine; lightweight adapters keep unit tests model-download-free until real STT/TTS adapter plans wire runtime loading.
- Phase 02-06 health disclosure policy: public AI backend health uses fixed sanitized degradation reasons rather than raw adapter exceptions, tracebacks, or local model paths.
- Phase 02-07 STT policy: uploaded samples are decoded to generated temporary WAV paths, faster-whisper runs English transcribe with `condition_on_previous_text=False`, and no-speech/hallucination/failure paths preserve retry plus manual transcript fallback.
- Phase 02 GPU runtime policy: the AI backend must fail fast instead of falling
  back to CPU for production AI models. faster-whisper STT is CUDA
  `int8_float16`; F5-TTS requires CUDA PyTorch/torchaudio. OMEN deploy verifies
  the CUDA Toolkit runtime and rejects CPU-only Torch before restart.

- Execution learning policy: repeated user reports of untested handoffs must be
  converted into durable tests, saved evidence, and `.planning/LEARNINGS.md`
  entries that name the false assumption and recurrence guard.

- Session reset policy: every new context-reset session must read
  `.planning/SESSION-START.md` and run `scripts/operational-check.sh start`
  before implementation, deployment, or readiness handoff decisions.

- Phase 02-08 TTS registry policy: TTS runtime packages are locked behind the AI backend optional `tts` extra, the canonical synthesis route is `/tts/synthesize`, and per-engine adapter modules are import-gated until live runtime evidence enables real model synthesis paths.
- Phase 02-08 TTS error policy: synthesis failures return fixed public `tts_failed` details and never expose local paths, tracebacks, or adapter exception text.
- Phase 02-09 voice API policy: voice save persists metadata plus sample linkage without a preview-success gate; rename updates display name only; Web UI transcription uses the AI backend `/stt/transcribe` route with stored sample bytes.
- Phase 02-10 Settings policy: server-side Settings persists `stt_model` and `tts_default_engine` with audio/VAD defaults, uses compact AI backend status fields matching the RayMe-owned bridge, and unit tests override backend status dependencies instead of probing live LAN services.
- Phase 02-11 character default voice policy: assignments use stable voice IDs, reject missing or soft-deleted voices on write, and keep deleted references visible as `Voice unavailable` with tombstoned voice names.
- Phase 02-12 Voice Lab policy: client save is gated by sample asset, name, transcript, and selected engine only; preview success is optional and never required.
- Phase 02-12 engine-picker policy: Voice Lab renders the full six-engine roster from Settings AI backend metadata with a full-roster fallback.
- Phase 02-13 Voice Library action policy: test-play loading is row-scoped and must not disable rename/delete actions on unrelated saved voices.
- Phase 02-13 delete policy: blocked delete referents are preserved by the client delete wrapper so the UI can show readable character/chat names before `Force Delete Voice`.
- Phase 02-13 unavailable-state policy: force-deleting a referenced voice removes it from active library rows while leaving character references intact for later UI to render as `Voice unavailable`.
- Phase 02-14 Settings UI policy: browser saves include audio, VAD, STT, and TTS defaults before every endpoint test, and backend residency stays a compact endpoint-panel summary rather than a dashboard.
- Phase 02-14 navigation policy: Voice Lab is a real top-level destination; Call navigation remains out of scope for Phase 2.
- Phase 02-15 character voice UI policy: Character Editor default voice selection is route-owned state and persists only through `Save Character`.
- Phase 02-15 Gallery voice-state policy: voice names render as text-only badges, and deleted references remain visible as `Voice unavailable` rather than crashing or disappearing.
- Phase 02-16 license policy: TTS notices distinguish package/code licenses from model/weights licenses and keep default engine selection separate from commercial-use clearance.
- Phase 02-16 runtime evidence policy: runtime promotion requires one-runtime evidence first; split runtime, WSL, Docker, or subprocess paths require logged one-runtime failure evidence while preserving one public AI backend API.
- Phase 02-16 cleanup policy: Voice Lab cleanup guidance uses exact durable blob paths and protects the canonical OMEN-PC checkout plus reusable TLS material.
- Phase 02-17 signaling policy: Phase 2 exposes only `/webrtc/status` and `/webrtc/offer`; live media, captions, barge-in, and peer connection allocation remain Phase 3+ scope.
- Phase 03-01 call contract policy: AI backend call behavior is locked by RED tests before replacing the Phase 2 WebRTC skeleton.
- Phase 03-01 inbound audio policy: mic audio must finalize through VAD and STT into a typed `user_final` event, not through fabricated JSON input.
- Phase 03-01 signaling error policy: malformed WebRTC payloads must return sanitized 400/422 validation responses without traceback text.
- Phase 03-02 Web UI call API policy: call bootstrap and controls are locked by RED same-origin server tests with server-owned `call_id` to AI-backend `session_id` mapping, fixed public call error codes, and no `/turns` route until Plan 03-09.
- Phase 03-02 call prompt policy: call memory uses selected non-stale text and speech rows, excludes `call_start`/`call_end` event rows from LLM messages, and caps call context at the most recent 24 conversational turns.
- Phase 03-03 client call policy: client call implementation remains RED-gated by browser-facing tests before building the Svelte call surface.
- Phase 03-03 live call policy: live call acceptance is opt-in through `RAYME_ENABLE_LIVE_E2E` and must avoid mocked call, WebRTC, or media routes.
- Phase 03-04 AI backend session policy: call sessions are held in `app.state.call_session_manager` and exposed through session-backed `/webrtc` controls.
- Phase 03-04 WebRTC testability policy: minimal unit-test SDP uses a deterministic answer path, while real media/ICE offers allocate `aiortc` peer connections.
- Phase 03-04 call event policy: data-channel call events use the `rayme-events` label and fixed public failure codes such as `call_stt_failed`, `webrtc_offer_failed`, `call_session_not_found`, and `call_control_failed`.
- Phase 03-05 Web UI call facade policy: browser call controls use same-origin `/api/calls` routes only; the Web UI server owns `call_` IDs, maps them to server-generated `rtc_` sessions, checks backend readiness before creating active calls, and rejects foreign Origin headers.
- Phase 03-05 call prompt policy: call offers hydrate recent selected non-stale text and speech rows through `build_call_prompt_context(max_turns=24)` while excluding `call_start` and `call_end` event rows.
- Phase 03-06 prompt window policy: the Plan 03-05 `build_call_prompt_context` helper is the canonical call prompt path, and tests explicitly lock the total cap to 24 conversational turns plus the optional system message.
- Phase 03-07 client call policy: browser call transport uses typed same-origin `/api/calls` wrappers, parses only known `rayme-events` data-channel payloads, treats malformed messages as no-ops, and keeps server mute state independent from local microphone track state.
- Phase 03-07 browser media policy: AudioContext unlock uses the Start Call gesture path with a one-sample silent buffer, device picker unsupported states use fixed UI copy, and visualizer metering keeps microphone listening RMS separate from AI speaking RMS.
- Phase 03-08 call UI route policy: the approved operational call surface lives at `/call/{threadId}` and is entered from thread headers or character cards.
- Phase 03-08 call browser contract policy: local Playwright call contracts mock the canonical same-origin `/api/calls/start` route and scope live state assertions to the visualizer to avoid collisions with approved transcript copy.
- Phase 03-08 mobile layout policy: the AppShell bottom navigation remains visible on mobile call routes while sticky call controls reserve enough space and expose 44px touch targets above it.
- Phase 03-09 call loop policy: Web UI server owns call/session validation for every `user_final` turn, streams `ai_token` events, and persists final `ai_speech` from the exact visible accumulated text.
- Phase 03-09 TTS policy: call playback forwards saved voice sample audio and reference transcript to the AI backend; placeholder reference audio is invalid for generic TTS adapters.
- Phase 03-09 interrupt policy: button interrupt cancels browser SSE reading, server LLM generation, and AI backend speech playback before returning to listening.
- Phase 03-10 evidence policy: local Phase 3 call acceptance must keep mocked call specs free of skip/only/TODO gates, save browser evidence with command/timestamp/commit/pass-fail details, and leave live acceptance opt-in through `RAYME_ENABLE_LIVE_E2E`.
- Phase 07 planned on 2026-05-11: VoxCPM2 roster evaluation is ready to execute with 12 verified plans across 5 execution waves, including runtime-path decision, Wave 0 contracts, OMEN-only deployment evidence through `scripts/deploy-omen.sh`, live call-flow evidence, manual listening, and final promotion writeback.
- Phase 07-01 contract policy: VoxCPM2 must be metadata-visible before runtime promotion, must load through `voxcpm==2.0.2` and `openbmb/VoxCPM2` with `device="cuda"`, and must sanitize traceback, local path, and model-id disclosure in public synthesis failures.
- Phase 07-02 Voice Lab metadata policy: VoxCPM2 voice-level settings are contracted under `metadata.engine_settings.voxcpm2` and reused for preview, test-play, and future call playback.
- Phase 07-02 missing-transcript policy: blank transcript with VoxCPM2 transcript-guided preference must fall back to reference-only behavior with warning code `voxcpm2_reference_only_without_transcript`.
- Phase 07-03 call contract policy: VoxCPM2 preview success is insufficient; saved mode/style metadata must reach real call playback before promotion.
- Phase 07-03 call error policy: VoxCPM2 call failures must surface sanitized `call_tts_failed` behavior while preserving truthful transcript rows.
- Phase 07-03 validation policy: VoxCPM2 call option validation must be bounded and must not echo traceback, local path, or model-cache details.
- Phase 07-04 evidence policy: VoxCPM2 promotion evidence uses `sample_path` as the future matrix/audio link field; the current `output_wav`-only harness behavior remains an intentional RED gap.
- Phase 07-04 verifier policy: Phase 07 evidence verification starts with contract-only checks and reserves matrix, call-flow, and decision-ready modes for later live evidence plans.
- Phase 07-05 runtime path policy: VoxCPM2 initial backend implementation uses the standard Python `generate` API behind the existing RayMe AI backend API; streaming and serving variants remain evidence-gated.
- Phase 07-05 metadata policy: VoxCPM2 is visible as a candidate with RTX 3060 evidence pending, and F5 remains the only default engine.
- Phase 07-05 runtime guard policy: VoxCPM2 loading requires CUDA through `require_torch_cuda_runtime("VoxCPM2")` and `device="cuda"`.
- Phase 07-06 Web UI metadata default policy: VoxCPM2 voice metadata defaults to `reference_only`, empty `style_prompt`, `cfg_value` 2.0, `inference_timesteps` 10, `normalize` false, and `denoise` false.
- Phase 07-06 synthesis bridge policy: Web UI server forwards VoxCPM2 settings to the AI backend only when the target engine is `voxcpm2`; other engines omit all `voxcpm2_*` payload fields even if saved metadata exists.
- Phase 07-07 client metadata policy: browser save/preview typing uses `metadata.engine_settings.voxcpm2`; preview includes VoxCPM2 metadata only when VoxCPM2 is selected.
- Phase 07-07 Voice Lab UI policy: VoxCPM2 settings are route-owned state preserved across engine switches, but controls render only for `selectedEngine === "voxcpm2"`.
- Phase 07-07 client default policy: VoxCPM2 controls mirror server defaults from Plan 07-06: `reference_only`, empty style, cfg 2.0, 10 timesteps, normalize false, and denoise false.
- Phase 07-08 call API policy: Real call playback reuses saved VoxCPM2 settings through the existing RayMe call API; no VoxCPM2-specific browser route is added.
- Phase 07-08 validation policy: AI backend call speak validation uses the same VoxCPM2 bounds as transient synthesis and does not echo rejected input.
- Phase 07-08 adapter policy: Legacy call-specific TTS adapters remain compatible unless they explicitly accept VoxCPM2 option kwargs.
- Phase 07-09 scenario matrix policy: VoxCPM2 benchmark rows use the standard Python CUDA path with runtime-reported sample rates and the shared RayMe chunk planner.
- Phase 07-09 streaming evidence policy: VoxCPM2 `generate_streaming` collection rows are benchmark-only until call playback consumes live chunks.
- Phase 07-09 evidence readiness policy: decision-ready VoxCPM2 evidence requires matrix, runtime, call-flow, and manual quality checks.
- Phase 07-10 OMEN deploy policy: VoxCPM2 runtime evidence must stay inside `scripts/deploy-omen.sh`; no alternate OMEN deployment scripts, launcher files, or manual scheduled-task edits are allowed.
- Phase 07-10 VoxCPM2 loader policy: live `voxcpm==2.0.2` rejects the documented `device="cuda"` loader kwarg, so RayMe loads with the actual package API and verifies CUDA residency after model load.
- Phase 07-10 OMEN TTS sync policy: optional TTS sync on OMEN must target Python 3.11 and repair CUDA PyTorch wheels after `uv sync`, because the default Windows sync path installs CPU torch.
- Phase 07 final VoxCPM2 decision: VoxCPM2 was selectable with caveats. Quality was preferred over F5, runtime/call-flow/VRAM gates passed, and the remaining live streaming playback caveat is now closed by the Phase 8 VoxCPM2 live-call default decision.

## Evidence

- Human-readable synthesis: `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
- Machine-readable roll-up: `.planning/phases/00-measurement-gate/results/phase0_summary.json`
- Runtime matrix: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix.json`
- Warm-model scenario matrix and listening samples: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`, `.planning/phases/00-measurement-gate/results/tts_scenario_audio/`

## Accumulated Context

### Roadmap Evolution

- Plan 00-07.1 inserted into `00-measurement-gate`: benchmark TTS attention/optimization backends per engine before final writeback.
- Plan 00-07.2 completed: benchmarked native Windows vs WSL runtime permutations before Phase 0 writeback.
- 2026-04-23 TTS follow-up: shared chunking has been implemented and the Windows plus WSL matrix reran. Manual listening is partially scored but sufficient to close the spike with caveats: keep all engines, avoid raw latency-only defaults, tune F5 long-form stretch/duration, retest LuxTTS with better references, and keep Chatterbox optimized long-form while avoiding baseline/raw long-form.
- Phase 01.1 inserted after Phase 1: UI acceptance and regression test hardening. Reason: Phase 1 live LAN/Android acceptance exposed UI workflows that existed but were not adequately agent-tested before product-owner testing. Future manual user testing must be treated as acceptance after agent-run API/browser/deployed verification, not first-line QA.
- Phase 7 added: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations.
- Phase 8 added: Wire VoxCPM2 streaming chunks into live RayMe call playback.

### Phase 0 Completion Notes

- Android HTTPS passed with mkcert after installing the root CA on the phone.
- The checked-in measurement artifacts were captured directly on the RTX 3060 target hardware.
- Phase 1 should start from the frozen decisions in PROJECT.md rather than re-opening model-selection debates.

## Session Continuity

Last session: 2026-05-11T19:07:10.056Z
Stopped at: Completed 08-05-PLAN.md
Resume file: None

**Planned Phase:** 08 (Wire VoxCPM2 streaming chunks into live RayMe call playback) — 6 verified plans, ready to execute — 2026-05-11T14:13:40.567Z
