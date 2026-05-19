---
phase: quick-qwen-disable-thinking-chat
plan: 260519-nnw
type: execute
wave: 1
depends_on: []
files_modified:
  - web-ui/server/app/api/chat.py
  - web-ui/server/app/api/messages.py
  - web-ui/server/tests/test_chat_stream.py
  - web-ui/server/tests/test_message_actions.py
autonomous: true
requirements:
  - QUICK-QWEN-CHAT-01
must_haves:
  truths:
    - "The existing llm_disable_thinking setting affects normal non-call chat sends."
    - "The same setting affects non-call chat message actions that generate LLM text."
    - "Qwen thinking is still disabled only through the existing Qwen-aware llm_stream behavior."
    - "Existing live-call generation behavior is preserved."
  artifacts:
    - path: "web-ui/server/app/api/chat.py"
      provides: "Normal chat send passes endpoint_settings.llm_disable_thinking into ChatCompletionSettings."
      contains: "disable_thinking=endpoint_settings.llm_disable_thinking"
    - path: "web-ui/server/app/api/messages.py"
      provides: "Regenerate, swipe, edit, and continue actions pass endpoint_settings.llm_disable_thinking into ChatCompletionSettings."
      contains: "disable_thinking=endpoint_settings.llm_disable_thinking"
    - path: "web-ui/server/tests/test_chat_stream.py"
      provides: "Route-level regression for normal chat setting propagation."
    - path: "web-ui/server/tests/test_message_actions.py"
      provides: "Route-level regression for message action setting propagation."
  key_links:
    - from: "web-ui/server/app/api/chat.py"
      to: "web-ui/server/app/domain/settings_service.py"
      via: "SettingsService(session, runtime_settings).read()"
      pattern: "endpoint_settings\\.llm_disable_thinking"
    - from: "web-ui/server/app/api/messages.py"
      to: "web-ui/server/app/domain/llm_stream.py"
      via: "ChatCompletionSettings.disable_thinking"
      pattern: "disable_thinking=endpoint_settings\\.llm_disable_thinking"
---

<objective>
Make the existing RayMe "Disable Qwen thinking" setting apply to non-call chat, not only live-call LLM generation.

Purpose: Users expect the Settings toggle to control Qwen thinking behavior consistently for text chat and calls.

Output: Focused server route wiring plus regressions proving the setting reaches normal chat sends and chat message actions.

User-goal preservation: preserve existing live-call behavior and do not change call, TTS, STT, VAD, WebRTC, reconnect, call UI, or deployment paths.
</objective>

<execution_context>
@/home/agent/.codex/get-shit-done/workflows/execute-plan.md
@/home/agent/.codex/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md
@.planning/LIVE-CALL-INVARIANTS.md
@web-ui/server/app/domain/settings_service.py
@web-ui/server/app/domain/llm_stream.py
@web-ui/server/app/api/calls.py
@web-ui/server/app/api/chat.py
@web-ui/server/app/api/messages.py
@web-ui/server/tests/test_chat_stream.py
@web-ui/server/tests/test_message_actions.py

<interfaces>
Existing contracts to use directly:

```python
# web-ui/server/app/domain/settings_service.py
@dataclass(frozen=True, slots=True)
class EndpointSettings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_disable_thinking: bool
```

```python
# web-ui/server/app/domain/llm_stream.py
@dataclass(frozen=True, slots=True)
class ChatCompletionSettings:
    base_url: str
    model: str
    api_key: str | None = None
    disable_thinking: bool = False
```

```python
# web-ui/server/app/domain/llm_stream.py
def _should_disable_thinking(settings: ChatCompletionSettings) -> bool:
    return settings.disable_thinking and "qwen" in settings.model.lower()
```

Live-call reference: `web-ui/server/app/api/calls.py` already passes
`disable_thinking=endpoint_settings.llm_disable_thinking` into
`ChatCompletionSettings`. Keep that behavior unchanged.
</interfaces>

<source_audit>
| Source | Item | Coverage |
|--------|------|----------|
| GOAL | Existing Qwen disable-thinking setting also affects non-call chat. | Tasks 1 and 2 cover `/api/chat/{thread_id}/send` and `/api/messages/*` action routes. |
| CONTEXT | Preserve live-call behavior. | Task 2 explicitly avoids call/TTS/STT/WebRTC files and runs a focused call-turn regression. |
| CONTEXT | Prefer existing settings and LLM streaming patterns. | Task 2 uses `SettingsService.read()` and `ChatCompletionSettings.disable_thinking`; no new config is introduced. |
| CONSTRAINT | Single quick plan, no research phase. | This file is one autonomous execute plan with two tasks. |
</source_audit>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add non-call chat setting propagation regressions</name>
  <files>web-ui/server/tests/test_chat_stream.py, web-ui/server/tests/test_message_actions.py</files>
  <behavior>
    - Normal chat: when persisted or runtime endpoint settings use `llm_model="unsloth/Qwen3.5-27B"` and `llm_disable_thinking=True`, the scripted completion client receives `ChatCompletionSettings(..., disable_thinking=True)`.
    - Normal chat: when the same Qwen model has `llm_disable_thinking=False`, the scripted completion client receives `disable_thinking=False`.
    - Message actions: at least one route-backed generation path, preferably regenerate, receives the same `disable_thinking` value from endpoint settings.
  </behavior>
  <action>
    Add route-level tests that prove the setting reaches `ChatCompletionSettings` for non-call chat. Use existing test fixtures and helper patterns in `test_chat_stream.py` and `test_message_actions.py`; if persisted settings are needed, write an `AppSetting` row using the existing `SETTINGS_KEY` shape instead of inventing a new settings path. Name the tests descriptively, for example `test_send_endpoint_forwards_qwen_disable_thinking_setting` and `test_message_action_routes_forward_qwen_disable_thinking_setting`.

    Do not test `_should_disable_thinking` by duplicating its internals here; `test_qwen_generation_can_disable_thinking` already covers the OpenAI-compatible `/no_think` and `extra_body` behavior. These new tests should cover route-to-settings wiring.
  </action>
  <verify>
    <automated>cd web-ui/server && uv run pytest tests/test_chat_stream.py::test_send_endpoint_forwards_qwen_disable_thinking_setting tests/test_message_actions.py::test_message_action_routes_forward_qwen_disable_thinking_setting -q</automated>
  </verify>
  <done>The new tests fail before production wiring because non-call routes do not forward `llm_disable_thinking`, and the failure is limited to the expected `disable_thinking` mismatch.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire existing disable-thinking setting into non-call chat routes</name>
  <files>web-ui/server/app/api/chat.py, web-ui/server/app/api/messages.py, web-ui/server/tests/test_chat_stream.py, web-ui/server/tests/test_message_actions.py</files>
  <behavior>
    - `/api/chat/{thread_id}/send` builds `ChatCompletionSettings` with `disable_thinking=endpoint_settings.llm_disable_thinking`.
    - `/api/messages/{message_id}/regenerate`, swipe, edit, and continue routes inherit the same field through `_completion_settings`.
    - Non-Qwen models keep using the same LLM stream path; the Qwen-only gate remains in `llm_stream.py`.
    - Live-call route wiring in `api/calls.py` remains unchanged.
  </behavior>
  <action>
    In `web-ui/server/app/api/chat.py`, add `disable_thinking=endpoint_settings.llm_disable_thinking` to the existing `ChatCompletionSettings` constructor in `send_chat_message`.

    In `web-ui/server/app/api/messages.py`, add the same constructor field in `_completion_settings`, so all non-call message action generation paths share the persisted setting.

    Update existing test expectations in `test_chat_stream.py` and `test_message_actions.py` where route defaults now include `disable_thinking=True`. Do not change fixtures to force the old default false; the setting default is intentionally true in `Settings`. Do not modify `web-ui/server/app/domain/llm_stream.py` unless a test exposes a real bug in the existing Qwen-aware behavior. Do not edit call, TTS, STT, VAD, WebRTC, reconnect, call UI, or deployment files.
  </action>
  <verify>
    <automated>cd web-ui/server && uv run pytest tests/test_chat_stream.py tests/test_message_actions.py tests/test_calls.py::test_two_turns_stream_tokens_and_write_exact_speech_rows_before_call_end -q</automated>
  </verify>
  <done>Normal chat sends and message actions pass the persisted Qwen disable-thinking setting into `ChatCompletionSettings`; existing Qwen stream behavior handles `/no_think` and `extra_body`; the focused call-turn regression still passes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> Web UI API | User chat content enters `/api/chat` and `/api/messages` routes. |
| Web UI API -> LLM endpoint | Server settings, including private API key and Qwen thinking flag, are used to call the configured OpenAI-compatible endpoint. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-qwen-chat-01 | I | `ChatCompletionSettings` construction | mitigate | Keep `llm_api_key` server-side only; tests must continue asserting prompt text does not include `server-secret`. |
| T-quick-qwen-chat-02 | T | `llm_disable_thinking` setting propagation | mitigate | Read the value from `SettingsService` only; do not accept per-request chat payload overrides. |
| T-quick-qwen-chat-03 | D | Chat generation route regressions | accept | Change is one boolean field in existing constructors; focused route and call-turn regressions cover the affected behavior. |
</threat_model>

<verification>
Run the focused server tests:

```bash
cd web-ui/server && uv run pytest tests/test_chat_stream.py tests/test_message_actions.py tests/test_calls.py::test_two_turns_stream_tokens_and_write_exact_speech_rows_before_call_end -q
```
</verification>

<success_criteria>
- `llm_disable_thinking=True` reaches non-call chat `ChatCompletionSettings` for Qwen-capable routes.
- `llm_disable_thinking=False` also reaches non-call chat settings, so the toggle can re-enable Qwen thinking.
- No new configuration key, route, or model-specific chat path is introduced.
- The existing live-call route still passes its focused regression.
</success_criteria>

<output>
After completion, create `.planning/quick/260519-nnw-make-the-setting-about-disabling-thinkin/260519-nnw-SUMMARY.md`
</output>
