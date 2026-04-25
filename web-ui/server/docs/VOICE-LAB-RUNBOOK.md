# Voice Lab Runbook

Voice Lab is the Phase 2 workflow for turning a short sample into a saved RayMe
voice. The browser talks to RayMe-owned Web UI server routes; the Web UI server
owns durable voice state and sends transient processing requests to the AI
backend.

## Runtime Locations

On `OMEN-PC`, use the canonical checkout and reusable TLS directory:

```text
C:\Users\pmpg\rayme\RayMe\
C:\Users\pmpg\rayme\phase1-tls\
```

Do not use copied staging trees, `C:\Users\pmpg\rayme\phase1-app\`, throwaway
certificates, or new top-level directories under `C:\Users\pmpg\`.

Phase 2 live URLs:

```text
Voice Lab: https://192.168.1.199:8443/voice-lab
AI health: https://192.168.1.199:9443/health
```

## Workflow

### 1. Upload Sample

Upload a WAV, MP3, or FLAC sample in the browser Voice Lab. The Web UI server
validates the upload and stores the original sample under an internal asset ID,
not the user's filename.

Durable sample blobs live under:

```text
web-ui/server/data/blobs/voice-samples/
```

### 2. Transcript Retry or Manual Transcript

After upload, Voice Lab asks the AI backend to transcribe the sample. If STT
returns silence, hallucination, or a sanitized failure, keep the uploaded sample
and use either:

- retry transcription
- manual transcript entry

Manual transcript entry is a normal supported path. Do not require the user to
re-upload a sample just because transcription failed.

### 3. Optional Preview

Preview is optional. This optional preview step is a convenience, not a save
gate. A failed preview must preserve the sample, voice name, manual transcript,
selected engine, default-engine setting, and preview text.
The user can retry, switch engine, edit text, or save without a successful
preview.

If future code introduces persisted preview blobs, store them only under:

```text
web-ui/server/data/blobs/voice-previews/
```

Phase 2 does not require preview blobs for save.

### 4. Save Voice

Save requires:

- uploaded sample asset
- non-empty voice name
- non-empty transcript
- selected default engine

Save does not require `preview_id`, `preview_url`, or successful synthesis.
Saved voice records keep a stable internal voice ID, mutable display name,
default engine, editable transcript, metadata, and sample asset link.

### 5. Rename

Rename changes the user-facing display name only. It must not change the stable
voice ID, default engine, transcript, or sample asset.

### 6. Force Delete

Referenced voices can be force-deleted only after explicit confirmation. In API
and test notes, this is the force delete path for referenced voices.
Deletion is a soft-delete/tombstone operation so existing character references
render `Voice unavailable` instead of crashing or silently clearing state.

Never document cleanup with globs or expanded variables. Delete only exact
paths that are known to contain disposable generated output.

### 7. Test-Play

Test-play sends a transient synthesis request through the Web UI server to the
AI backend. The AI backend returns generated audio; the Web UI server decides
what, if anything, to persist in later phases. Phase 2 test-play audio is not a
durable app-state source of truth.

## Safe Cleanup Paths

At the end of Phase 2, these paths may contain disposable Voice Lab runtime
output if the operator intentionally wants to clear saved test voices:

```text
web-ui/server/data/blobs/voice-samples/
web-ui/server/data/blobs/voice-previews/
```

The first path contains uploaded original voice samples, including samples for
saved voices. Delete it only when intentionally clearing local test voice data.
The second path is reserved for future preview blobs and may not exist yet.

Do not delete:

```text
C:\Users\pmpg\rayme\RayMe\
C:\Users\pmpg\rayme\phase1-tls\
.local/phase1-tls/
```

The Git checkout and TLS material are reusable project assets.
