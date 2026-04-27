---
status: fixing
created: 2026-04-27T03:30:00Z
updated: 2026-04-27T20:00:00Z
---

# Debug Session: Android Call Speaking No Audio

## Current Focus

reasoning_checkpoint:
  hypothesis: The SSE connection on Android Chrome is interrupted during TTS synthesis (10-15s) because the server yields no SSE data during `await _speak_call()`. FastAPI's StreamingResponse closes the HTTP connection when no data flows for the server's idle timeout, which cancels the SSE generator task. This in-flight CancelledError propagates to `_synthesize_speech` -> `run_in_executor` -> F5-TTS, aborting the TTS synthesis. No audio is enqueued, so the browser hears only silence keepalive (speakingRms=0.04).

  confirming_evidence:
    - OMEN logs show `asyncio.exceptions.CancelledError` at `_synthesize_speech` line 667
    - WebRTC disconnects and reconnects during TTS (browser logs show ice=disconnected -> connected cycles)
    - speak_call returns HTTP 500 (CancelledError passes `except Exception` since it inherits BaseException)
    - TTS succeeds later (wav_bytes logged) — the issue is timing, not F5-TTS itself
    - calls.py SSE generator yields zero data during `await _speak_call()` — idle connection
    - The 200 OK for `/turns` confirms the SSE generator eventually completes

  falsification_test: Add SSE keepalive ping during `_speak_call()`. If TTS stops being cancelled, the hypothesis is confirmed.

  fix_rationale: SSE keepalive yields periodic comment-only SSE events during `_speak_call()`, preventing the HTTP idle timeout. CancelledError handling in `speak_session` catches it explicitly (returns 502 instead of 500).

  blind_spots:
    - If the cancellation source is not the SSE idle timeout but something else (e.g., browser closing and reopening the SSE connection)
    - If the browser discards WebRTC connection during SSE gap despite silence keepalive

### Problem A: No AI Audio (Post-8d20fd2)

hypothesis: SSE idle timeout during `_speak_call()` causes the FastAPI StreamingResponse to close, cancelling the SSE generator task. CancelledError propagates to `_synthesize_speech` -> `run_in_executor`, aborting TTS synthesis.

test: Add SSE keepalive during _speak_call(). If TTS stops being cancelled, hypothesis confirmed.

expecting: TTS completes, audio is enqueued, browser hears audio.

next_action: Implement SSE keepalive + CancelledError handling + deploy.

### Problem B: Silence Transcribed as "Thank You"

hypothesis: The client's microphone track stays enabled during AI thinking/speaking. Ambient noise flows through VAD -> STT -> Whisper hallucinates "thank you" from silence. The server-side `handle_inbound_audio_frame` only drops frames when `muted=True` or state in {"ended","failed"}, NOT when state is "speaking" or "thinking". During LLM generation, state is "listening" (reset after user_final), so audio accumulates.

confirming_evidence:
  - session.py line 109: `if self.muted or self.state in {"ended", "failed"}` — does NOT include "speaking" or "thinking"
  - session.py line 241: `self.state = "listening"` after finalize_user_turn — state resets to listening during LLM gen
  - Client +page.svelte never disables mic tracks during AI turn
  - No `set_muted` call made by web UI before LLM generation

falsification_test: If we add "speaking" to the drop states and disable client mic during AI turn, silence should no longer be transcribed.

fix_rationale: Dual defense — client disables mic track on thinking/speaking (primary), server drops frames during speaking (safety net).

blind_spots:
  - If the Whisper hallucination is from very short silence bursts that pass VAD before the AI turn starts
  - If the VAD threshold is too low, letting room noise through even when user isn't speaking

## Symptoms

expected: AI audio plays during 'speaking' state on Android Chrome
actual: UI reaches 'speaking', shows AI text, but no audio is heard. State transitions to 'listening'.
errors:
  - CancelledError during TTS synthesis (AI backend logs)
  - tts.enqueue after data channel closed
  - track.send.progress queue_size=0 buffer_size=0
  - speak_call.background_failed
reproduction: Start call on Android Chrome, speak, wait for AI response. Text appears but no audio.
started: After commit 8244cb0 (SSE unblock fix)

## Problem 1: Ad-Hoc PS1 Scripts on OMEN

**Created by:** A previous Claude session on 4/24/2026 ~15:22

**Location:** `C:\Users\pmpg\rayme\` on OMEN (outside the git repo)

**The 3 files:**

| File | What it does |
|------|-------------|
| `reconfigure-hidden-runtime.ps1` | Creates the other 2 scripts, kills existing processes, recreates scheduled tasks `RayMePhase1AI` / `RayMePhase1Web` to point to `.ps1` instead of `.cmd` |
| `start-ai-backend-hidden.ps1` | Starts AI backend via `Start-Process -WindowStyle Hidden` with hardcoded paths |
| `start-web-ui-hidden.ps1` | Starts web UI via `Start-Process -WindowStyle Hidden` with hardcoded env vars |

**Content of `start-ai-backend-hidden.ps1`:**
```powershell
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\pmpg\rayme\RayMe'
$logs = 'C:\Users\pmpg\rayme\logs'
Start-Process -WindowStyle Hidden `
  -WorkingDirectory $repo `
  -FilePath 'C:\Users\pmpg\rayme\RayMe\ai-backend\.venv\Scripts\python.exe' `
  -ArgumentList 'ai-backend\scripts\run_https.py --host 192.168.1.199 --port 9443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem' `
  -RedirectStandardOutput "$logs\ai-backend.hidden.out.log" `
  -RedirectStandardError "$logs\ai-backend.hidden.err.log"
```

**Content of `start-web-ui-hidden.ps1`:**
```powershell
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\pmpg\rayme\RayMe'
$logs = 'C:\Users\pmpg\rayme\logs'
$env:RAYME_WEB_BIND_HOST = '192.168.1.199'
$env:RAYME_WEB_PORT = '8443'
$env:RAYME_WEB_PUBLIC_URL = 'https://192.168.1.199:8443'
$env:RAYME_AI_BACKEND_BASE_URL = 'https://192.168.1.199:9443'
$env:RAYME_DATABASE_URL = 'sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3'
$env:RAYME_ALLOWED_ORIGINS = 'https://192.168.1.199:8443,https://rayme.local:8443'
Start-Process -WindowStyle Hidden `
  -WorkingDirectory $repo `
  -FilePath 'C:\Users\pmpg\rayme\RayMe\web-ui\server\.venv\Scripts\python.exe' `
  -ArgumentList 'web-ui\server\scripts\run_dev_https.py --host 192.168.1.199 --port 8443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem' `
  -RedirectStandardOutput "$logs\web-ui.hidden.out.log" `
  -RedirectStandardError "$logs\web-ui.hidden.err.log"
```

**Content of `reconfigure-hidden-runtime.ps1`:**
```powershell
$ErrorActionPreference = 'Continue'
$root = 'C:\Users\pmpg\rayme'
$repo = 'C:\Users\pmpg\rayme\RayMe'
$logs = 'C:\Users\pmpg\rayme\logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# Creates the two .ps1 scripts above via Set-Content
# Then kills existing processes matching run_https.py / run_dev_https.py
# Then deletes and recreates scheduled tasks:
#   schtasks /Delete /TN RayMePhase1AI /F
#   schtasks /Delete /TN RayMePhase1Web /F
#   schtasks /Create /TN RayMePhase1AI /TR "powershell.exe -NoProfile ... -File C:\Users\pmpg\rayme\start-ai-backend-hidden.ps1" /SC ONCE /ST 23:59 /F
#   schtasks /Create /TN RayMePhase1Web /TR "powershell.exe -NoProfile ... -File C:\Users\pmpg\rayme\start-web-ui-hidden.ps1" /SC ONCE /ST 23:59 /F
#   schtasks /Run /TN RayMePhase1AI
#   schtasks /Run /TN RayMePhase1Web
```

**Why this broke things:**

The proper `scripts/deploy-omen.sh` writes `start-ai-backend.cmd` (a `.cmd` file) and uses `schtasks` to start services. The PS1 scripts OVERRODE the scheduled tasks to point to `.ps1` files. Now:
- `deploy-omen.sh` writes `.cmd` but scheduled tasks run `.ps1`
- The scheduled tasks are one-shot (ONCE at 23:59) — they ran once and won't auto-restart
- Last ran 4/26/2026 23:43 — processes crashed and never restarted
- The app is completely DOWN

**Also check:** `.local/phase1-tls/reconfigure-hidden-runtime.ps1` exists in the local repo. Check if it was committed to git or is only in `.gitignore`. It should NOT be tracked.

## Problem 2: Android Call Debugging

**Current state:**
- Local HEAD: 02bca89 (pushed to origin)
- OMEN deployed: bc60630 (behind — needs deploy)
- Fixes 8244cb0 + 02bca89 are pushed but NOT deployed because app is down

**Fixes pending deployment:**
1. `8244cb0` — SSE unblock (yield ai_done before TTS) + VAD max turn safety net
2. `02bca89` — Data channel ping sent immediately on open (was delayed 0.5s)

**Known issues from prior investigation:**
- VAD/STT works (turns 1 & 2 completed successfully in logs)
- `user_final` events sent via data channel
- Browser received events, submitted `/turns`
- SSE generator blocked on TTS (5-15s) before yielding `ai_done` — browser stuck in "speaking"
- VAD early-returned when `speech_detected=False`, bypassing max turn duration
- DTLS ConnectionError — peer connection died during TTS blocking gap
- Outbound track logs show `queue_size=0, buffer_size=0` — TTS audio never queued

**What the 8244cb0 fix caused:**
- First call: stuck in listening, never transcribed
- Second call: "RayMe could not start this call" error
- Root cause: 8244cb0 was NOT deployed (OMEN was at bc60630, "ahead 1")
- The regressions may have been from the data channel dying, not the code changes

## What to Do

### Step 1: Clean up ad-hoc PS1 scripts on OMEN

Via `ssh rayme-pmpg` (SSH works):

```powershell
# Delete the 3 ad-hoc scripts
Remove-Item C:\Users\pmpg\rayme\start-ai-backend-hidden.ps1 -Force
Remove-Item C:\Users\pmpg\rayme\start-web-ui-hidden.ps1 -Force
Remove-Item C:\Users\pmpg\rayme\reconfigure-hidden-runtime.ps1 -Force

# Delete the hijacked scheduled tasks
schtasks /Delete /TN RayMePhase1AI /F
schtasks /Delete /TN RayMePhase1Web /F
```

### Step 2: Restore proper deployment

From WSL/Linux repo root:
```bash
cd /d/Pedro/Repos/Program/RayMe
git push origin main
scripts/deploy-omen.sh
```

This will:
- Write proper `start-ai-backend.cmd`
- Build web client
- Kill existing processes on ports 8443/9443
- Recreate scheduled tasks pointing to `.cmd`
- Start services
- Verify health endpoints

### Step 3: Verify services are up

```bash
ssh rayme-pmpg 'powershell -NoProfile -Command "curl.exe -k --max-time 5 https://192.168.1.199:9443/health"'
ssh rayme-pmpg 'powershell -NoProfile -Command "curl.exe -k --max-time 5 https://192.168.1.199:8443/api/settings"'
```

### Step 4: Test Android call

1. Open `https://192.168.1.199:8443` on Android Chrome
2. Start a call, speak
3. Watch for: Listening → Thinking → Speaking → Listening
4. Confirm AI audio is audible
5. If still broken, read logs and continue debugging

### Step 5: Check local repo for ad-hoc scripts

```bash
# Check if .local/phase1-tls/reconfigure-hidden-runtime.ps1 is tracked
git ls-files .local/phase1-tls/reconfigure-hidden-runtime.ps1
# If tracked, untrack it
git rm --cached .local/phase1-tls/reconfigure-hidden-runtime.ps1
# Add to .gitignore if not already
```

## SSH Commands Reference

```bash
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.err.log -Tail 300"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\ai-backend.hidden.out.log -Tail 200"'
ssh rayme-pmpg 'powershell -NoProfile -Command "Get-Content C:\\Users\\pmpg\\rayme\\logs\\web-ui.hidden.out.log -Tail 200"'
```

## Do Not

- Do NOT create new ad-hoc scripts
- Do NOT use the ad-hoc PS1 scripts
- Do NOT run Playwright E2E tests
- Do NOT reintroduce fake/synthetic success paths
- Do NOT mark resolved until live Android path works end-to-end

## Investigation Evidence (2026-04-27T19:00:00Z)

### Problem A: No AI Audio

- checked: Full audio delivery path — TTS synthesis -> _queue_outbound_audio -> QueuedAudioOutputTrack.enqueue -> aiortc RTP -> browser ontrack -> AudioContext -> speakers
- found: Path looks correct. TTS fix (8d20fd2) keeps connection alive. But OMEN logs are sparse after 10:55 AM restart — no speak_call logs visible.
- checked: Client attachRemoteAudio — AudioContext resume() called if suspended, but resume() requires user gesture on Android Chrome
- implication: If AudioContext suspends, resume() silently fails. TTS audio never plays.

### Problem B: Silence Transcribed as "Thank You"

- checked: session.py handle_inbound_audio_frame line 109
- found: Frame drop condition is `if self.muted or self.state in {"ended", "failed"}` — does NOT include "speaking" or "thinking"
- checked: Client +page.svelte — no mic gating during AI turns
- found: Mic tracks never disabled during thinking/speaking states. Audio continuously flows to server.
- implication: Ambient noise gets transcribed during AI thinking/speaking. This is the root cause of "thank you" hallucination.

### Applied Fixes

- Fix B1: Server-side frame drop during speaking state (session.py)
- Fix B2: Client-side mic gating — disable mic on thinking/speaking, re-enable on listening (+page.svelte)
- Fix A1: Added diagnostics logging to track TTS synthesis and audio delivery
