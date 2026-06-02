---
quick_task: 260602-4xz
status: complete
objective: "Repair the OMEN-PC Desktop launcher so it is quiet, does not open the browser automatically, and does not leave blank service command prompts."
completed_at: "2026-06-02T03:38:21Z"
commits:
  - "3dffff8 fix(quick-260602-4xz): quiet OMEN desktop launcher"
key_files:
  - scripts/start-rayme-omen.ps1
  - scripts/deploy-omen.sh
  - web-ui/server/docs/HTTPS-LAN.md
---

# Quick Task 260602-4xz Summary

The OMEN-PC Desktop launcher was repaired to behave like a quiet service
starter instead of a suspicious-looking command transcript. It no longer opens
the RayMe page automatically, no longer prints raw `schtasks` success output
when clicked, and the deployed service launchers now use `pythonw.exe` so the
AI/Web service processes do not own visible blank command-prompt windows.

## Changes

- Added `-Quiet` and `-OpenBrowser` switches to
  `scripts/start-rayme-omen.ps1`.
- Changed the Desktop shortcut created by `scripts/deploy-omen.sh` to pass
  `-Quiet` and removed `-ExecutionPolicy Bypass` from the shortcut arguments.
- Suppressed raw `schtasks.exe /Run` output in the click-time launcher unless a
  scheduled task start fails.
- Made browser launch opt-in only via `-OpenBrowser`; the Desktop shortcut does
  not pass it.
- Changed the canonical deployed `start-ai-backend.cmd` and `start-web-ui.cmd`
  contents to run their server scripts through `pythonw.exe`.
- Updated `web-ui/server/docs/HTTPS-LAN.md` to document that the Desktop
  shortcut starts services only and the user opens the browser manually.

## Verification

- `bash -n scripts/deploy-omen.sh` - PASS.
- Windows PowerShell parser over SSH against `scripts/start-rayme-omen.ps1` -
  PASS (`parse-ok` locally before deploy; `errors.Count = 0` after deploy).
- OMEN pre-check: AI and Web venvs both include `pythonw.exe` - PASS.
- OMEN pre-check: `pythonw.exe` preserves redirected stdout logging - PASS.
- `OMEN_SSH_ALIAS=rayme-pmpg scripts/deploy-omen.sh` - PASS, deployed
  `3dffff8b8513ccfa160fd7e9274a35015b44f3ea`.
- Post-deploy shortcut verification - PASS:
  - Target: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
  - Arguments: `-NoProfile -File "C:\Users\pmpg\rayme\RayMe\scripts\start-rayme-omen.ps1" -Quiet`
  - Description: `Start RayMe services without opening a browser`
  - No `ExecutionPolicy Bypass` in the shortcut arguments.
- Quiet click-path simulation - PASS:
  - Ran `start-rayme-omen.ps1 -Quiet` over SSH while services were up.
  - The launcher emitted no output; only the test sentinel printed.
- Post-deploy service process verification - PASS:
  - Port `9443` owner process: `pythonw`
  - Port `8443` owner process: `pythonw`
- Live health snapshot after deploy - PASS for deploy gate:
  - AI `/health`: `stt_ready=true`, `vad_ready=true`, `resident_tts_engine=f5`, `status=degraded`.
  - Web `/api/settings`: AI backend reachable, `endpoint_status=degraded`, `tts_default_engine=voxcpm2`.

## Deviations from Plan

None.

## Threat Notes

- The repair stayed inside `scripts/deploy-omen.sh` and repo-owned scripts.
- Scheduled tasks still point only to `C:\Users\pmpg\rayme\start-ai-backend.cmd`
  and `C:\Users\pmpg\rayme\start-web-ui.cmd`.
- No ad-hoc OMEN-side deployment scripts were created.
- No call, TTS, STT, VAD, WebRTC, reconnect, or call UI code was changed.

## Known Stubs

None.
