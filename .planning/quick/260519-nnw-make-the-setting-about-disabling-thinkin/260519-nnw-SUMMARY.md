---
quick_task: 260519-nnw
status: complete
objective: "Make the existing Disable Qwen thinking setting apply to non-call chat sends and message actions."
completed_at: "2026-05-19T17:10:58Z"
commits:
  - "7dfbca5 test(quick-qwen-disable-thinking-chat-260519-nnw): add disable-thinking route regressions"
  - "4f70221 fix(quick-qwen-disable-thinking-chat-260519-nnw): wire disable-thinking into non-call chat"
key_files:
  - web-ui/server/app/api/chat.py
  - web-ui/server/app/api/messages.py
  - web-ui/server/tests/test_chat_stream.py
  - web-ui/server/tests/test_message_actions.py
---

# Quick Task 260519-nnw Summary

The existing `llm_disable_thinking` endpoint setting now reaches normal non-call chat generation and message-action generation through `ChatCompletionSettings.disable_thinking`.

## Changes

- Added route-level regressions for `/api/chat/{thread_id}/send` proving both `True` and `False` persisted Qwen disable-thinking values reach the scripted completion client.
- Added route-level regressions for `/api/messages/{message_id}/regenerate` proving the same persisted setting reaches message action generation.
- Wired `endpoint_settings.llm_disable_thinking` into `ChatCompletionSettings` in `web-ui/server/app/api/chat.py`.
- Wired the same field into the shared message-action `_completion_settings` helper in `web-ui/server/app/api/messages.py`.
- Updated existing route expectations for the runtime default, where `Settings.llm_disable_thinking` defaults to `True`.

## Verification

- RED gate: `cd web-ui/server && uv run pytest tests/test_chat_stream.py::test_send_endpoint_forwards_qwen_disable_thinking_setting tests/test_message_actions.py::test_message_action_routes_forward_qwen_disable_thinking_setting -q`
  - Failed as expected before production wiring on the `disable_thinking=True` cases.
- Focused GREEN gate: same command
  - Passed: `4 passed`.
- Plan verification: `cd web-ui/server && uv run pytest tests/test_chat_stream.py tests/test_message_actions.py tests/test_calls.py::test_two_turns_stream_tokens_and_write_exact_speech_rows_before_call_end -q`
  - Passed: `23 passed`.

## Deviations from Plan

None.

## Threat Notes

- No new route, request payload field, configuration key, or model-specific path was introduced.
- The LLM API key remains server-side; route tests continue asserting `server-secret` does not enter prompt text.
- Live-call route code was not modified; the focused call-turn regression passed.

## Known Stubs

None.
