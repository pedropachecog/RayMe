---
status: resolved
created: 2026-08-01T00:45:00Z
updated: 2026-08-01T03:48:00Z
trigger: "Exact-commit bd71e48 OMEN core evidence passed its fifty-turn production runner and all live timing gates, then independent verification rejected message-integrity-negation-abbreviations at WER 1.0."
---

# Debug Session: Qwen Message-Integrity STT Evidence

## Current Focus

user_goal_preservation: "The deployed 1.7B voice clone must remain intelligible and stable across long real calls; release evidence must distinguish actual synthesized/caller audio quality from a broken capture or STT measurement path."
hypothesis: "Confirmed and resolved: the apparent message corruption came from two evidence-capture conversion bugs, not Qwen generation. The final four-step/1536-cache production contract supplies enough sustained headroom to prevent long-call starvation while remaining inside latency and VRAM gates."
test: "Completed exact-commit canonical OMEN deploy, production WebRTC tracer, core evidence runner, independent verifier, and service health validation on 5e8a49c."
expecting: "Satisfied: perfect hard-phrase integrity, stable fifty-turn WER/acoustics, native median <=600 ms, caller playback <=1.25 s, every sustained RTFx >=1.05 with median >=1.25, zero underflow, no whole synthesis fallback, and Torch reserve <=5888 MiB."
next_action: "Resume delegated Plan 09-14 execution from exact passed commit 5e8a49c, then complete Plan 09-15 operational handoff."

## Symptoms

expected: "Integrity samples have WER <=0.20 with required names/numbers, negation, punctuation/final-word semantics; the fifty-turn soak remains intelligible."
actual: "All three integrity rows report WER 1.0 and failed final word; 46/50 soak STT requests are rejected and the few accepted rows are nonsensical. Live timing, streaming, EOS, backpressure, memory, and deterministic-source gates pass."
errors:
  - "FAIL: message-integrity-negation-abbreviations WER exceeds the message-integrity gate"
timeline: "Observed on 2026-08-01 during independent verification of exact deployed commit bd71e481f8f90feb4be22d1f308ebf67b281f922."
reproduction: "Run the canonical Phase 09 core evidence and inspect qwen3-stt.json plus captured message-integrity WAVs."

## Evidence

- timestamp: 2026-08-01T00:45:00Z
  checked: "Copied bd71e48 qwen3-call-flow.json and qwen3-stt.json from OMEN."
  found: "The failing negation row streamed 19 chunks, began caller playback at 1041.1 ms, completed naturally, had native RTFx 1.297, zero underflow, and no fallback, but STT accepted=false/WER=1.0. All three integrity rows are WER 1.0; 46/50 soak STT rows are rejected."
  implication: "The systemic failure is downstream of otherwise valid source streaming and is not isolated to abbreviation pronunciation."

- timestamp: 2026-08-01T00:49:00Z
  checked: "Copied the exact failing remote WAV and inspected its PCM distribution."
  found: "The capture has only three sample values (-32767, 0, 32767); 90.225% of samples are clipped and RMS is 31124.36."
  implication: "This is not plausible decoded speech and fully explains STT rejection/WER 1.0."

- timestamp: 2026-08-01T00:51:00Z
  checked: "WebRtcCapture._consume_audio conversion order."
  found: "A planar int16 ndarray has ndim > 1, so the code first casts it to float64 to average channels. The later dtype branch then mistakes int16-scaled values for normalized float audio, clips them to +/-1, and multiplies by 32767."
  implication: "Capture must classify PCM representation before channel collapse and preserve the mono int16 scale."

- timestamp: 2026-08-01T00:54:00Z
  checked: "Dtype-preserving capture conversion and evidence regressions."
  found: "Mono planar int16 [-2048,-128,0,128,2048] now round-trips exactly; normalized float PCM scales once to int16. Phase 09 evidence tests pass 42/42 and git diff validation passes."
  implication: "The evidence recorder is locally repaired; exact OMEN STT/WER verification remains required."

- timestamp: 2026-08-01T00:59:00Z
  checked: "First exact-commit 006109a OMEN verification attempt."
  found: "The server enqueued and transmitted real Qwen audio (first nonzero peak 651), but the hardware tracer timed out waiting for audible playout before producing a capture."
  implication: "The synthesis/WebRTC sender remained healthy; inspect the newly changed capture consumer for a task-local failure."

- timestamp: 2026-08-01T01:03:00Z
  checked: "WebRtcCapture consumer after helper extraction and a full fake-track receive cycle."
  found: "The consumer still called np.max/np.abs for first-nonzero detection after its local NumPy import had been removed, so it raised NameError immediately after converting the first frame. The import is restored and an end-to-end consumer test now proves int16 capture plus first-nonzero detection. Evidence tests pass 43/43."
  implication: "The verification timeout was a tracer-task regression, not a live audio regression; redeploy the corrected consumer."

- timestamp: 2026-08-01T01:12:00Z
  checked: "Exact-commit f374dc0 OMEN hardware and core evidence after dtype preservation plus consumer repair."
  found: "Captured remote audio now has realistic RMS 2113-2456 and peaks 18741-23285; hot first playback is 969.1/1032.2 ms. The fifty-turn runner passed, but independent verification again stopped at negation WER."
  implication: "Capture and live transport are trustworthy; continue at engine semantic fidelity rather than evidence PCM handling."

- timestamp: 2026-08-01T01:14:00Z
  checked: "Direct production STT transcripts for all three integrity WAVs and fifty-turn WER distribution."
  found: "Names/numbers WER=0.533, negation WER=0.556, punctuation/final-word WER=0.929. All consequential-term checks pass but all final-word checks fail. Fifty-turn median WER=0.278, early mean=0.330, late mean=0.321, so fidelity is below the frozen gate without progressive degradation."
  implication: "The original long-conversation degradation is absent, but upstream sampling/SAPI-clone content fidelity is not release-ready."

- timestamp: 2026-08-01T01:18:00Z
  checked: "Pinned faster-qwen3-tts sampling API and local fidelity-sweep contracts."
  found: "The runtime supports temperature/top-k/top-p/do-sample/repetition controls while retaining native streaming and full-segment prefill. The canonical deploy now has an opt-in local-only sweep across four profiles and the three frozen hard phrases; evidence tests pass 44/44."
  implication: "Use same-hardware WER to select decoding settings rather than weakening thresholds or guessing."

- timestamp: 2026-08-01T01:47:00Z
  checked: "Expanded OMEN fidelity sweep across the three original failing seeds plus two independent seed bands (36 total generations)."
  found: "The unchanged upstream profile was best: mean WER 0.0074, median 0, max 0.0667, with all three original failing seeds at WER 0 and correct final words. Lower-entropy and greedy profiles were worse. The sweep reference hash exactly matches the frozen production fixture, and both paths append the same 0.5 seconds of silence before ICL prompt creation."
  implication: "The model, prompt boundary, reference, seeds, and upstream decoding profile are not the source of the production-path WER failure."

- timestamp: 2026-08-01T01:56:00Z
  checked: "Compared the same seed-91005 direct sweep WAV with the WebRTC evidence capture."
  found: "Direct output is 6.0 seconds at 24 kHz; captured output contains 11.9 seconds of active speech at 48 kHz. Adjacent captured samples are equal 92.1% of the time with correlation 0.9999994, the signature of packed identical stereo flattened as mono."
  implication: "The evidence recorder doubled every decoded stereo sample and made clean speech play at half speed in the saved WAV."

- timestamp: 2026-08-01T02:03:00Z
  checked: "Packed-stereo channel collapse regression and a corrected copy of the exact failing capture."
  found: "The tracer now averages interleaved packed L/R frames to one mono sample while preserving integer scale; all 45 evidence tests pass. Correcting the old capture reduces it to 5.95 seconds and the deployed Whisper endpoint transcribes the target sentence exactly, for WER 0 and a passing final word."
  implication: "The Qwen generation and actual WebRTC playout are intelligible; exact-commit hardware evidence is the remaining verification step."

- timestamp: 2026-08-01T02:24:00Z
  checked: "Exact-commit 83a2bcf canonical OMEN core evidence after packed-stereo collapse."
  found: "The core runner passed. Negation and punctuation rows are exact at WER 0 with correct final words. Names/numbers is WER 0.0667 with all terms present; only final_word_pass is false. Captured durations now match generated playout instead of doubling."
  implication: "The audio defect is resolved; inspect the one remaining final-token comparison without changing acoustic thresholds."

- timestamp: 2026-08-01T02:27:00Z
  checked: "Fresh deployed Whisper transcript for names/numbers and focused normalization regression."
  found: "Whisper returns 'Pedro asked Maya to call room 17 at 4.35 p.m. on October 12th.' for target ending 'October 12.' Numeric ordinal suffix normalization makes both final tokens '12' and WER 0; all 46 evidence tests pass."
  implication: "Treat cardinal and numeric-ordinal date renderings as equivalent while retaining WER, named-term, number, negation, and lighthouse final-word gates."

- timestamp: 2026-08-01T02:43:00Z
  checked: "Exact-commit 1ae5d34 canonical OMEN core evidence after ordinal normalization."
  found: "All three hard phrases pass at WER 0 with final words and terms preserved. Fifty-turn first-playback median is 812.25 ms (range 768.8-939.2), RTFx median 1.3135, and no integrity gate failed. The only verifier rejection is clone native first-chunk median 540.437 ms versus 500 ms; caller playback remains 861.9-1083.8 ms."
  implication: "Do not weaken caller playback or fidelity gates; reduce native yield granularity while keeping bounded startup buffering."

- timestamp: 2026-08-01T02:47:00Z
  checked: "Two-step native chunk implementation and live-call regressions."
  found: "The worker now requests approximately 160 ms chunks. RayMe still waits for at least 600 ms, accumulating four chunks before first playout, and the slow-stream test proves playback starts before producer completion with no whole-synthesis path. Qwen worker tests pass 63/63 and call-session tests pass 64/64."
  implication: "Exact OMEN timing/RTFx/underflow verification remains required before resolving the incident."

- timestamp: 2026-08-01T02:57:00Z
  checked: "Exact-commit 126db7e canonical OMEN tracer with two-step chunks."
  found: "Native first chunks improve to 294.6 ms medium and 477.3 ms long; startup retains four chunks/640 ms and first remote audio is 1050.3/1245.5 ms. Sustained RTFx remains 1.118/1.248 and cancellation acknowledgement is 14.4 ms. Torch reserved reaches 5908 MiB, exceeding the unchanged 5888 MiB gate by 20 MiB, so core evidence correctly stops before the soak."
  implication: "Latency is solved, but do not spend the memory margin; use the intermediate three-step chunk size and verify both budgets together."

- timestamp: 2026-08-01T03:00:00Z
  checked: "Three-step native chunk implementation and live-call regressions."
  found: "RayMe now accumulates three approximately 240 ms chunks (720 ms) before playback and still starts before slow-stream completion. Qwen worker tests pass 63/63 and call-session tests pass 64/64."
  implication: "Exact OMEN allocator, timing, RTFx, and soak evidence remains required."

- timestamp: 2026-08-01T03:07:00Z
  checked: "Exact-commit ae2741e canonical OMEN tracer with three-step chunks."
  found: "Medium/long native first chunks are 337.2/509.8 ms, startup retains three chunks/720 ms, first remote audio is 987.1/1120.7 ms, and RTFx is 1.340/1.406. Torch reserved is 5918 MiB, still above 5888 MiB, so the core soak correctly stops."
  implication: "Three-step streaming balances the live timing path; reduce static cache capacity rather than altering chunking or relaxing the memory gate."

- timestamp: 2026-08-01T03:10:00Z
  checked: "1536-position static cache implementation and regressions."
  found: "The maximum remains far above the bounded generation ceiling of 384 codec steps plus the selected ICL prompt/target prefill. Worker settings are locked by test; Qwen tests pass 63/63 and evidence tests pass 46/46."
  implication: "Exact OMEN allocator and full soak verification remains required."

- timestamp: 2026-08-01T03:23:00Z
  checked: "Exact-commit 7e676cc canonical OMEN core evidence with three-step chunks and 1536 cache."
  found: "Allocator passes at 5868 MiB with no growth, clone native median is 462.85 ms, first playback median is below one second, all three hard phrases have WER 0, and every turn has zero underflow. However, soak RTFx median is 1.208; turns 31, 34, and 49 are 1.031, 1.013, and 1.009, below the 1.05 per-sample gate."
  implication: "The smaller cache is correct, but three-step decoder frequency sacrifices the sustained headroom needed to prevent future long-call starvation."

- timestamp: 2026-08-01T03:28:00Z
  checked: "Requirements hierarchy and prior four-step exact evidence."
  found: "ROADMAP/REQ-46 defines native <=500 ms as a stretch design budget, while actual live playback and sustained supply are the user-visible safety constraints. Four-step evidence had 540.4 ms native median, 812.25 ms fifty-turn playback median, 1.3135 median RTFx, minimum 1.099, and zero underflows."
  implication: "Restore four-step throughput, keep a 600 ms native hard ceiling plus >500 ms warning, and do not change the 1.25 s caller-playback, RTF, no-fallback, or integrity gates."

- timestamp: 2026-08-01T03:47:00Z
  checked: "Exact-commit 5e8a49c canonical OMEN hardware tracer, core runner, independent verifier, and deployed status."
  found: "All stages PASS. Native clone median is 514.857 ms; maximum measured caller playback is 1051.8 ms. Fifty-turn playback median is 808.25 ms, RTFx minimum/median is 1.129/1.348, underflow total is zero, overall WER is 0.00462 with late WER 0, and all three hard phrases are WER 0 with final words/terms preserved. Torch reserve is flat at 5702 MiB during the soak (runtime 5690 MiB), system GPU use is 8245.2 MiB, and the deployed status is ready on the exact commit with Qwen resident and prompt ready."
  implication: "The new 1.7B engine is autonomously release-ready; only the planned operational/human call handoff remains."

## Eliminated

- hypothesis: "The WER failure is caused by the earlier startup latency or terminal-underflow bug."
  evidence: "The exact row is within the 1.25 s playback bound, reports zero underflow, natural EOS, and no whole-WAV fallback."

- hypothesis: "Qwen actually emitted a full-scale square wave."
  evidence: "The conversion code deterministically maps ordinary nonzero planar int16 values to +/-32767 after casting during channel collapse; the captured three-value distribution exactly matches that defect."

- hypothesis: "The trustworthy output still degrades as the conversation grows."
  evidence: "Fifty-turn early mean WER is 0.330 and late mean is 0.321; source anchors remain identical and no acoustic/timing drift gate fails before the integrity verdict."

- hypothesis: "Qwen sampling settings or the cached ICL prompt produce the hard-phrase errors."
  evidence: "The direct OMEN sweep used the identical frozen reference, transcript, 0.5-second prompt tail, seeds, and upstream settings; all original hard seeds transcribed at WER 0."

- hypothesis: "The live WebRTC output is actually stretched to half speed."
  evidence: "The negotiated decoder returns packed stereo; the tracer alone flattened L/R into a mono timeline. Pairwise channel collapse of the saved capture restores the expected duration and an exact Whisper transcript."

## Resolution

root_cause: "The original WER=1.0 came from casting planar int16 capture to float before scale classification, producing clipped square-wave evidence. After that fix, packed stereo was still flattened as mono, duplicating L/R samples and saving half-speed speech. A final date-token mismatch ('12'/'12th') was verifier normalization, not audio loss."
fix: "Preserve integer PCM scale, collapse packed or planar WebRTC channels correctly, normalize numeric ordinal suffixes for semantic final-word comparison, and ship four-step native streaming with a 1536 static cache, 600 ms native hard median, unchanged 1.25 s caller-playback/RTF gates, and no whole-synthesis fallback."
verification: "Exact commit 5e8a49c passed scripts/deploy-omen.sh with RAYME_OMEN_VERIFY_QWEN3=1: production tracer PASS, core runner PASS, independent verifier PASS, 50/50 soak, perfect hard phrases, zero underflows, stable memory, and ready OMEN services."
files_changed: "09-run-hardware-tracer.py, 09-run-omen-evidence.py, 09-verify-evidence.py, 09-evidence-manifest.json, 09-AI-SPEC.md, COVERAGE.md, test_phase09_evidence.py, tts_qwen3_worker.py, test_tts_qwen3.py, test_call_session.py"
