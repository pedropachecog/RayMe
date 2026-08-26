---
quick_task: 260826-rgq
captured_at: 2026-08-26T20:02:30Z
commit: ca80da3050a6362eb50d0f9b828f956692479526
target: OMEN-PC (192.168.1.199)
result: pass
---

# Qwen-Resident OMEN And Desktop Launcher Evidence

## Local Verification

- RED contracts failed before implementation for the missing
  `RAYME_TTS_DEFAULT_ENGINE` override, missing Desktop launcher Qwen/service
  identity, and missing deploy-time shortcut attestation.
- Focused model-manager, health, deploy, Desktop launcher, and live streaming
  invariant suite: `57 passed`.
- Full AI backend suite:
  `uv run --project ai-backend pytest ai-backend/tests -q` ->
  `436 passed, 4 dependency/deprecation warnings`.
- Web settings bridge suite:
  `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q`
  -> `37 passed`.
- `bash -n scripts/deploy-omen.sh` -> pass.
- OMEN Windows PowerShell parser over `scripts/start-rayme-omen.ps1` ->
  `parse-ok`.
- `git diff --check` -> pass.

The focused invariant set included:

- `test_voxcpm2_slow_stream_starts_playback_before_stream_completion`
- `test_qwen_slow_stream_starts_playback_before_stream_completion`
- `test_interrupt_after_first_voxcpm2_stream_chunk_discards_late_chunks`

No call playback, streaming, buffering, VAD, reconnect, or interrupt source was
changed.

## Canonical Deployment

`scripts/deploy-omen.sh` deployed exact commit
`ca80da3050a6362eb50d0f9b828f956692479526` and passed:

- pinned Faster Qwen3-TTS runtime/model provisioning,
- CUDA Torch `2.10.0+cu126` and torchaudio `2.10.0+cu126`,
- NVIDIA GeForce RTX 3060 runtime check,
- database migration,
- Web client production build,
- canonical scheduled-task recreation,
- Desktop shortcut write plus read-back attestation,
- AI/Web listeners on `9443`/`8443`,
- direct AI health and Web bridge Qwen-residency gates.

Post-deploy health reported:

- `resident_tts_engine=qwen3_1_7b`
- resident engine list exactly `[qwen3_1_7b]`
- `loading_engine=null`
- `stt_ready=true`
- `vad_ready=true`
- Qwen Torch reserved VRAM `4286.0 MiB`
- total used VRAM `5584.3 MiB`
- VRAM headroom `5415.7 MiB`
- WebRTC `status=ready`, `live_call_ready=true`,
  `media_transport_ready=true`
- Web-to-AI readiness `status=ready`, `authenticated=true`
- Web root HTTP `200`

The overall AI health classification remains `degraded` only because
non-implemented optional roster engines are truthfully marked unavailable.

## Desktop Shortcut Contract

Deployed `C:\Users\pmpg\Desktop\Run RayMe.lnk` read back as:

- target:
  `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- arguments:
  `-NoProfile -File "C:\Users\pmpg\rayme\RayMe\scripts\start-rayme-omen.ps1"`
- working directory: `C:\Users\pmpg\rayme\RayMe`
- window style: `1` (normal/visible)
- description:
  `Run RayMe with visible AI and Web logs; close the console to stop`

There was no logged-in Explorer/Desktop session on OMEN during verification,
so the exact shortcut target and arguments were executed through a foreground
TTY. That run proved the same command path:

- set the console title to `RayMe Console`,
- printed keep-open and close-to-stop guidance,
- printed `https://192.168.1.199:8443`,
- stopped prior scheduled listeners so the console owned RayMe,
- streamed `[AI]` and `[WEB]` startup logs,
- reached `AI backend is listening`, `Web UI is listening`, and `Ready`,
- served authenticated AI/Web health with one-hot Qwen residency.

Sending Ctrl+C to close the foreground console printed both child PIDs being
stopped and `RayMe stopped`. Independent probes then proved ports `9443` and
`8443` were both closed and both scheduled tasks had returned to `Ready`.

## Restored Running State

The existing canonical tasks were started again without recreating or editing
them. Final state:

- `RayMePhase1AI`: `Running`, action
  `C:\Users\pmpg\rayme\start-ai-backend.cmd`
- `RayMePhase1Web`: `Running`, action
  `C:\Users\pmpg\rayme\start-web-ui.cmd`
- AI resident TTS: `qwen3_1_7b`
- Web HTTP: `200`
- authenticated Web-to-AI readiness: `ready`
- deployed commit: `ca80da3050a6362eb50d0f9b828f956692479526`
