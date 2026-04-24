# RayMe External LLM Configuration

RayMe does not ship local inference. Phase 1 treats the LLM as an external
OpenAI-compatible Chat Completions endpoint, reached only by the RayMe Web UI
server.

## Runtime Contract

- The browser never calls the LLM endpoint directly.
- The Web UI server keeps the base URL, API key, and model name server-side.
- Phase 1 LLM status is checked with `POST /api/settings/test/llm`.
- A local server such as `llama-server` is valid when it exposes an
  OpenAI-compatible Chat Completions API.

## Settings

Configure these values on the Web UI server:

```env
RAYME_LLM_BASE_URL=https://api.openai.com/v1
RAYME_LLM_API_KEY=
RAYME_LLM_MODEL=gpt-4.1-mini
```

Use `llm/openai-compatible.example.env` as the minimal environment-file shape.
Keep `RAYME_LLM_API_KEY` blank in committed examples and set it only in the
server runtime environment.

## Settings Test

The Settings screen should call `POST /api/settings/test/llm`. That server-side
probe confirms the configured OpenAI-compatible endpoint can answer without
requiring a RayMe-owned LLM `/health` service.
