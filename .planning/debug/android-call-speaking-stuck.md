---
status: awaiting_human_verify
created: 2026-04-27T03:30:00Z
updated: 2026-04-27T05:00:00Z
handoff_for: next-agent
---

# Handoff: OMEN Deployment Infrastructure Broken + Call Debugging Stalled

## What Needs to Be Done

Two problems:

1. **OMEN deployment infrastructure is broken** — ad-hoc PS1 scripts hijacked the scheduled tasks. The app is COMPLETELY DOWN (ports 8443 and 9443 not responding). Need to clean up the ad-hoc scripts and restore proper deployment via `scripts/deploy-omen.sh`.

2. **Android call debugging stalled** — we were making progress (VAD/STT works, turns complete) but the call gets stuck in "speaking" with no audio. The fixes at commit 8244cb0 caused regressions (stuck in listening, call won't start). The data channel keepalive fix at 02bca89 was pushed but never tested because the app is down.

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
