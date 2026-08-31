"""Exact structured prompt-composition contracts for every generation action."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from app.domain.prompt_builder import (
    PROMPT_ESTIMATOR_VERSION,
    PromptBudgetExceeded,
    PromptBuildInput,
    PromptCharacterSnapshot,
    PromptHistoryEntry,
    PromptThreadSnapshot,
    build_call_prompt_context,
    build_prompt_context,
    compose_prompt,
    parse_example_groups,
)
from app.domain.prompt_profiles import PromptGenerationSettings


UNICODE_CANARY = "cafe\u0301 / café / 漢字 / 🫀 <script>not html</script>"
LORE_CANARY = "LOREBOOK-MUST-NEVER-ENTER-PROMPT"


def _settings(
    *,
    mode: str = "roleplay",
    context_limit: int = 16_384,
    max_tokens: int = 512,
    main: str | None = None,
    auxiliary: str | None = None,
    post_history: str | None = None,
) -> PromptGenerationSettings:
    defaults = PromptGenerationSettings.defaults()
    updates: dict[str, Any] = {
        "mode": mode,
        "context_limit": context_limit,
        "max_tokens": max_tokens,
    }
    if any(value is not None for value in (main, auxiliary, post_history)):
        selected = getattr(defaults, mode)
        updates[mode] = {
            "main": selected.main if main is None else main,
            "auxiliary": selected.auxiliary if auxiliary is None else auxiliary,
            "post_history": selected.post_history if post_history is None else post_history,
        }
    return defaults.merge(updates)


def _build_input(
    *,
    action: str = "send",
    settings: PromptGenerationSettings | None = None,
    card_main: str | None = "",
    card_phi: str | None = "",
    examples: str | None = "",
    history: tuple[PromptHistoryEntry, ...] | None = None,
    composer_text: str | None = None,
) -> PromptBuildInput:
    return PromptBuildInput(
        settings=settings or _settings(),
        character=PromptCharacterSnapshot(
            name="Mara",
            description=f"A keeper of exact bytes: {UNICODE_CANARY}",
            personality="Dry; watchful; kind only by choice.",
            scenario="Rain against the observatory glass.",
            system_prompt=card_main,
            post_history_instructions=card_phi,
            mes_example=examples,
        ),
        thread=PromptThreadSnapshot(thread_id="thread-1", variant="selected"),
        history=history
        or (
            PromptHistoryEntry(
                id="msg-001", sequence=1, role="assistant", content="An old answer."
            ),
            PromptHistoryEntry(
                id="msg-002", sequence=2, role="user", content="The newest user turn."
            ),
        ),
        action=action,  # type: ignore[arg-type]
        call_mode="call" if action in {"call_offer", "call_turn"} else "text",
        composer_text=composer_text,
    )


def _section(result: object, section_id: str) -> object:
    sections = getattr(result, "sections")
    return next(section for section in sections if section.section_id == section_id)


def test_card_inheritance_original_boundaries_and_one_pass_macros_are_exact() -> None:
    settings = _settings(
        mode="custom",
        main="GLOBAL({{char}}|{{user}}|{{unknown}})",
        auxiliary="AUX={{char}}/{{user}}",
        post_history="PHI({{char}})",
    )
    result = compose_prompt(
        _build_input(
            settings=settings,
            card_main="before{{original}}after::{{char}}::{{user}}::{{mystery}}",
            card_phi="[{{original}}][{{char}}][{{user}}]",
        )
    )

    main = _section(result, "main")
    assert main.content == (
        "beforeGLOBAL(Mara|User|{{unknown}})after::Mara::User::{{mystery}}"
    )
    assert main.override_state == "includes_original"
    assert _section(result, "auxiliary").content == "AUX=Mara/User"
    assert _section(result, "late_phi").content == "[PHI(Mara)][Mara][User]"

    non_recursive = compose_prompt(
        _build_input(settings=settings, card_main="{{char}} / {{user}}").with_character_name(
            "{{user}}"
        )
    )
    assert _section(non_recursive, "main").content == "{{user}} / User"


def test_blank_card_fields_inherit_but_nonblank_fields_replace_exactly() -> None:
    settings = _settings(
        mode="custom",
        main=" inherited-main ",
        auxiliary="",
        post_history=" inherited-phi ",
    )
    inherited = compose_prompt(_build_input(settings=settings, card_main="\t", card_phi=""))
    replaced = compose_prompt(
        _build_input(settings=settings, card_main=" replacement ", card_phi="\nreplacement-phi")
    )

    assert _section(inherited, "main").content == " inherited-main "
    assert _section(inherited, "main").override_state == "inherited"
    assert _section(inherited, "late_phi").content == " inherited-phi "
    assert _section(replaced, "main").content == " replacement "
    assert _section(replaced, "main").override_state == "replaced"
    assert _section(replaced, "late_phi").content == "\nreplacement-phi"


def test_section_identity_order_unicode_and_equal_content_are_preserved() -> None:
    duplicate = "same bytes"
    result = compose_prompt(
        _build_input(
            examples=(
                "<START>\n{{user}}: example one\ncontinuation\n"
                "{{char}}: reply one\n<START>\n{{user}}: example two\n{{char}}: reply two"
            ),
            history=(
                PromptHistoryEntry(id="a", sequence=1, role="user", content=duplicate),
                PromptHistoryEntry(id="b", sequence=2, role="assistant", content=duplicate),
                PromptHistoryEntry(id="c", sequence=3, role="user", content=UNICODE_CANARY),
            ),
        )
    )

    ids = [section.section_id for section in result.sections]
    assert ids[:6] == [
        "main",
        "character_name",
        "description",
        "personality",
        "scenario",
        "auxiliary",
    ]
    assert ids[6:10] == [
        "example:000:000",
        "example:000:001",
        "example:001:000",
        "example:001:001",
    ]
    assert ids[10:13] == ["history:a", "history:b", "history:c"]
    assert ids[-1] == "late_phi"
    assert _section(result, "example:000:000").content == "example one\ncontinuation"
    assert [_section(result, item).content for item in ("history:a", "history:b")] == [
        duplicate,
        duplicate,
    ]
    assert _section(result, "history:c").content.encode("utf-8") == UNICODE_CANARY.encode(
        "utf-8"
    )
    assert result.public_preview.sections[-1].content == _section(result, "late_phi").content


def test_examples_parse_only_complete_groups_and_null_is_truthful() -> None:
    groups = parse_example_groups(
        "preamble outside a group\n"
        "<START>\n{{user}}: first\nline two\n{{char}}: second\n"
        "<START>\nmalformed before a speaker\n{{user}}: ignored\n"
        "<START>\n{{user}}: final\n{{char}}: answer"
    )
    assert [[turn.content for turn in group.turns] for group in groups] == [
        ["first\nline two", "second"],
        ["final", "answer"],
    ]
    assert parse_example_groups("") == ()
    assert parse_example_groups(None) == ()
    result = compose_prompt(_build_input(examples=None))
    assert not any(section.section_id.startswith("example:") for section in result.sections)


def test_empty_optional_sections_are_visible_but_do_not_fabricate_messages() -> None:
    settings = _settings(mode="custom", main="Main", auxiliary="", post_history="")
    result = compose_prompt(_build_input(settings=settings))

    assert _section(result, "auxiliary").content == ""
    assert _section(result, "late_phi").content == ""
    candidate_ids = {
        candidate.section_ids for candidate in result.transmitted_message_candidates
    }
    assert ("auxiliary",) not in candidate_ids
    assert ("late_phi",) not in candidate_ids


@pytest.mark.parametrize(
    "action",
    ["send", "regenerate", "swipe", "continue", "call_offer", "call_turn", "preview"],
)
def test_all_actions_promote_newest_user_and_continue_prefill_under_pressure(
    action: str,
) -> None:
    settings = _settings(context_limit=2_048, max_tokens=1_024)
    history = tuple(
        PromptHistoryEntry(
            id=f"msg-{index:03d}",
            sequence=index,
            role="user" if index % 2 == 0 else "assistant",
            content=("old optional context " * 45) + str(index),
        )
        for index in range(1, 9)
    ) + (
        PromptHistoryEntry(
            id="newest-user",
            sequence=99,
            role="user",
            content=f"NEWEST::{UNICODE_CANARY}",
        ),
    )
    composer_text = "assistant prefix" if action == "continue" else None
    result = compose_prompt(
        _build_input(
            action=action,
            settings=settings,
            history=history,
            composer_text=composer_text,
        )
    )

    mandatory_ids = {section.section_id for section in result.sections if section.mandatory}
    assert {
        "main",
        "character_name",
        "description",
        "personality",
        "scenario",
        "auxiliary",
        "history:newest-user",
        "late_phi",
    } <= mandatory_ids
    assert _section(result, "history:newest-user").content == f"NEWEST::{UNICODE_CANARY}"
    assert result.dropped_history_count > 0
    if action == "continue":
        assert result.sections[-1].section_id == "assistant_prefill"
        assert result.transmitted_message_candidates[-1].role == "assistant"
        assert result.transmitted_message_candidates[-1].content == "assistant prefix"


def test_budget_formula_and_output_reservation_change_optional_retention() -> None:
    history = tuple(
        PromptHistoryEntry(
            id=f"h-{index}",
            sequence=index,
            role="user" if index % 2 else "assistant",
            content="x" * 320,
        )
        for index in range(1, 13)
    )
    retained: list[int] = []
    budgets: list[int] = []
    for output in (64, 1_024, 4_096):
        result = compose_prompt(
            _build_input(
                settings=_settings(context_limit=8_192, max_tokens=output),
                history=history,
            )
        )
        budgets.append(result.input_budget)
        retained.append(12 - result.dropped_history_count)
        assert result.safety_margin == 410

    assert budgets == [7_718, 6_758, 3_686]
    assert retained[0] >= retained[1] > retained[2]
    assert PROMPT_ESTIMATOR_VERSION.startswith("rayme-")


def test_mandatory_bundle_just_fits_and_one_byte_beyond_is_typed_overflow() -> None:
    base = _build_input(
        settings=_settings(
            mode="custom",
            context_limit=2_048,
            max_tokens=1_024,
            main="M",
            auxiliary="",
            post_history="",
        ),
        history=(PromptHistoryEntry(id="u", sequence=1, role="user", content="U"),),
    )
    baseline = compose_prompt(base)
    available = baseline.input_budget
    current = baseline.estimated_input_tokens
    fitting_main = "M" + ("x" * max(0, (available - current - 7) * 3))
    fitting = compose_prompt(base.with_card_main(fitting_main))
    assert fitting.estimated_input_tokens <= fitting.input_budget

    with pytest.raises(PromptBudgetExceeded) as raised:
        compose_prompt(base.with_card_main(fitting_main + ("y" * 60)))
    assert raised.value.code == "prompt_budget_exceeded"
    assert raised.value.to_public_dict()["code"] == "prompt_budget_exceeded"


def test_call_offer_alone_enforces_transport_message_and_content_limits() -> None:
    too_long = "z" * 20_001
    history = (
        PromptHistoryEntry(id="older", sequence=1, role="assistant", content=too_long),
        PromptHistoryEntry(id="newest", sequence=2, role="user", content="still retained"),
    )
    normal = compose_prompt(_build_input(action="call_turn", history=history))
    offer = compose_prompt(_build_input(action="call_offer", history=history))

    assert any(
        candidate.content == too_long for candidate in normal.transmitted_message_candidates
    )
    assert all(
        len(candidate.content) <= 20_000
        for candidate in offer.transmitted_message_candidates
    )
    assert offer.target_constraints.max_messages == 48
    assert normal.target_constraints.max_messages is None

    with pytest.raises(PromptBudgetExceeded):
        compose_prompt(
            _build_input(
                action="call_offer",
                card_main=too_long,
                history=(
                    PromptHistoryEntry(id="u", sequence=1, role="user", content="u"),
                ),
            )
        )


def test_lorebook_canary_is_absent_from_sections_preview_and_candidates() -> None:
    source_character = {
        "lorebook_json": {"entries": [{"content": LORE_CANARY}]},
        "world_info": LORE_CANARY,
    }
    result = compose_prompt(_build_input())
    serialized = repr(
        (result.sections, result.public_preview, result.transmitted_message_candidates)
    )

    assert LORE_CANARY not in serialized
    assert source_character["lorebook_json"]["entries"][0]["content"] == LORE_CANARY
    assert source_character["world_info"] == LORE_CANARY


def test_prompt_build_values_are_frozen_and_credential_free() -> None:
    result = compose_prompt(_build_input())
    with pytest.raises(FrozenInstanceError):
        result.action = "swipe"  # type: ignore[misc]
    preview = repr(result.public_preview).lower()
    assert "api_key" not in preview
    assert "authorization" not in preview
    assert "seed" not in preview


class ScriptedPromptRepository:
    def __init__(self, *, example_snapshot: str | None = "") -> None:
        self.thread = {
            "id": "thread-1",
            "character_snapshot": {
                "name": "Mara",
                "description": "Exact description",
                "personality": "Exact personality",
                "scenario": "Exact scenario",
                "system_prompt": "",
                "post_history_instructions": "",
                "mes_example": example_snapshot,
                "lorebook_json": {"content": LORE_CANARY},
            },
            "messages": [
                {
                    "id": "user-1",
                    "sequence": 1,
                    "role": "user",
                    "content_text": "Hello",
                },
                {
                    "id": "ai-1",
                    "sequence": 2,
                    "role": "assistant",
                    "content_text": "Original branch",
                    "selected_alternate_id": "selected-alt",
                    "alternates": [
                        {"id": "selected-alt", "content_text": "Selected branch"},
                        {"id": "unused-alt", "content_text": "Hidden branch"},
                    ],
                },
                {
                    "id": "stale",
                    "sequence": 3,
                    "role": "user",
                    "content_text": "stale",
                    "stale_after_edit": True,
                },
            ],
        }

    async def get_prompt_thread(self, thread_id: str) -> object:
        assert thread_id == "thread-1"
        return self.thread


async def test_compatibility_wrappers_delegate_to_structured_composer() -> None:
    repository = ScriptedPromptRepository()
    messages = await build_prompt_context(
        "thread-1",
        repository=repository,
        settings=_settings(),
        action="swipe",
    )
    call_messages = await build_call_prompt_context(
        "thread-1",
        repository=repository,
        settings=_settings(),
        action="call_turn",
    )

    text = "\n".join(message["content"] for message in messages)
    assert "Selected branch" in text
    assert "Hidden branch" not in text
    assert "stale" not in text
    assert LORE_CANARY not in text
    assert call_messages == messages
