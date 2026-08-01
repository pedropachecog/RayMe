# Phase 09 Deferred Items

No open blocker remains for Plan 09-15 autonomous release readiness.

## Resolved: deployed browser call could not complete two cycles

- **Original blocked commit:** `c392d26264a28b7f00c1dd8ced6f864ef7ee5a14`
- **Resolved deployed commit:** `3501a1a1e2b4371a46d6d65322975134b0d35a5f`
- **Root cause:** a boundary-emitted Qwen sentence could leave the turn without a backend terminal marker; the live Windows process also differed from the executable originally targeted by the WebRTC firewall rule.
- **Resolution:** commit `98161b2` added synthesis-free terminalization for the empty segmenter tail, and commit `3501a1a` bound the LocalSubnet-only UDP rule to the base Python executable that owns live port 9443.
- **Verification:** the exact deployed `live-call.spec.ts` suite passed 6/6 across desktop and mobile Chromium, including two user-to-AI cycles, early audio, two `ai_done`/listening recoveries, and durable speech. The decision-ready verifier also passed against the same commit.
- **Debug record:** `.planning/debug/resolved/qwen-browser-speaking-stuck.md`

## Validation boundary: operational shell gate

`scripts/operational-check.sh handoff` validates the handoff arguments and required artifact presence; it is not the semantic evidence oracle. Plan 09-15 therefore runs `09-verify-evidence.py --decision-ready` first and records both commands in the operator handoff. The ordered release workflow passes at the exact deployed commit above, so this boundary is documented and non-blocking.

## Human acceptance still pending

Integrated human listening and the physical multi-turn/barge-in call remain explicit manual acceptance steps. They are not blockers to the autonomous evidence result and must not be reported as completed until a person performs them.
