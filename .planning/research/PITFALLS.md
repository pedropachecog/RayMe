# Pitfalls Research

**Domain:** Self-hosted real-time voice AI calls (full-duplex browser + GPU backend)
**Researched:** 2026-04-16
**Confidence:** HIGH

Pitfalls below are ordered by impact on the project's core value: "feels like an actual phone call." Anything that breaks duplex, barge-in, latency, or mobile audio is **Critical**. Everything else is a supporting concern.

Severity legend: **Critical** = call-feel broken or project fails validation. **High** = major UX degradation. **Medium** = quality/operational issue users notice. **Low** = long-tail cleanup.

---

## Critical Pitfalls

### Pitfall 1: Echo loop — TTS audio bleeds back into mic, retriggers VAD, ping-pongs the conversation

**Severity:** Critical

**What goes wrong:**
AI speaks through the phone/laptop speaker. The mic picks up that audio. Server-side VAD flags it as user speech, triggers a barge-in, cancels TTS mid-sentence, submits the hallucinated "user turn" (which is the AI's own words echoed back through Whisper), and the LLM replies to itself. Worst case: the two sides ping-pong indefinitely. Best case: every sentence is cut off by the agent's own voice.

**Why it happens:**
Browser AEC (AcousticEchoCancellation in getUserMedia constraints) only cancels audio the browser *knows it is playing*. If TTS audio is streamed from the backend as raw PCM/Opus and decoded manually into an `AudioContext` buffer — which is what nearly every custom pipeline does — the browser has no reference signal. AEC becomes a no-op, and the mic captures a loud copy of the speaker.

**How to avoid:**
- Play TTS audio through an `<audio>` element or a `MediaStreamAudioDestinationNode` that the browser's WebRTC stack can see. Do not bypass the browser audio graph.
- Request `getUserMedia({ audio: { echoCancellation: true, autoGainControl: true, noiseSuppression: true }})` — and verify it's honored (log `track.getSettings()`).
- Add a server-side "playback gate": while TTS is actively playing, ignore or heavily dampen VAD triggers until either (a) real duplex barge-in logic confirms user voice energy exceeds TTS output energy plus a margin, or (b) the user's STT partial has at least N real words (not filler).
- Track `playback_active_until` on the server from the TTS engine's sample-accurate timeline, not just "we started streaming."
- For headphone users the problem mostly disappears; make headphones a recommended configuration in the UI help text but do not *require* them.

**Warning signs:**
- The first dev call experiences one to two "AI interrupts itself" events per minute.
- STT transcripts contain fragments of AI-generated sentences the user never said.
- Captions show the user "speaking" during moments of actual silence while TTS is playing.
- Issue reproduces on laptop speakers but not AirPods — that's the smoking gun.

**Phase to address:** Duplex/barge-in phase (whichever phase first puts STT + TTS in the same session). Must be solved before any "feels like a call" demo is meaningful.

---

### Pitfall 2: Mobile Safari refuses the mic because HTTPS is missing, self-signed, or the cert isn't trusted on the device

**Severity:** Critical

**What goes wrong:**
The app works perfectly on desktop Chrome via `http://192.168.x.x:port`. On an iPhone, `getUserMedia` either silently rejects, throws `NotAllowedError`, or Safari shows "Cannot connect to server" because the self-signed cert is untrusted. User cannot place a call from their phone, which is 50% of the use case.

**Why it happens:**
- `getUserMedia` is gated on a "secure context" everywhere except `localhost`. LAN IPs are **not** secure contexts over plain HTTP.
- Desktop Chrome shows a click-through warning for self-signed certs. **iOS Safari does not** — it either outright rejects or requires installing the Root CA via a Configuration Profile *and* manually enabling full trust under Settings → General → About → Certificate Trust Settings. Novice users will not find this.
- Even with a trusted cert, `getUserMedia` requires a user gesture on iOS; auto-starting a call from a deep link can fail silently.

**How to avoid:**
- Pick a specific HTTPS strategy during the Web UI phase and commit to it. Three realistic options:
  1. **mkcert + local CA install** — generate a local CA, install it on every device that needs access (one-time per device), issue certs signed by it. Cleanest for a one-person home LAN.
  2. **Tailscale HTTPS / tailnet cert** — Tailscale issues real Let's Encrypt certs for `*.ts.net` hostnames automatically. Zero cert install on devices. Recommended if Tailscale is acceptable.
  3. **Real domain + DNS challenge + Let's Encrypt** — point a subdomain of a domain you own at the LAN IP, use DNS-01 ACME. Overkill but bulletproof.
- Assign a stable hostname (via `.local` mDNS or a hosts-file entry) so the cert CN matches the URL the phone hits.
- Never suggest `http://...` in the README. Every "how to access this" doc must start with `https://`.
- On the Voice Call screen, before opening the call, do a one-line precheck: `if (!window.isSecureContext) show "Must be on HTTPS"`. Fail loud, not silent.

**Warning signs:**
- `navigator.mediaDevices` is `undefined` in Safari (it's gated behind secure context).
- Permission prompt never appears.
- Desktop Chrome works, iPhone does not.

**Phase to address:** Web UI / deployment phase, before the first mobile duplex test. This is a day-one decision because reversing it later means redeploying and re-trusting certs on every phone.

---

### Pitfall 3: AudioContext is created without a user gesture, so TTS never plays on iOS

**Severity:** Critical

**What goes wrong:**
The call UI opens, STT works, the LLM responds, TTS audio is streamed back — and nothing comes out of the iPhone speaker. Console (if you can even attach one) shows "The AudioContext was not allowed to start." The user taps around, eventually gives up.

**Why it happens:**
iOS Safari (and increasingly all browsers) require an `AudioContext` to be created *or resumed* inside a user-gesture handler (touchstart/click). An `AudioContext` created at page load starts in `suspended` state and will silently drop all audio until `.resume()` is called from a gesture. The "Start Call" button *is* a gesture, but only if the `AudioContext` is created/resumed inside that specific click handler — not later, not in an async callback that awaits a WebSocket.

**How to avoid:**
- Create a single shared `AudioContext` on first user interaction (e.g., the "Start Call" tap). Reuse it for every call; do not recreate per call.
- Inside the same synchronous handler as the tap, call `audioContext.resume()` and verify `state === 'running'` before proceeding.
- On iOS, also unlock by playing a 1-sample silent buffer inside the gesture — this is the standard idiom and makes subsequent auto-routing reliable.
- If the `AudioContext` transitions to `interrupted` (screen lock, incoming call), handle `statechange` and auto-resume when the user returns.
- Additionally: on iOS, a call that is started via push/deeplink and auto-resumed after minimization may find the `AudioContext` suspended with *no gesture in sight*. Do not rely on auto-dialing; always require a tap.

**Warning signs:**
- Works on first load after a tap, breaks on the second call.
- Works when the dev tools are open (Safari's remote Web Inspector changes behavior).
- Audio plays if the user taps again before TTS finishes the first sentence.

**Phase to address:** Voice Call UI phase, same phase as the call screen itself. Set up the audio-unlock pattern on day one.

---

### Pitfall 4: F5-TTS does not stream natively — naively waiting for full synthesis blows the latency budget

**Severity:** Critical

**What goes wrong:**
Reference implementations of F5-TTS generate a whole utterance, then return a wav. For a 15-word sentence at RTF 0.15 on a 3060 that's ~1.5s *before TTS audio starts playing*. Stack that on top of STT endpoint + LLM TTFT and you're at 2.5–3s per turn — far outside the 600–800ms "natural phone call" window.

**Why it happens:**
F5-TTS (as of the flow-matching release and throughout late 2025 / early 2026) is architected for 30-second chunked generation, not token-by-token streaming. The official repo has an open tracking issue for real-time streaming support. Gradio demos hide this by generating short sentences quickly, which gives a false sense that it's "fast enough."

**How to avoid:**
- Architect the TTS layer as "stream of short utterances" rather than "one long synthesis":
  1. Extract sentence boundaries from the LLM's token stream as they arrive (split on `. ! ? \n` with a small lookahead).
  2. Dispatch each sentence to F5 synthesis the moment its boundary is seen; do not wait for the LLM to finish.
  3. Queue the generated audio segments and play them back-to-back in the browser.
- First-audio latency is then `STT-endpoint + LLM-TTFT + first-sentence synthesis + one network hop` — targets ~500–800ms if each piece is tight.
- Keep first sentence short: bias the system prompt to "Start every reply with a short acknowledging phrase" so the first audible chunk is 2–4 words.
- Budget: aim for F5 first-sentence synthesis under 300ms on the 3060 for a 3–5 word sentence. If it misses, fall back to XTTS v2 for that voice.
- If streaming support lands in F5-TTS upstream, revisit; treat current approach as a workaround.

**Warning signs:**
- Time-to-first-audio is greater than ~1s end-to-end even with a fast LLM.
- The AI sounds like it's always "thinking" for a second before responding.
- You can visually see the captions update before any audio plays.

**Phase to address:** TTS integration phase. This shapes the entire AI backend pipeline, not just the TTS service.

---

### Pitfall 5: STT endpointing (deciding when the user stopped talking) is where conversational systems fail

**Severity:** Critical

**What goes wrong:**
Two failure modes, both equally bad:
- **Cut off:** System decides user finished after 300ms of silence mid-thought ("I was thinking maybe we could..."), fires the LLM with a half-sentence, AI responds to nothing useful.
- **Dragged out:** System waits 2s of silence to be sure, user sits there hearing nothing, feels like the AI is frozen.

**Why it happens:**
Whisper was trained on 30-second fixed chunks; it has no native concept of "end of utterance." Naive streaming Whisper implementations just keep transcribing until *you* decide when to stop. The decision layer is what people either skip or mis-tune.

**How to avoid:**
- Use a **dedicated VAD for endpointing** (Silero VAD is the standard — MIT licensed, ~tiny model, <1ms per frame on CPU). Don't try to endpoint from Whisper's no_speech_prob; it's unreliable.
- Two-stage gate: VAD detects silence → wait configurable `endpoint_ms` (default 500–700ms) → confirm no new speech → fire endpoint.
- Use **adaptive endpoint**: if the LLM is mid-reply (we're interrupting), endpoint aggressively (200ms). If the user is mid-thought in a quiet room, endpoint conservatively (700ms).
- Emit **partial transcripts** to the UI live, final only on endpoint. This gives the user visible feedback that the system is hearing them, which tolerates longer endpoint windows.
- Test with a Spanish-accented English speaker (the builder) specifically — accented speech has different pause patterns and VAD can mis-classify filled pauses ("uh", "este") as speech or silence inconsistently.

**Warning signs:**
- User reports "it cuts me off" or "it takes forever to reply."
- Captions stall on the last word for multiple seconds before the AI responds.
- Short responses ("yeah", "okay") get truncated or missed.

**Phase to address:** STT / duplex phase. Pair this tuning with Pitfall 1 (echo loop) — they interact heavily.

---

### Pitfall 6: Whisper hallucinates plausible sentences on silence or non-speech audio

**Severity:** High (approaches Critical on mobile with noisy environments)

**What goes wrong:**
User is silent, HVAC runs, baby cries, music plays in the background. Whisper transcribes "Thank you for watching." or "Please subscribe to my channel." or (classic) random Korean/Spanish sentences. The LLM then responds to those ghosts.

**Why it happens:**
Whisper's training data included YouTube subtitles and podcast audio with trailing silence. The model learned to output common filler sentences when given "unlabeled" audio. It hallucinates especially hard on audio longer than 30s (chunk boundary) or on pure silence.

**How to avoid:**
- **Pre-gate with VAD**: only feed Whisper audio segments that Silero VAD marked as speech. This is the single most effective mitigation (cited in WhisperX, consistently reduces hallucinations in benchmarks).
- Use `condition_on_previous_text=False` in faster-whisper for streaming — previous-text conditioning amplifies hallucinations.
- Set `no_speech_threshold` conservatively and `logprob_threshold` to reject low-confidence segments.
- Add a post-filter: if the final transcript is one of a known hallucination list ("Thank you for watching", "Please subscribe", ". . ."), drop it.
- Keep chunks short (≤10s) via VAD segmentation.

**Warning signs:**
- Transcripts contain "Thanks for watching" or similar YouTube-outro phrases with no mic activity.
- Long silences produce full sentences in the transcript log.
- Transcript repeats the same phrase multiple times ("I'm sorry. I'm sorry. I'm sorry.").

**Phase to address:** STT phase. Apply mitigations before the first call test, not in bug-fixing later.

---

### Pitfall 7: VRAM budget on 12GB blows up when STT + TTS + VAD are loaded simultaneously for real-time use

**Severity:** High

**What goes wrong:**
Loaded separately, each model fits. At runtime, with activations, KV caches, audio buffers, and fragmentation, the backend OOMs mid-call or falls back to swap, causing multi-second stalls. Long sessions drift toward OOM even without obvious leaks.

**Why it happens:**
Published "VRAM required" figures are usually *weight-only* at fp16. Real use adds:
- Activation memory during inference (model-dependent, often 1–3GB extra at batch 1).
- KV cache for any transformer-based TTS like XTTS (grows with utterance length).
- CUDA allocator fragmentation from allocating/freeing audio tensors every turn.
- PyTorch's workspace + cudnn autotune caches.

On a 12GB 3060, a realistic simultaneous load:

| Component | Weights (fp16) | Peak working set |
|-----------|---------------|------------------|
| Whisper large-v3 (via faster-whisper CT2 int8) | ~1.5 GB | ~2 GB |
| distil-large-v3 int8 (alternative) | ~0.75 GB | ~1.1 GB |
| Silero VAD | ~15 MB | ~50 MB |
| F5-TTS | ~1.5 GB | ~2.5–3 GB |
| XTTS v2 | ~2 GB | ~3–3.5 GB |
| OS/WDDM reserve on Windows | — | ~0.5–1 GB |

Both TTS engines simultaneously + whisper-large + overhead *will* exceed 12 GB on Windows. Linux is tighter but not by much.

**How to avoid:**
- Default STT: **faster-whisper distil-large-v3 int8** (good accent robustness, ~1.1GB peak). Only upgrade to full large-v3 if accent WER is unacceptable.
- Use **faster-whisper (CTranslate2)** not vanilla openai/whisper — 4× faster and less memory.
- **Lazy-load TTS engines:** keep only the engine required by the currently-selected voice in VRAM. Swap when the user changes voice. Cost: ~2–5s swap on first use (acceptable between calls, unacceptable mid-call — lock the voice for the duration of a call).
- On Windows, set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to mitigate fragmentation.
- Monitor `torch.cuda.memory_reserved()` across a long session and assert it stays bounded. If it drifts, explicit `torch.cuda.empty_cache()` between calls.
- If even one TTS engine loaded + STT blows the budget on Windows, fall back to Linux (WSL2 won't help — it uses the same WDDM allocation) or drop the STT to distil-small.

**Warning signs:**
- `nvidia-smi` shows >11 GB used with headroom shrinking over a 15-minute session.
- First call after changing voice takes >2s to start.
- Occasional `CUDA out of memory` errors that don't reproduce on the first few calls.

**Phase to address:** AI backend phase, before integrating TTS engines. Decide the swap strategy upfront; bolt-on is painful.

---

### Pitfall 8: Mid-stream LLM cancellation doesn't actually cancel — GPU keeps generating tokens you throw away

**Severity:** High

**What goes wrong:**
User barges in. The UI stops playing TTS. But the LLM server keeps generating the rest of the (now-irrelevant) reply in the background, burning GPU cycles that should be answering the user's *new* turn. On a local llama-server running on the same or nearby GPU, this also means the next turn's TTFT is delayed because the previous generation is still queued.

**Why it happens:**
Closing an `EventSource` or `fetch` stream on the client does not by itself signal cancellation to an OpenAI-compatible backend. The HTTP connection close propagates eventually, but many servers (llama-server, LM Studio, early vLLM versions) only notice on the next token write or at the sampling boundary. Some don't notice at all until the generation completes.

**How to avoid:**
- Use `fetch` with an `AbortController` on the Web UI → AI backend path. The AI backend proxies to the LLM, and **must** forward the abort downstream.
- On the AI backend, use a client that supports true per-request cancellation (OpenAI Python SDK supports `with client.chat.completions.create(...)` contextmanager; or use `httpx` with explicit cancel scopes).
- For llama-server specifically, `stop` requests are best-effort; verify cancellation actually aborts generation (watch llama-server logs for "request cancelled" vs "generation complete").
- Design the turn state machine so a new user turn *always* aborts any in-flight LLM request before queuing the new one. Don't allow two LLM streams to run in parallel for the same chat.
- Log wasted-token-count per cancellation so you can measure the leak and tune.

**Warning signs:**
- Backend LLM process shows ongoing GPU usage after a barge-in.
- Next-turn TTFT spikes after a barge-in relative to a clean turn.
- `nvidia-smi` power draw stays high during what should be an idle moment.

**Phase to address:** AI backend + barge-in phase. The LLM-cancellation pattern has to be established before barge-in is declared working.

---

### Pitfall 9: F5-TTS voice quality is corrupted by reference-transcript errors from STT auto-transcription

**Severity:** High

**What goes wrong:**
Voice Lab accepts a 15-second voice sample, runs STT to auto-fill the reference transcript, saves the voice. At synthesis time, F5 produces gibberish, mispronounces the speaker's words, or inserts phrases from the reference audio into the output (a known issue in F5-TTS #85). The voice sounds nothing like the reference.

**Why it happens:**
F5 is conditioned on `(reference_audio, reference_text)` pairs. A transcript error (say, "where" vs "were", a dropped word, a misspelled proper noun) creates a mismatch at inference: F5 tries to align reference-text to reference-audio and the wrong mapping poisons the voice embedding. Unlike XTTS which is more forgiving, F5 is quite sensitive to transcript accuracy.

Additional F5 gotchas that compound:
- Reference audio longer than ~20s truncates or drops output words.
- Reference audio with background music or noise degrades the clone badly.

**How to avoid:**
- **Always let the user edit the auto-transcript.** Voice Lab UX: STT runs → show the transcript in an editable textbox → user reviews → save. This is in the active requirements already; treat it as non-negotiable.
- Cap reference audio at 15s in the UI (hard stop at 20s). Ideal is 8–12s of clean, expressive speech.
- Show a spectrogram or waveform with a "trim" UI so users can cut off breath noises and silence at the edges.
- Run a quick pre-save check: synthesize a short test phrase with the saved voice and play it back. If the user says "doesn't sound right," prompt them to re-record or re-transcribe.
- Warn users: "For best results, record in a quiet room; avoid background music."

**Warning signs:**
- Generated voice mispronounces proper nouns that *are* in the reference transcript — usually a transcript-text mismatch.
- Generated audio contains words from the reference transcript injected into unrelated output.
- Voice clone quality is wildly inconsistent between voices.

**Phase to address:** Voice Lab phase. Bake the editable-transcript requirement into the first implementation.

---

### Pitfall 10: False barge-in triggers — breath, "mm-hmm", or a cough stops the AI mid-sentence

**Severity:** High

**What goes wrong:**
User inhales audibly. VAD fires. TTS cuts off. AI thinks the user was interrupting, context switches to "respond to whatever the user said," STT produces nothing useful, LLM generates a confused reply. Alternately: user back-channels ("mm-hmm", "yeah") to *signal agreement and keep the AI talking*, and the AI interprets this as a full interruption.

**Why it happens:**
VAD detects *voice activity*, not *intent to take the turn*. Breath energy, back-channels, laughs, and throat clears all look like speech to a frame-level classifier. Naive barge-in fires the moment VAD says "speech" — which is wrong.

**How to avoid:**
- **Minimum duration gate:** require N consecutive VAD-positive frames (e.g., ≥250–400ms of sustained speech) before calling it a barge-in. Breath is typically <200ms; back-channels are often <300ms.
- **Energy threshold:** require the mic signal RMS to exceed a calibrated threshold, not just "any voice detected."
- **Word-count gate:** do not cancel TTS until STT has produced at least one confident word, not just a VAD flag. This trades ~200–400ms of barge-in lag for dramatically fewer false fires.
- Consider a tiered response: on first VAD trigger, *duck* TTS volume by 50% (signals "I hear you"). Only fully cancel when the word-count gate trips. This mimics how humans handle back-channels.
- Tune against the actual user (builder speaks Spanish-accented English; some back-channel patterns may differ from the training data VADs were tuned on).

**Warning signs:**
- Testers report "it cuts me off when I breathe."
- Listening to a logged call, you can hear the AI stopping mid-word at random moments.
- Captions show empty user-turns ("" or "uh") between AI replies.

**Phase to address:** Barge-in / duplex phase, same phase as Pitfall 1 and 5.

---

### Pitfall 11: Race condition between "TTS finished" and "user started speaking"

**Severity:** High

**What goes wrong:**
AI finishes a sentence. User starts speaking 100ms after the last TTS sample plays. But the server's "TTS done" flag flipped *before* the last audio bytes made it to the user's speaker (buffering). From the server's point of view: TTS ended 400ms ago, the user is just starting a new turn. From the user's point of view: they started talking right as the AI finished. If the server's barge-in suppression is still active (Pitfall 1), the first word is missed. If it's not, it's handled correctly — but it may miscount the start timestamp and produce a weird endpoint-window offset.

**Why it happens:**
The server generates audio samples. The network transports them. The browser decodes and schedules them for playback. Actual audible playback is 100–500ms *after* the server emitted the bytes. "TTS done" on the server ≠ "user heard the last word."

**How to avoid:**
- Track **perceived playback position** on the server: use `AudioContext.currentTime` or `AudioBufferSourceNode.onended` from the browser to signal actual end-of-playback back to the server.
- Maintain a `tts_playing_until_server_time` estimate based on total bytes sent and known audio duration, padded by a fixed network+jitter buffer (~200ms). Don't accept barge-in interpretations until that time has elapsed post-TTS-done.
- Alternatively: send a distinct "user is now in turn" event from the browser, not just from server-side VAD. The browser knows when playback ended and can also run a browser-local VAD that matches perceptual reality.

**Warning signs:**
- Users report "it misses my first word after it stops talking."
- Logs show user-turn-start timestamps that are earlier than the server thinks they are.
- Captions lag behind audio.

**Phase to address:** Duplex phase. Instrument timing end-to-end from day one — add a shared clock/latency monitor to the call session object.

---

## High-Severity Pitfalls

### Pitfall 12: Coqui TTS is abandonware; pinning to the wrong fork strands you on broken Python versions

**Severity:** High

**What goes wrong:**
`pip install TTS` pulls the original `coqui-ai/TTS` package, which is unmaintained (Coqui shut down January 2024). It pins to old PyTorch and Python versions, breaks with numpy 2.x, breaks on newer CUDA, and has unresolved security issues. Installing today produces a fragile environment that will rot within months.

**Why it happens:**
The original company is gone. The `TTS` PyPI name is still the one most tutorials reference. Forks (most actively, `idiap/coqui-ai-TTS` published as `coqui-tts` on PyPI) have diverged and support newer dependency stacks, but Google hits still point to the old package.

**How to avoid:**
- Use the **`coqui-tts` package (idiap fork)**, not `TTS`. `pip install coqui-tts`.
- Pin the XTTS v2 model checkpoint explicitly (hash or version) — the model is licensed under CPML and distribution is unchanged, but the loader code keeps changing.
- Plan an escape hatch: design the TTS engine abstraction so adding a third engine (Fish Speech, CosyVoice 2, whatever) is a plugin, not a rewrite. F5 + XTTS today, something else next year is likely.
- Verify the fork is still maintained before each release cycle — the upstream repo activity is the bellwether.

**Warning signs:**
- Install fails on Python 3.12+ or numpy 2.x.
- `import TTS` works but lots of deprecation warnings.
- XTTS model download URL starts failing (hosted on old Coqui infra).

**Phase to address:** TTS integration phase. Lock dependency choice in the first implementation.

---

### Pitfall 13: XTTS v2 and F5-TTS are both non-commercial licenses

**Severity:** High (for clarity about the product's shape, not for v1 shipping)

**What goes wrong:**
Project is built on F5-TTS (CC-BY-NC 4.0) and XTTS v2 (CPML, explicitly non-commercial). If the project ever pivots to a paid tier, a team use case, or distributed SaaS, both engines must be replaced — and voice clones made with them can't be redistributed.

**Why it happens:**
Both licenses were set by model authors for non-commercial research release. Coqui previously sold commercial XTTS licenses; with the company gone, no legitimate commercial-use path exists for XTTS today. F5 commercial licensing is ambiguous (see issue #997 in the F5 repo).

**How to avoid:**
- Accept the license for v1: single-user self-hosted, personal use, clearly non-commercial. Document this in README.
- Do not build features that presume commercial distribution of voice clones or model outputs (e.g., a "share your voice pack" marketplace).
- Keep the TTS engine layer pluggable — if the project ever needs a commercial path, it swaps engines (Fish Speech is Apache-2.0, Kokoro is Apache-2.0, several other 2026 options exist).
- Add a small NOTICES/LICENSES.md that lists each model's license so future-you doesn't forget.

**Warning signs:**
- Plans drift toward "let friends use it too over the internet" or "build a companion service" without license review.

**Phase to address:** Project setup / TTS phase. Document upfront, revisit at each milestone.

---

### Pitfall 14: SillyTavern card parsing — XSS via character description / first message / example dialogue

**Severity:** High

**What goes wrong:**
Character card's `description`, `first_mes`, `mes_example`, `scenario`, or `creator_notes` contains crafted HTML/JS. The character gallery or chat screen renders those fields via `innerHTML` or a permissive Markdown renderer, script runs, LAN-level access means the attacker (the card author) gets arbitrary JS execution in the app origin. Even as single-user, this can exfiltrate LAN service endpoints, model weights, saved audio, or pivot to other LAN services.

**Why it happens:**
Cards come from public repositories, Discord drops, random pastes. The ecosystem has no signing. SillyTavern itself has had vulnerability reports in this area. Character cards routinely use Markdown with HTML fragments (style, tables); a naive dev turns on `dangerouslySetInnerHTML` or `v-html` to "make it render nicely" and bypasses the framework's default escaping.

**How to avoid:**
- Never render card fields as raw HTML. Render as plain text, or through a strict Markdown pipeline (`marked` with `sanitize: true` + DOMPurify, or `micromark` without HTML extensions).
- Strip or sandbox `<script>`, `<iframe>`, `<object>`, `<embed>`, event handlers (`onclick=`, `onerror=`), and `javascript:` URIs.
- Validate card JSON against a schema before storing. Unknown fields → drop (don't merge blindly into the DB).
- PNG-embedded cards: validate tEXt/chara chunk base64, decode as JSON, schema-validate. Reject malformed chunks.
- CSP on the web app: `default-src 'self'`, no `unsafe-inline`. This is defense in depth against rendering mistakes.

**Warning signs:**
- Devtools shows `innerHTML=` or `v-html=` in the character-rendering components.
- Any card from the internet renders with *styled* text — means HTML is leaking through.
- Running a known-malicious card (embed `<img src=x onerror=alert(1)>` in description) pops an alert.

**Phase to address:** Character management phase, during import path implementation.

---

### Pitfall 15: Sillytavern v2 vs v3 card format differences trip the importer

**Severity:** Medium (High for user frustration if broken)

**What goes wrong:**
Importer works for v2 cards, user drops a v3 card, fields go missing or the character looks broken. Or vice versa. Or the PNG tEXt chunk uses a different key (`chara` vs `ccv3`) and the importer reads from the wrong one.

**Why it happens:**
- V2 puts the JSON in a tEXt chunk keyed `chara`. V3 may use `ccv3` as a new chunk alongside the legacy `chara` for back-compat.
- V3 introduces `character_book` (lorebook), `depth_prompt`, new group fields, alternate greetings arrays, asset references, and extension metadata.
- SillyTavern itself typically writes both chunks so cards are backwards compatible; not all third-party tools do.

**How to avoid:**
- Implement parsers for both v2 and v3. For PNG imports: try `ccv3` first, fall back to `chara`.
- Normalize to a single internal character shape, not raw card JSON. Preserve original JSON as a blob for round-trip export.
- Gracefully handle missing/optional fields — v3 fields absent in v2 should default sanely. Don't crash on missing `alternate_greetings`.
- Support JSON import too (not every card comes as a PNG).
- Unit test with a corpus of real cards from public repos (v2 and v3) before shipping.

**Warning signs:**
- Imported character has blank description or personality in the editor.
- Some cards import fine, others produce garbled fields.
- PNG card imports work but exports don't round-trip.

**Phase to address:** Character management phase.

---

### Pitfall 16: CORS / WebSocket origin checks mis-configured across the three-service topology

**Severity:** Medium

**What goes wrong:**
Web UI is served from `https://rayme.local`. Browser tries to POST to AI backend at `https://ai.local:8001` and open a WebSocket for audio streaming. Browser blocks the cross-origin fetch (no CORS header) or the WS handshake (no origin check). Dev sets `Access-Control-Allow-Origin: *` to make it "just work," which silently permits any origin on the LAN to use the AI backend.

**Why it happens:**
- Three independent services are specifically in scope (Web UI, AI backend, LLM). That means cross-origin is the norm, not the exception.
- CORS for regular fetches is well-documented. CORS-like policy for WebSockets is *not* — browsers don't block cross-origin WS, they just send the `Origin` header and it's the server's job to check. Many devs skip the check.

**How to avoid:**
- Explicit CORS config on the AI backend: allow-list the Web UI origin(s), including the `https://` scheme and specific host(s). Do not use `*` if credentials or tokens ever travel.
- Validate `Origin` header on every WebSocket upgrade request; reject unknown origins.
- Make the allow-list configurable (env var / settings) so users on different LAN hostnames can adapt.
- Surface misconfigurations loudly: if the Web UI fails to connect, the error should say "AI backend rejected origin X" not "network error."

**Warning signs:**
- Opening dev tools shows CORS errors on the first backend call.
- WebSocket connects from *any* machine on the LAN regardless of UI origin.

**Phase to address:** Backend/API phase. Set the pattern before adding more endpoints.

---

### Pitfall 17: Services bound to `0.0.0.0` expose more than the LAN

**Severity:** Medium

**What goes wrong:**
Dev sets Flask/FastAPI/etc. to listen on `0.0.0.0` for LAN access. Box is also on a Tailscale tailnet, a work VPN, or a dual-NIC setup (Wi-Fi + Ethernet). Service is now reachable from networks that were not intended. No auth (by design) means anyone who finds the port has full access to a GPU that will cheerfully generate voice clones of anyone.

**Why it happens:**
`0.0.0.0` is the standard "listen on all interfaces" sentinel; most frameworks recommend it. It's easy to forget that "all interfaces" includes more than the home LAN on many home machines.

**How to avoid:**
- Bind to the specific LAN interface IP explicitly (e.g., `192.168.1.10`), or use a reverse proxy with strict `allow` rules (nginx `allow 192.168.1.0/24; deny all;`).
- Document the threat model explicitly: "LAN = trusted. If your LAN isn't trusted, this app isn't safe."
- If Tailscale is in use, bind *only* to the tailnet interface and treat that as the trusted network instead.
- OS firewall rules as defense in depth (Windows Firewall: allow inbound only from LAN subnet).

**Warning signs:**
- `netstat` / `ss` shows services on 0.0.0.0.
- The tailnet interface exposes services you didn't mean to expose.

**Phase to address:** Deployment / backend phase.

---

### Pitfall 18: Web-UI framework picked makes importing the Stitch HTML design painful

**Severity:** Medium

**What goes wrong:**
Framework is picked (say, heavy SSR React, or a templating system that requires a build step per file). Stitch design package is hand-crafted HTML with inline Tailwind-like styles. Porting is a slog of re-writing each screen instead of reusing the export. Design-to-code fidelity drifts.

**Why it happens:**
The Stitch export is pragmatic HTML, often with utility CSS and Font Awesome / heroicons. A framework that insists on a component model, a different CSS stack, or server components introduces friction that doesn't pay off for a single-user app.

**How to avoid:**
- Match the framework to the design export. If Stitch produces Tailwind-flavored HTML, use a framework that ingests Tailwind natively (Next.js, Astro, SvelteKit, Vite + any of them).
- Start by literally pasting one Stitch screen into the chosen framework. If that takes more than an hour, reconsider the framework.
- Use CSS-module / utility-class approaches that match the export; avoid `styled-components`-style runtime CSS if the export is static.
- Keep the design system tokens (colors, radii, fonts from DESIGN.md) in one place (CSS variables or a Tailwind config) so tweaks don't fragment.

**Warning signs:**
- First screen port takes a full day.
- Stitch screenshots and rendered app diverge within days.

**Phase to address:** Web UI setup phase, before any screen is implemented.

---

### Pitfall 19: Pipecat or LiveKit Agents is chosen, then fights the three-service LAN topology

**Severity:** Medium

**What goes wrong:**
Team reaches for Pipecat or LiveKit to "handle the hard parts." Both assume a WebRTC-first, SFU-style topology with a central orchestrator colocated with media. RayMe's topology is three services on a LAN, no WebRTC SFU, no cloud turn server, LLM possibly on a fourth machine. Adopting either framework forces architectural decisions (SFU, ICE, TURN, their component abstractions) that don't match the actual deployment. Result: fighting the framework.

**Why it happens:**
These frameworks are excellent for production voice agents with cloud telephony / WebRTC rooms. Their complexity and opinions are investments that pay off at scale. At single-user LAN scale, the overhead dwarfs the benefit.

**How to avoid:**
- For v1: build the pipeline directly. STT, TTS, VAD, LLM orchestration, barge-in state machine — all hand-rolled in the AI backend, exposing a WebSocket to the Web UI.
- Use small libraries for individual concerns (silero-vad, faster-whisper, the TTS engine) — not a mega-framework.
- If future scale demands (multi-user, cloud, WebRTC turn-server setups), revisit framework adoption then. Not now.
- If a framework is adopted anyway, verify: Can it run **without** a media server? Can it proxy audio over plain WebSocket? Is the dependency footprint acceptable?

**Warning signs:**
- Framework setup consumes more time than the actual features being built.
- Tutorials assume a cloud account / SFU deployment that doesn't fit.
- Simple changes (e.g., "show partial captions") require bending framework abstractions.

**Phase to address:** Architecture / backend phase, before implementation.

---

## Medium-Severity Pitfalls

### Pitfall 20: Saved audio files grow unbounded; metadata corruption if the service is killed mid-write

**Severity:** Medium

**What goes wrong:**
AI audio is saved by default. After 3 months, the storage directory is 40 GB and the metadata index (SQLite? JSON file?) has two orphan pointers because the service crashed during a write. Opening the chat shows missing audio clips or the app hangs indexing the directory on startup.

**Why it happens:**
Home machines reboot, crashes happen, power outages happen. A naive design writes the audio file, then writes the index, then commits — with no atomicity. Over time, orphans accumulate.

**How to avoid:**
- Use SQLite (or similar) with a single transaction that writes both the file-path reference and the message row. Use WAL mode for crash safety.
- Write audio to a temp filename, fsync, rename into place (atomic on POSIX; CreateFile + MoveFileEx on Windows). Only then commit the DB row.
- Background reaper: on startup, scan the audio dir vs the DB; delete orphans, flag dangling pointers.
- Cap per-chat retention (e.g., "keep the last 30 days of audio, older chats keep transcript only"). Expose as a setting.
- Storage size shown in Settings so user knows what they're using.

**Warning signs:**
- Disk fills up mysteriously after a couple months of use.
- Playing back an old audio clip shows "file not found" or the app hangs.
- Startup gets slower as data grows.

**Phase to address:** Chat / storage phase.

---

### Pitfall 21: Bluetooth headset / AirPods routing quirks on iOS break mic capture or output

**Severity:** Medium

**What goes wrong:**
User starts call on iPhone with AirPods. Once `getUserMedia` is granted, iOS Safari re-routes audio output to the *built-in speaker* (ignoring AirPods), then the AirPods mic picks up the speaker, creating echo. Or the mic comes back as empty/zero bytes when using AirPods. Or disconnecting AirPods mid-call doesn't re-route mic input.

**Why it happens:**
iOS Safari's `getUserMedia` implementation has known issues with Bluetooth audio routing; `setSinkId()` is not supported on iOS Safari; `enumerateDevices()` often doesn't list Bluetooth mics as selectable inputs.

**How to avoid:**
- Detect iOS Safari explicitly and display a "known limitation" note in the Voice Call UI: "Wired headphones recommended on iPhone; AirPods may not route correctly."
- Do not rely on `setSinkId()`; don't even implement output-device selection on mobile.
- On disconnect events (`devicechange` event), warn the user and offer to re-start the call.
- Test the specific hardware the builder will use (AirPods Pro / whatever) — quirks are device-specific.

**Warning signs:**
- Testers on iPhone report "no sound" or "I hear myself."
- Audio suddenly goes through speakers when mic activates.

**Phase to address:** Mobile testing phase, part of the Web UI validation cycle.

---

### Pitfall 22: Screen-off / background-tab behavior on iOS interrupts the AudioContext and the call silently drops

**Severity:** Medium

**What goes wrong:**
User locks screen during a call. iOS suspends the tab. `AudioContext` state becomes `interrupted`. WebSocket disconnects (or the mic track stops). User unlocks — call is dead, audio doesn't resume, UI is confused.

**Why it happens:**
iOS aggressively suspends background web content to save battery. Web apps don't get the AV Foundation background audio entitlements that native apps have. There's no "keep this web call running behind the lock screen" escape hatch for a self-hosted non-PWA web app.

**How to avoid:**
- Accept the limitation: the call lives as long as the tab is frontmost.
- Use Wake Lock API to keep the screen from sleeping during an active call (supported in iOS Safari 16.4+).
- Handle `visibilitychange` / `AudioContext` `statechange` events: if suspended during a call, pause everything cleanly, show a "Call paused — tap to resume" overlay instead of dying silently.
- For screen-off: don't fight it; gracefully end the call and preserve the transcript. Make resume-after-sleep reliable even if the call itself ended.

**Warning signs:**
- Putting the phone down during a call kills the audio with no UI change.
- User returns to the app and finds stale UI, broken playback.

**Phase to address:** Mobile Web UI phase.

---

### Pitfall 23: First-token latency dominates; sentence-boundary extraction from the LLM stream is done lazily

**Severity:** Medium (already addressed in Pitfall 4 but worth separating)

**What goes wrong:**
Naive pipeline: LLM streams tokens → buffer full reply → send to TTS. Total latency = LLM full generation + TTS full synthesis. For a 40-word reply that's multiple seconds. Breaks the "phone call" feel even if individual components are fast.

**Why it happens:**
It's the default and simplest pattern. Splitting token streams into sentence chunks at the right granularity takes deliberate effort, and handling punctuation edge cases is fiddly (abbreviations: "Dr. Who said..." — is "Dr." a sentence end?).

**How to avoid:**
- Extract at sentence boundaries (`. ! ?`) with a lookahead that catches common abbreviations (`Mr.`, `Dr.`, `Ms.`, `Mrs.`, `Jr.`, `Sr.`, `vs.`, `i.e.`, `e.g.`).
- Send the first sentence to TTS the moment the boundary is recognized — don't wait for the next token.
- If the first sentence is very short (≤3 words) and no second boundary arrives within 150ms, consider sending it anyway to minimize TTFA.
- Bias the system prompt: "Start every response with a brief acknowledgment." This shortens first-chunk latency structurally.

**Warning signs:**
- TTFA is greater than 1s despite individual components being fast.
- Captions populate noticeably before audio starts.

**Phase to address:** AI backend pipeline phase.

---

### Pitfall 24: Assumption that desktop Chrome behavior = mobile Safari behavior

**Severity:** Medium

**What goes wrong:**
Dev ships a build that works on desktop Chrome, tests on iPhone for the first time at milestone demo, finds five different broken things (Pitfalls 2, 3, 21, 22, plus codec differences). Delays ship.

**Why it happens:**
Desktop Chrome is the most permissive major browser for audio APIs. iOS Safari is the most restrictive. A working desktop-Chrome build gives a false positive for mobile readiness.

**How to avoid:**
- Test on actual iPhone (iOS Safari) and actual Android (Chrome) in every meaningful PR / phase gate, not just at the end.
- Set up a dedicated test device or at minimum keep BrowserStack / real-device testing in the loop.
- Maintain a "mobile parity checklist" for each feature (mic capture, audio playback, caption rendering, background behavior).

**Warning signs:**
- "Let me just check it on my phone" becomes a thing you keep deferring.
- Discovery of mobile-specific bugs is bunched at phase ends instead of spread throughout.

**Phase to address:** Every phase with any UI or audio work.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip TLS on LAN in dev | "I just want to test the mic on my phone real quick" | Pitfall 2 fires at demo time; weeks of re-trusting certs on every device | Never — set up mkcert or Tailscale once on day one |
| `dangerouslySetInnerHTML` for character descriptions | Markdown/HTML in cards renders prettily | XSS (Pitfall 14) on first malicious card | Never — use a sanitized renderer from the first implementation |
| Hardcode TTS engine (e.g., just F5, just XTTS) | Ship one engine path faster | Any engine swap = rewrite; license changes trap you | MVP if you are 100% sure engine will not change — false confidence |
| Load both TTS engines at startup | No swap latency between voices | OOM at runtime on 12GB 3060 (Pitfall 7) | Only if peak VRAM is measured and headroom exists |
| "LAN is safe, no auth" as rationalization for ignoring origin checks | Saves a config file | Any LAN compromise = full access; Pitfalls 16, 17 | Documented threat model where the user understands and accepts |
| Build with desktop Chrome only, defer mobile testing | Velocity in early phases | Late-stage mobile horror show | Never for this project — mobile is in the core requirements |
| Use the abandonware `TTS` package | `pip install TTS` works today | Breaks on next Python upgrade | Never — use `coqui-tts` fork |
| Endpoint with a fixed 700ms silence timeout | Simple | Feels slow; accented speech pauses get cut off | Phase 1 MVP only, tune immediately in next iteration |
| Client closes SSE stream and moves on | "Cancel" button works from user POV | LLM keeps generating on GPU (Pitfall 8) | Never — always propagate abort to the backend |
| Serve audio files from a flat directory with no index | Works for the first week | Orphans, corruption, slow startup (Pitfall 20) | Never — SQLite or equivalent from the start |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenAI-compatible LLM (llama-server, LM Studio, OpenAI API) | Assume all support true mid-stream cancellation | Verify each backend cancels on connection close; ship with a known-good server (llama-server recommended) |
| F5-TTS | Hand STT transcript to F5 unedited | Always let the user edit; validate transcript matches audio |
| XTTS v2 package | `pip install TTS` | `pip install coqui-tts` (idiap fork) |
| Whisper streaming | Feed all audio to Whisper, let it figure out silence | VAD-gate audio; Whisper only sees probable speech |
| Browser audio playback | Raw PCM decoded into AudioContext buffers | Playback through `<audio>` or `MediaStreamAudioDestinationNode` so browser AEC sees it |
| SillyTavern PNG cards | Read `chara` chunk only | Try `ccv3` first, fall back to `chara`; validate both against schema |
| WebSocket from Web UI to AI backend | No `Origin` check on server | Validate origin on WS upgrade, allow-list explicitly |
| Tailscale + local binding | Bind to `0.0.0.0` | Bind to the specific tailnet or LAN interface |
| Self-signed HTTPS | Show the warning click-through | On iOS, install Root CA as Configuration Profile and enable trust; or use mkcert/Tailscale |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Whisper large-v3 at fp16 always loaded | VRAM near cap; occasional OOM | Default to distil-large-v3 int8 via faster-whisper | Any session where both TTS engines also need to coexist |
| TTS synthesized full-sentence before playback | Time-to-first-audio >1s | Stream per-sentence; bias LLM to short openers | Any reply longer than ~6 words |
| No VAD gate before Whisper | Hallucinations on silence; GPU time wasted on non-speech | Silero VAD as preprocessing layer | Every call in a noisy environment |
| Fixed endpointing threshold | Either cut-off or laggy | Adaptive endpoint based on turn context | Accented speech, thoughtful users |
| Loading both F5 and XTTS simultaneously | VRAM contention on 3060 | Lazy-load; swap between voices with engine | Long sessions, multi-voice usage |
| Long reference audio (>20s) in F5 | Truncated / malformed output | Cap at 15s in UI | Voice Lab uploads |
| CUDA allocator fragmentation | VRAM drifts up over hours | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; periodic `empty_cache` | Multi-hour sessions |
| Unbounded audio file storage | Disk fills | Retention policy + cleanup reaper | Multi-month usage |
| No mid-stream LLM cancel | GPU wasted on interrupted generations | Propagate abort through backend | Frequent barge-ins |

## Security Mistakes

Within the threat model (single-user, LAN-trusted, no auth), security pitfalls are narrower but still real:

| Mistake | Risk | Prevention |
|---------|------|------------|
| Rendering character card fields as HTML | XSS from malicious cards → exfiltration / pivot to other LAN services | Strict text/markdown rendering; CSP; DOMPurify |
| Binding to `0.0.0.0` on multi-interface box | Services exposed to VPN / tailnet / Wi-Fi-public when only LAN was intended | Bind to specific interface; OS firewall rules |
| `Access-Control-Allow-Origin: *` on AI backend | Any malicious page on any LAN device can drive the GPU | Explicit allow-list of Web UI origins |
| No WebSocket origin check | Same as above, for WS endpoints | Validate `Origin` header on upgrade |
| Saving mic audio by default | Privacy violation if the builder later shares the machine | Mic audio off by default (already in requirements — verify) |
| Storing voice clones with weak filenames or public paths | Voice clone data leakage | Clones in a protected dir; no public URLs |
| Trusting LLM output in system UI | Prompt injection from character cards causes LLM to emit misleading UI content | Treat LLM outputs as untrusted; escape before rendering |
| Untrusted PNG chara chunks cause parser crashes | DoS / memory exhaustion | Validate chunk size + schema before decoding |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No visual indication that the AI is listening | User thinks it's frozen; speaks louder, triggers false barge-in | Live partial captions; mic-level indicator |
| TTS cuts off silently on barge-in with no fade | Jarring; feels buggy | 50–100ms fade-out on barge-in cancellation |
| Voice Lab auto-accepts the STT transcript | User saves a broken voice, doesn't know why clone is bad | Force a "review transcript" step; play synth preview before save |
| Only show captions after the AI finishes speaking | Deaf/HoH users can't follow; also slows troubleshooting | Stream captions as TTS plays |
| Character picker shows default voice with no indication another voice is active for this chat | User confused about why the voice changed | Clearly label per-chat voice override in the UI |
| No feedback during HTTPS/cert trust failures | "Nothing works on my phone" | Precheck `window.isSecureContext` and show actionable error with link to setup docs |
| Long first-call setup (certs, permissions, voice creation) with no progress indication | User gives up before first call | Linear onboarding flow with persistent setup checklist |
| Mic permission prompt shown before any explanation | Permission denied, now gated forever | Explain why before the first `getUserMedia` call |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Mobile audio:** Works on desktop Chrome — verify on iOS Safari with real cert trust, AirPods, screen-off.
- [ ] **Barge-in:** Cancels TTS — verify next-turn STT captures the first word (Pitfall 11), no ping-pong (Pitfall 1), no false trigger on breath (Pitfall 10).
- [ ] **STT:** Transcribes speech — verify accent (Spanish-accented English) WER, no hallucinations on silence, endpointing feels natural.
- [ ] **TTS:** Produces voice — verify first-audio latency <800ms, quality consistent across reference audios, F5 transcript edit path works.
- [ ] **Character import:** Loads cards — verify v2 JSON, v3 JSON, v2 PNG (chara), v3 PNG (ccv3), malformed input rejected, no XSS.
- [ ] **Voice Lab:** Saves voices — verify auto-transcript appears, user can edit, test synthesis preview plays before save.
- [ ] **LLM cancellation:** Stop button works from UI — verify GPU usage actually drops (Pitfall 8); not just client-side abort.
- [ ] **LAN HTTPS:** Serves from HTTPS — verify cert trusted on every device type the user owns; fail-loud on `http://`.
- [ ] **Service topology:** Three services talk — verify CORS + WS origin explicitly set, no `*` wildcards, bound to correct interface.
- [ ] **VRAM:** Fits at 12GB — verify 30-minute stress test with both TTS engines cycled, memory stable, no OOM.
- [ ] **Storage:** Saves audio — verify SIGKILL mid-write does not corrupt the index; reaper cleans orphans.
- [ ] **Per-chat voice:** Selectable — verify default vs override displays correctly; chat continuation preserves selection.
- [ ] **Captions:** Live both sides — verify user partials update in real time during speech, AI captions stream with TTS.
- [ ] **Chat continuity:** Calls and text share a thread — verify interleaved ordering, transcript format, resume-after-call state.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Echo loop (#1) | HIGH | Add playback-gate; verify AEC is honored; consider routing TTS via `<audio>`; worst case, require headphones for now |
| HTTPS broken on device (#2) | MEDIUM | Switch to Tailscale tailnet cert (fastest path) or re-issue via mkcert and install Root CA |
| AudioContext not playing on iOS (#3) | LOW | Ensure create/resume inside a click handler; add silent-buffer unlock |
| F5 non-streaming TTFA too high (#4) | MEDIUM | Implement sentence-boundary streaming; bias LLM to short first sentences; fall back to XTTS v2 which streams natively |
| STT endpoint misbehaving (#5) | MEDIUM | Tune VAD thresholds; add word-count gate; add adaptive endpoint based on context |
| Whisper hallucinations (#6) | LOW | Add Silero VAD gate + `condition_on_previous_text=False` + hallucination blocklist filter |
| VRAM OOM (#7) | MEDIUM | Swap to distil-large-v3 int8; lazy-load TTS engines; enable `expandable_segments` |
| LLM cancel leak (#8) | MEDIUM | Replace LLM client with one that supports proper cancel; verify with `nvidia-smi` |
| F5 bad voice clone (#9) | LOW | Force transcript review in Voice Lab; cap reference audio length; recorded-quality hints |
| False barge-in (#10) | LOW | Add minimum-duration gate + word-count gate + energy threshold |
| Race on TTS/user-turn boundary (#11) | MEDIUM | Add perceived-playback-end timestamp from browser; suppress server-side VAD during pad window |
| XSS from card (#14) | LOW if caught early / HIGH if shipped | Replace HTML renderer with sanitized pipeline; audit existing stored cards; add CSP header |
| Service on wrong interface (#17) | LOW | Reconfigure binding; add OS firewall rule; restart service |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| #1 Echo loop | Duplex/barge-in | Dogfood 10-min call on speakers; no AI self-interrupts |
| #2 HTTPS / cert trust | Web UI setup / deployment | Mobile test on the builder's iPhone day one |
| #3 AudioContext gesture | Voice Call UI | `AudioContext.state === 'running'` check on call start; play silent-buffer probe |
| #4 F5 streaming architecture | TTS integration | Time-to-first-audio <800ms measured end-to-end |
| #5 STT endpointing | STT / duplex | Tuning session with accented speech; both false-cut-off and lag below thresholds |
| #6 Whisper hallucinations | STT | VAD gate live; silence logs produce empty transcripts |
| #7 VRAM budget | AI backend (before TTS) | 30-min stress test, peak <11GB, no OOM |
| #8 LLM cancel leak | AI backend orchestration | `nvidia-smi` drops to idle ≤200ms after UI cancel |
| #9 F5 transcript error | Voice Lab | Transcript-edit UX mandatory; synth-preview before save |
| #10 False barge-in | Barge-in | Test with breath / back-channel audio; no false fires |
| #11 TTS/user-turn race | Duplex | End-to-end timing instrumentation; first-word capture test |
| #12 Coqui abandonware | TTS integration | `pip install coqui-tts` in setup docs, not `TTS` |
| #13 Non-commercial license | Project setup | LICENSES.md + README disclaimer |
| #14 Card XSS | Character management | Security test with malicious card; CSP header live |
| #15 Card v2/v3 parse | Character management | Import test corpus (both formats, PNG + JSON) |
| #16 CORS/WS origin | Backend/API | Allow-list test; rejection log visible |
| #17 Interface binding | Deployment | `ss`/`netstat` inspection; bind to specific IP |
| #18 Framework vs Stitch | Web UI setup | First screen port in <1 day |
| #19 Pipecat/LiveKit fit | Architecture | Explicit decision in ARCHITECTURE.md |
| #20 Audio storage | Chat / storage | Kill-during-write test; orphan reaper |
| #21 Bluetooth routing | Mobile UI testing | Real-device iOS AirPods test |
| #22 Screen-off behavior | Mobile UI | Lock-screen test; Wake Lock active during calls |
| #23 Sentence-boundary extraction | AI backend pipeline | TTFA measurement across reply lengths |
| #24 Mobile parity | Every UI phase | iOS Safari test in phase acceptance |

## Sources

- [F5-TTS RTF benchmark / inference speed](https://github.com/SWivid/F5-TTS/issues/81) — RTF 0.15 baseline, optimizations to 0.03
- [F5-TTS streaming request / status](https://github.com/SWivid/F5-TTS/issues/700) — Real-time streaming not yet native
- [F5-TTS reference audio truncation over 20s](https://github.com/SWivid/F5-TTS/issues/55) — Hard upper bound on reference length
- [F5-TTS injecting reference phrases](https://github.com/SWivid/F5-TTS/issues/85) — Transcript-mismatch failure mode
- [F5-TTS licensing discussion](https://github.com/SWivid/F5-TTS/discussions/997) — CC-BY-NC 4.0 and commercial ambiguity
- [Coqui shutdown and XTTS licensing clarification](https://github.com/coqui-ai/TTS/discussions/4304) — CPML non-commercial; company defunct
- [coqui-tts (idiap fork) PyPI](https://pypi.org/project/coqui-tts/) — Maintained fork to use today
- [idiap/coqui-ai-TTS GitHub](https://github.com/idiap/coqui-ai-TTS) — Active maintenance
- [iOS Safari self-signed cert trust requirements](https://blog.httpwatch.com/2013/12/12/five-tips-for-using-self-signed-ssl-certificates-with-ios/) — Root CA install + trust toggle
- [iOS compatible self-signed SSL for LAN](https://barefootwebdesign.co.nz/blog/ios-compatible-self-signed-ssl-certificate/) — .home.arpa / mkcert patterns
- [AudioContext user-gesture unlock pattern](https://www.mattmontag.com/web/unlock-web-audio-in-safari-for-ios-and-macos) — Canonical iOS unlock idiom
- [WebKit AudioContext background behavior](https://bugs.webkit.org/show_bug.cgi?id=231105) — Stops on minimize/background
- [MDN Autoplay guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay) — Secure-context + gesture requirements
- [Echo cancellation breakdown in browser voice agents](https://dev.to/remi_etien/i-built-a-voice-ai-with-sub-500ms-latency-heres-the-echo-cancellation-problem-nobody-talks-about-14la) — Browser AEC doesn't see custom-decoded audio
- [Deepgram voice agent echo cancellation](https://developers.deepgram.com/docs/voice-agent-echo-cancellation) — Self-interrupt failure mode
- [Hamming debug guide for WebRTC voice agents](https://hamming.ai/resources/debug-webrtc-voice-agents-troubleshooting-guide) — Full-duplex troubleshooting
- [Silero VAD GitHub](https://github.com/snakers4/silero-vad) — Performance, MIT license
- [Silero VAD with Whisper / barge-in pipelines](https://medium.com/@aidenkoh/how-to-implement-high-speed-voice-recognition-in-chatbot-systems-with-whisperx-silero-vad-cdd45ea30904) — Pre-gate pattern
- [Whisper hallucination on silence](https://github.com/openai/whisper/discussions/1606) — Issue history
- [Whisper hallucination on non-speech audio (arXiv)](https://arxiv.org/html/2501.11378v1) — Academic analysis
- [Calm-Whisper — reducing non-speech hallucinations](https://arxiv.org/html/2505.12969v1) — Fine-tuning decoder heads mitigation
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 speed/memory benefits
- [Choosing Whisper variants](https://modal.com/blog/choosing-whisper-variants) — distil-large-v3 int8 memory footprint
- [distil-whisper GitHub](https://github.com/huggingface/distil-whisper) — 6× faster, 1% WER gap
- [Whisper endpointing discussion (Deepgram)](https://developers.deepgram.com/docs/understanding-end-of-speech-detection-while-streaming) — Endpointing strategies
- [LLM streaming cancellation — litellm tracking issue](https://github.com/BerriAI/litellm/issues/17364) — Cancel-on-disconnect not universal
- [LM Studio streaming cancel bug](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1203) — Immediate-cancel fails
- [Twilio core latency guide for voice agents](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents) — TTFT-dominated latency budget
- [Dograh: LiveKit vs Pipecat vs Dograh](https://blog.dograh.com/ai-voice-agents-github-proven-guide-dograh-vs-livekit-vs-pipecat/) — Framework fit for different topologies
- [Pipecat architectural trade-offs (Arun Baby)](https://www.arunbaby.com/ai-agents/0018-voice-agent-frameworks/) — When frameworks help vs hurt
- [SillyTavern GitHub - card management / chunks](https://deepwiki.com/SillyTavern/SillyTavern/5.1-character-management) — v2/v3 chunk structure
- [SillyTavern authentication & security](https://deepwiki.com/SillyTavern/SillyTavern/2.4-authentication-and-security) — Known security posture
- [SillyTavern CVE listing](https://app.opencve.io/cve/?vendor=sillytavern) — Documented vulnerabilities
- [iOS Safari AirPods routing limitations](https://medium.com/@python-javascript-php-html-css/ios-safari-forces-audio-output-to-speakers-when-using-getusermedia-2615196be6fe) — Speaker re-route on mic activation
- [WebRTC Bluetooth audio routing issues on iOS](https://www.webrtc-developers.com/using-homepod-mini-and-airpods-with-webrtc/) — AirPods discovery gaps

---
*Pitfalls research for: Self-hosted real-time voice AI calls (RayMe)*
*Researched: 2026-04-16*
