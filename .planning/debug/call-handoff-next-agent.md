---
status: investigating
created: 2026-04-26T00:00:00Z
updated: 2026-04-26T00:25:00Z
owner: next-agent
---

# Next Agent Handoff: Make Calls Actually Work

## User Goal

The user does not want a cosmetic failure path. The app must complete a real
voice call path:

1. Android Chrome microphone permission is granted.
2. Browser creates a real WebRTC offer.
3. Web UI forwards that offer to the AI backend.
4. AI backend creates a real WebRTC answer.
5. Browser receives backend audio.
6. User speech reaches STT.
7. Final transcript drives the LLM turn.
8. TTS audio is generated.
9. TTS audio is sent back over WebRTC and plays in the browser.

Do not claim this is working until this complete path is proven on the live
OMEN deployment or with equivalent real-device evidence.

## Current State

- Repo: `/d/Pedro/Repos/Program/RayMe`
- Branch: `main`
- Current local HEAD: `27750e9 fix: surface real WebRTC offer failures`
- Known deployed commit from previous pass: `6d817dd fix: wire real call audio path`
- There may be newer local commits than the deployed OMEN checkout. Verify
  deployment state before testing.

## Critical Facts

- Android client IP seen in OMEN logs: `192.168.1.253`
- Web URL: `https://192.168.1.199:8443`
- AI URL: `https://192.168.1.199:9443`
- SSH alias that must work: `rayme-pmpg`
- Deploy command: `scripts/deploy-omen.sh`
- The deploy script was changed to restore the SSH alias before using it. Do
  not waste time on manual SSH alias work unless that regression is back.

## What Went Wrong Already

- Earlier changes alternated between:
  - failing during offer setup,
  - hiding the offer failure and leaving the UI looking like it was listening,
  - failing fast but still not making the call work.
- The user explicitly rejects fake or synthetic success paths.
- The existing debug file was previously marked resolved too early. It is now
  reopened as `investigating`.

## Evidence From The Latest Android Retest

The user manually tested on Android after the real-audio-path work and reported:

- The call now fails fast.
- It still does not work.
- It still does not tell the exact actionable reason.

OMEN web logs from that manual test showed Android reaching the web facade:

- `POST /api/calls/start` returned `201 Created`
- `POST /api/calls/{call_id}/offer` returned `502 Bad Gateway`
- `POST /api/calls/{call_id}/end` returned `200 OK`

AI backend access logs did not show a matching `POST /webrtc/offer` line for
those Android `502` failures in the inspected tail. That points to one of these
boundaries:

- Web UI facade failed before forwarding to AI.
- Web UI facade timed out while AI had not yet logged a completed response.
- Logging did not capture the relevant AI line.
- AI backend rejected or hung during WebRTC offer processing before a visible
  access log was emitted.

Do not assume microphone permission is still the blocker; Android already gets
past call creation and posts the offer.

## Production Synthetic Paths Fixed In Current Worktree

These production web facade paths were found after the earlier handoff and have
now been replaced with explicit public-safe errors:

- Missing `create_webrtc_offer` no longer returns `answer: None`.
- Missing `mute_call` no longer returns local mute success.
- Missing `interrupt_call` no longer returns local interrupt success.
- Missing `end_call` no longer returns local end success.
- Missing `speak_call` no longer returns `ai_done`.

The replacement error code is `call_backend_client_misconfigured`. Regression
coverage was added in `web-ui/server/tests/test_calls.py`, and the production
synthetic-path guard was strengthened to reject `answer: None`.

## Important Files

- `web-ui/server/app/api/calls.py`
- `web-ui/server/app/domain/ai_backend_client.py`
- `web-ui/client/src/routes/call/[threadId]/+page.svelte`
- `web-ui/client/src/lib/api/calls.ts`
- `ai-backend/app/api/webrtc.py`
- `ai-backend/app/call/session.py`
- `ai-backend/app/call/tracks.py`
- `scripts/deploy-omen.sh`
- `.planning/debug/android-call-offer-502.md`
- `.planning/debug/call-working-incident.md`

## Recommended First Debug Actions

1. Verify current deployment commit:
   `ssh rayme-pmpg 'cd C:\Users\pmpg\rayme\RayMe; git rev-parse --short HEAD'`
2. If OMEN is behind local HEAD, push and deploy:
   `git push origin main && scripts/deploy-omen.sh`
3. Tail both web and AI logs while reproducing Android:
   `ssh rayme-pmpg 'Get-Content C:\Users\pmpg\rayme\logs\web-ui.hidden.out.log -Tail 120'`
   `ssh rayme-pmpg 'Get-Content C:\Users\pmpg\rayme\logs\ai-backend.hidden.out.log -Tail 120'`
4. Add structured logging around `create_call_offer` and
   `create_webrtc_offer_answer` if logs still do not reveal the failing
   boundary.
5. Make the Android offer path succeed, not merely fail with a clearer message.
   The success criterion is actual audible AI response after user speech.

## Verification Commands Already Used

- `uv run --project ai-backend pytest ai-backend/tests -q`
- `uv run --project web-ui/server pytest web-ui/server/tests -q`
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`
- `uv run --project ai-backend pytest ai-backend/tests/test_no_synthetic_production_paths.py -q`
- `npm --prefix web-ui/client run check`
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1`

These are not enough by themselves. They did not prove Android live WebRTC,
STT, LLM, TTS, and browser playback.

## Command For Next Agent

Start from the repo root:

```bash
cd /d/Pedro/Repos/Program/RayMe && codex '$gsd-debug continue android-call-offer-502. Read .planning/debug/call-handoff-next-agent.md first. Do not implement synthetic or fake success paths. Make the Android call work end to end, verify on OMEN, and remove production fallback behavior that pretends backend call actions succeeded.'
```
