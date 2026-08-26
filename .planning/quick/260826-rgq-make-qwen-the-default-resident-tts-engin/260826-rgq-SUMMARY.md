---
quick_task: 260826-rgq
status: complete
date: 2026-08-26
implementation_commit: ca80da3050a6362eb50d0f9b828f956692479526
deployed_target: OMEN-PC (192.168.1.199)
---

# Quick Summary: Qwen-Resident OMEN Startup And Desktop Launcher

## Result

Canonical OMEN startup now explicitly selects `qwen3_1_7b` as the resident TTS
engine. Both deploy-time health gates and the Web UI bridge reject startup if
the resident engine is not Qwen.

The Desktop `Run RayMe.lnk` path was repaired to carry the same runtime
identity as the scheduled services: pinned Qwen model directory/revision,
deployed commit, rotated service token, private CA bundle, CUDA path, and Qwen
startup-engine selection. Deploy now reads the shortcut back and fails if its
target, arguments, working directory, normal window style, or visible-console
description drift.

Generic/local AI startup still falls back to F5 when the OMEN-specific
`RAYME_TTS_DEFAULT_ENGINE` environment value is absent. The existing persisted
OMEN Web setting was already `qwen3_1_7b`.

## Verification

- Focused startup/deploy/launcher/live-stream suite: `57 passed`.
- Full AI backend suite: `436 passed` with 4 existing dependency/deprecation
  warnings.
- Web settings suite: `37 passed`.
- Shell syntax, Windows PowerShell parser, and `git diff --check`: pass.
- Canonical deployment: pass at exact commit
  `ca80da3050a6362eb50d0f9b828f956692479526`.
- RTX 3060: CUDA Torch `2.10.0+cu126`; one-hot Qwen residency; `4286.0 MiB`
  Qwen Torch reservation; `5415.7 MiB` reported headroom.
- Direct WebRTC readiness: ready, live media ready, exact deployed commit.
- Web-to-AI readiness: ready and authenticated.
- Web root: HTTP 200.

## Desktop Lifecycle Proof

The deployed shortcut metadata passed read-back verification. Because OMEN had
no logged-in Explorer/Desktop session, the shortcut's exact PowerShell target
and arguments were run through a foreground TTY. It displayed the RayMe
Console title, keep-open/close-to-stop guidance, `[AI]`/`[WEB]` logs, LAN URL,
and `Ready`. Closing it stopped both child services and closed ports 9443/8443.
The canonical scheduled tasks were then restarted and RayMe was left running
with Qwen resident.

Full saved evidence:
`260826-rgq-LIVE-EVIDENCE.md`.

## Files Changed

- `ai-backend/app/config.py`
- `ai-backend/tests/test_model_manager.py`
- `ai-backend/tests/test_omen_deploy_contract.py`
- `ai-backend/tests/test_omen_desktop_launcher_contract.py`
- `scripts/deploy-omen.sh`
- `scripts/start-rayme-omen.ps1`
- `README.md`

No temporary project/runtime directory was created by this task.
