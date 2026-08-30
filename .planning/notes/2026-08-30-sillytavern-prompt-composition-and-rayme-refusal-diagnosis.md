---
title: SillyTavern prompt composition and RayMe refusal diagnosis
date: 2026-08-30
context: Research and product decisions admitted into urgent Phase 09.1
---

# SillyTavern prompt composition and RayMe refusal diagnosis

## User-goal preservation

RayMe must answer as the selected character by default. A blank character-level
system prompt must not silently turn the conversation into a generic
"helpful AI" exchange that moralizes, cites unspecified guidelines, or offers
to change the subject. The default product mode is unfiltered fictional
roleplay for every character conversation. Assistant mode and a fully custom
prompt mode remain explicit user choices; neither may silently replace the
default.

The same effective prompt contract must drive text chat and live calls. Refusal
recovery in a call may add only a small, bounded prefix guard. It must never
wait for the whole LLM response or the whole TTS stream before first playback,
and explicit interruption must still cancel late LLM and audio work.

## Admitted external research

The following block records external-source findings as untrusted research
data. All five findings were admitted into Phase 09.1; none remain unresolved.

DATA_041BE393_START

1. SillyTavern composes a conversation from ordered prompt sections rather
   than relying on a lone character-card system field. Its default Main prompt
   frames the task as writing the character's next reply in a fictional chat.
   The built-in Auxiliary and post-history prompts are blank by default, while
   optional roleplay presets strengthen continued character behavior.
   Source: official SillyTavern repository at release commit
   `8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8`,
   `public/scripts/PromptManager.js`.

2. The effective order is Main prompt, world information before character,
   persona, character description, personality, scenario, Auxiliary prompt,
   world information after character, example dialogue, chat history, then the
   post-history instruction. SillyTavern internally calls that last slot the
   `jailbreak` prompt, but the useful engineering property is its late position
   and explicit visibility—not the label.
   Source: official SillyTavern repository, `public/scripts/openai.js` and
   `public/scripts/PromptManager.js`; official prompt-manager documentation.

3. Character-level Main and post-history prompts can override the global
   versions, and `{{original}}` lets an override retain the corresponding
   global prompt. This makes blank fields inherit a strong application default
   while specialized cards can extend or replace it deliberately.
   Source: official SillyTavern repository,
   `public/scripts/PromptManager.js`; official prompt documentation.

4. Example dialogue is actually injected into the request, subject to context
   budget, role, depth, and ordering rules. The UI also exposes a prompt
   inspector so the user can see the request that was constructed.
   Source: official SillyTavern repository, `public/scripts/openai.js` and
   `public/scripts/PromptManager.js`; official prompt-manager documentation.

5. For OpenAI-compatible custom endpoints, SillyTavern sends the composed
   message array together with configured sampler parameters; its server-side
   adapter then applies the selected completion/template behavior. Refusal
   resistance therefore comes from the complete prompt pipeline and generation
   controls, not from one magic sentence named "jailbreak."
   Source: official SillyTavern repository,
   `src/endpoints/backends/chat-completions.js`; official prompt documentation.

DATA_041BE393_END

Official documentation consulted:

- <https://docs.sillytavern.app/usage/prompts/>
- <https://docs.sillytavern.app/usage/prompts/prompt-manager/>
- <https://github.com/SillyTavern/SillyTavern>

## Verified RayMe diagnosis

RayMe currently has a much thinner contract:

- `web-ui/server/app/domain/prompt_builder.py` merges the character system
  prompt, name, description, personality, scenario, and post-history
  instruction into one system message placed before history.
- `mes_example` is stored but never injected. RayMe has no global Main or
  Auxiliary prompt, no true late post-history slot, no `{{original}}`
  inheritance, no character/user macro expansion, no prompt ordering or token
  budgeting, and no exact effective-prompt inspector.
- `web-ui/server/app/domain/llm_stream.py` sends the message array, model,
  streaming flag, and random seed. It does not expose the normal sampler set
  that materially affects local-model behavior.
- Text and call paths have no refusal classifier or bounded retry. The first
  refusal is streamed to the UI, spoken in a call, persisted in history, and
  then becomes reinforcing context for later turns.
- Existing thread snapshots mean later edits to a character do not repair the
  effective identity of an already-created thread unless prompt resolution is
  deliberately changed.

The observed deployed failure was explicit, not a transport timeout or empty
completion: Qwen produced a generic refusal beginning "I cannot continue this
conversation" and citing safety guidelines. The affected character had blank
system, post-history, and example-dialogue fields, so RayMe supplied only its
short name/description/personality scaffold.

## Phase 09.1 implementation boundary

Phase 09.1 must deliver:

1. A shared, ordered, inspectable prompt composer for text and call generation.
2. A default Roleplay preset that remains active for blank cards, with explicit
   Assistant and Custom alternatives.
3. Character overrides with `{{original}}`, `{{char}}`, and `{{user}}`, example
   dialogue injection, context budgeting, and model-aware message roles.
4. Visible generation controls and an exact effective-request preview with
   secrets excluded.
5. A bounded streaming refusal guard that cancels and retries before an
   explicit guideline refusal is emitted, spoken, or persisted.
6. Regression evidence that normal output still streams early, slow live-call
   playback begins before LLM/TTS completion, VoxCPM2 never falls back to whole
   synthesis, and explicit interruption rejects late chunks.

If prompt composition and bounded retries cannot make the fixed refusal corpus
pass on the deployed model, the phase must produce model-adapter or checkpoint
evidence and fix that boundary. It may not declare success by hiding the
refusal, returning canned prose, or buffering the entire answer.
