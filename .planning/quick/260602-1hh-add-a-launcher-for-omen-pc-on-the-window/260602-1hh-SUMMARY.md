---
quick_task: 260602-1hh
status: complete
objective: "Add a Windows Desktop launcher on OMEN-PC to start/open RayMe through the canonical scheduled-task runtime."
completed_at: "2026-06-02T01:13:25Z"
commits:
  - "a30054f feat(quick-260602-1hh): add OMEN desktop launcher"
key_files:
  - scripts/start-rayme-omen.ps1
  - scripts/deploy-omen.sh
  - web-ui/server/docs/HTTPS-LAN.md
---

# Quick Task 260602-1hh Summary

OMEN-PC now gets a Windows Desktop shortcut named `Run RayMe.lnk` during the
canonical `scripts/deploy-omen.sh` flow. The shortcut points to the repo-owned
`C:\Users\pmpg\rayme\RayMe\scripts\start-rayme-omen.ps1` launcher, which starts
the existing `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks only when
their listeners are not already running, then opens `https://192.168.1.199:8443`.

## Changes

- Added `scripts/start-rayme-omen.ps1`, a Windows PowerShell launcher that
  checks the canonical OMEN checkout, verifies the two scheduled tasks exist,
  starts missing AI/Web listeners, and opens the RayMe LAN URL.
- Extended `scripts/deploy-omen.sh` to create or update
  `C:\Users\pmpg\Desktop\Run RayMe.lnk` via `WScript.Shell`.
- Updated `web-ui/server/docs/HTTPS-LAN.md` to document the Desktop shortcut as
  a convenience entry point, not a replacement deployment path.

## Verification

- `bash -n scripts/deploy-omen.sh` - PASS.
- `rg -n "start-rayme-omen|Run RayMe|CreateShortcut|RayMePhase1AI|RayMePhase1Web" scripts/deploy-omen.sh scripts/start-rayme-omen.ps1 web-ui/server/docs/HTTPS-LAN.md` - PASS.
- Windows PowerShell parser over SSH against `scripts/start-rayme-omen.ps1` - PASS (`parse-ok` before deployment; `errors.Count = 0` after deployment).
- `OMEN_SSH_ALIAS=rayme-pmpg scripts/deploy-omen.sh` - PASS, deployed `a30054fcc0d67cfca4df1b1df0ab2557326a04c8`.
- Post-deploy shortcut verification - PASS:
  - Path: `C:\Users\pmpg\Desktop\Run RayMe.lnk`
  - Target: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
  - Arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\pmpg\rayme\RayMe\scripts\start-rayme-omen.ps1"`
  - Working directory: `C:\Users\pmpg\rayme\RayMe`
- Post-deploy scheduled-task verification - PASS:
  - `RayMePhase1AI` task target remains `C:\Users\pmpg\rayme\start-ai-backend.cmd`.
  - `RayMePhase1Web` task target remains `C:\Users\pmpg\rayme\start-web-ui.cmd`.
- Live health snapshot after deploy - PASS for deploy gate:
  - AI `/health`: `stt_ready=true`, `vad_ready=true`, `resident_tts_engine=f5`, `status=degraded`.
  - Web `/api/settings`: AI backend reachable, `endpoint_status=degraded`, `tts_default_engine=voxcpm2`.

## Deviations from Plan

None.

## Threat Notes

- No scheduled-task definitions were created, deleted, or modified outside
  `scripts/deploy-omen.sh`.
- No new launcher files were written under `C:\Users\pmpg\rayme\` beyond the
  two existing canonical `.cmd` launchers written by the deploy script.
- The Desktop shortcut points into the Git checkout rather than embedding an
  ad-hoc remote script.
- No call, TTS, STT, VAD, WebRTC, reconnect, or call UI behavior was changed.

## Known Stubs

None.
