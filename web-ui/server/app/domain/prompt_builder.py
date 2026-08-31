"""One exact structured prompt composer shared by text, calls, and preview."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, TypeAlias, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.prompt_profiles import PROMPT_CONTRACT_VERSION, PromptGenerationSettings
from app.domain.thread_service import ThreadService
from app.storage.session import async_session_factory

PromptAction: TypeAlias = Literal[
    "send",
    "regenerate",
    "swipe",
    "continue",
    "call_offer",
    "call_turn",
    "preview",
]
PromptRole: TypeAlias = Literal["system", "user", "assistant"]
CallMode: TypeAlias = Literal["text", "call"]
OverrideState: TypeAlias = Literal[
    "global",
    "inherited",
    "replaced",
    "includes_original",
    "not_applicable",
]

PROMPT_ESTIMATOR_VERSION = "rayme-utf8-bytes-v1"
CALL_OFFER_MAX_MESSAGES = 48
CALL_OFFER_MAX_CONTENT_LENGTH = 20_000
_NAME_MACRO = re.compile(r"\{\{(char|user)\}\}")


class PromptContextMessage(TypedDict):
    role: str
    content: str


class PromptContextRepository(Protocol):
    """Repository boundary consumed by the shared prompt composer."""

    async def get_prompt_thread(self, thread_id: str) -> object: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyPromptRepository:
    """Prompt repository backed by the immutable thread hydration contract."""

    session: AsyncSession

    async def get_prompt_thread(self, thread_id: str) -> object:
        return await ThreadService(self.session).get_thread_detail(thread_id)


@dataclass(frozen=True, slots=True)
class PromptCharacterSnapshot:
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    system_prompt: str | None = None
    post_history_instructions: str | None = None
    mes_example: str | None = None


@dataclass(frozen=True, slots=True)
class PromptThreadSnapshot:
    thread_id: str
    variant: str = "selected"


@dataclass(frozen=True, slots=True)
class PromptHistoryEntry:
    id: str
    sequence: int
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class PromptBuildInput:
    settings: PromptGenerationSettings
    character: PromptCharacterSnapshot
    thread: PromptThreadSnapshot
    history: tuple[PromptHistoryEntry, ...]
    action: PromptAction
    call_mode: CallMode = "text"
    composer_text: str | None = None

    def with_character_name(self, name: str) -> PromptBuildInput:
        return replace(self, character=replace(self.character, name=name))

    def with_card_main(self, content: str | None) -> PromptBuildInput:
        return replace(self, character=replace(self.character, system_prompt=content))


@dataclass(frozen=True, slots=True)
class PromptSection:
    section_id: str
    logical_role: PromptRole
    content: str
    source: str
    override_state: OverrideState
    mandatory: bool
    estimated_tokens: int
    atomic_group_id: str | None = None


@dataclass(frozen=True, slots=True)
class PromptMessageCandidate:
    role: PromptRole
    content: str
    section_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromptTargetConstraints:
    max_messages: int | None = None
    max_content_length: int | None = None


@dataclass(frozen=True, slots=True)
class PromptPreviewProjection:
    action: PromptAction
    mode: str
    prompt_contract_version: str
    estimator_version: str
    sections: tuple[PromptSection, ...]
    messages: tuple[PromptMessageCandidate, ...]
    input_budget: int
    estimated_input_tokens: int
    dropped_history_count: int
    dropped_example_group_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    action: PromptAction
    variant: str
    call_mode: CallMode
    mode: str
    prompt_contract_version: str
    estimator_version: str
    settings: PromptGenerationSettings
    character: PromptCharacterSnapshot
    thread: PromptThreadSnapshot
    history: tuple[PromptHistoryEntry, ...]
    sections: tuple[PromptSection, ...]
    transmitted_message_candidates: tuple[PromptMessageCandidate, ...]
    public_preview: PromptPreviewProjection
    context_limit: int
    configured_max_output: int
    safety_margin: int
    input_budget: int
    estimated_input_tokens: int
    dropped_history_count: int
    dropped_example_group_count: int
    warnings: tuple[str, ...]
    target_constraints: PromptTargetConstraints


@dataclass(frozen=True, slots=True)
class ExampleTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ExampleGroup:
    group_id: str
    turns: tuple[ExampleTurn, ...]


class PromptBudgetExceeded(ValueError):
    """Mandatory prompt material cannot fit without changing exact content."""

    code = "prompt_budget_exceeded"

    def __init__(
        self,
        *,
        input_budget: int,
        estimated_tokens: int,
        limit: str = "context_budget",
    ) -> None:
        super().__init__("The required prompt does not fit the configured context budget.")
        self.input_budget = input_budget
        self.estimated_tokens = estimated_tokens
        self.limit = limit

    def to_public_dict(self) -> dict[str, int | str]:
        return {
            "code": self.code,
            "message": str(self),
            "input_budget": self.input_budget,
            "estimated_tokens": self.estimated_tokens,
            "limit": self.limit,
        }


def estimate_prompt_tokens(content: str) -> int:
    """Deterministic provider-neutral estimate; never changes request text."""

    if not content:
        return 0
    return math.ceil(len(content.encode("utf-8")) / 3) + 6


def parse_example_groups(value: str | None) -> tuple[ExampleGroup, ...]:
    """Parse complete SillyTavern ``<START>`` groups without guessing roles."""

    groups, _malformed = _parse_example_groups(value)
    return groups


def compose_prompt(build: PromptBuildInput) -> PromptBuildResult:
    """Compose one immutable logical prompt or raise typed mandatory overflow."""

    selected_prompts = getattr(build.settings, build.settings.mode)
    main_content, main_override = _resolve_card_prompt(
        card_text=build.character.system_prompt,
        global_text=selected_prompts.main,
        character_name=build.character.name,
    )
    phi_content, phi_override = _resolve_card_prompt(
        card_text=build.character.post_history_instructions,
        global_text=selected_prompts.post_history,
        character_name=build.character.name,
    )
    auxiliary = _expand_names(selected_prompts.auxiliary, build.character.name)

    base_sections = [
        _make_section(
            "main", "system", main_content, "resolved_main", main_override, mandatory=True
        ),
        _make_section(
            "character_name",
            "system",
            f"Name: {build.character.name}",
            "character_snapshot",
            "not_applicable",
            mandatory=True,
        ),
        _make_section(
            "description",
            "system",
            f"Description: {build.character.description}",
            "character_snapshot",
            "not_applicable",
            mandatory=True,
        ),
        _make_section(
            "personality",
            "system",
            f"Personality: {build.character.personality}",
            "character_snapshot",
            "not_applicable",
            mandatory=True,
        ),
        _make_section(
            "scenario",
            "system",
            f"Scenario: {build.character.scenario}",
            "character_snapshot",
            "not_applicable",
            mandatory=True,
        ),
        _make_section(
            "auxiliary",
            "system",
            auxiliary,
            "global_profile",
            "global",
            mandatory=True,
        ),
    ]

    example_groups, malformed_count = _parse_example_groups(build.character.mes_example)
    example_sections = [
        tuple(
            _make_section(
                f"example:{group_index:03d}:{turn_index:03d}",
                turn.role,
                _expand_names(turn.content, build.character.name),
                "example_snapshot",
                "not_applicable",
                mandatory=False,
                atomic_group_id=group.group_id,
            )
            for turn_index, turn in enumerate(group.turns)
        )
        for group_index, group in enumerate(example_groups)
    ]

    history = _ordered_history(build.history)
    if build.action != "continue" and build.composer_text:
        next_sequence = max((entry.sequence for entry in history), default=-1) + 1
        history = (
            *history,
            PromptHistoryEntry(
                id="composer-user",
                sequence=next_sequence,
                role="user",
                content=build.composer_text,
            ),
        )
    if build.action == "continue" and not build.composer_text:
        next_sequence = max((entry.sequence for entry in history), default=-1) + 1
        history = (
            *history,
            PromptHistoryEntry(
                id="continue-instruction",
                sequence=next_sequence,
                role="user",
                content=_continue_instruction(),
            ),
        )

    newest_user_id = next(
        (entry.id for entry in reversed(history) if entry.role == "user"),
        None,
    )
    history_sections = [
        _make_section(
            f"history:{entry.id}",
            entry.role,
            entry.content,
            "selected_history",
            "not_applicable",
            mandatory=entry.id == newest_user_id,
            atomic_group_id=f"history:{entry.id}",
        )
        for entry in history
    ]
    phi_section = _make_section(
        "late_phi",
        "system",
        phi_content,
        "resolved_post_history",
        phi_override,
        mandatory=True,
    )
    prefill_section = (
        _make_section(
            "assistant_prefill",
            "assistant",
            build.composer_text,
            "assistant_prefill",
            "not_applicable",
            mandatory=True,
        )
        if build.action == "continue" and build.composer_text
        else None
    )

    safety_margin = max(256, math.ceil(build.settings.context_limit * 0.05))
    input_budget = build.settings.context_limit - build.settings.max_tokens - safety_margin
    mandatory = [
        *base_sections,
        *(section for section in history_sections if section.mandatory),
        phi_section,
        *([prefill_section] if prefill_section is not None else []),
    ]
    mandatory_tokens = _estimated_total(mandatory)
    if mandatory_tokens > input_budget:
        raise PromptBudgetExceeded(
            input_budget=input_budget,
            estimated_tokens=mandatory_tokens,
        )

    retained_history = list(history_sections)
    retained_examples = list(example_sections)
    dropped_history_count = 0
    dropped_example_group_count = 0

    def assembled() -> tuple[PromptSection, ...]:
        sections: list[PromptSection] = [*base_sections]
        sections.extend(section for group in retained_examples for section in group)
        sections.extend(retained_history)
        sections.append(phi_section)
        if prefill_section is not None:
            sections.append(prefill_section)
        return tuple(sections)

    while _estimated_total(assembled()) > input_budget:
        removable_index = next(
            (index for index, section in enumerate(retained_history) if not section.mandatory),
            None,
        )
        if removable_index is not None:
            retained_history.pop(removable_index)
            dropped_history_count += 1
            continue
        if retained_examples:
            retained_examples.pop(0)
            dropped_example_group_count += 1
            continue
        raise PromptBudgetExceeded(
            input_budget=input_budget,
            estimated_tokens=_estimated_total(assembled()),
        )

    constraints = (
        PromptTargetConstraints(
            max_messages=CALL_OFFER_MAX_MESSAGES,
            max_content_length=CALL_OFFER_MAX_CONTENT_LENGTH,
        )
        if build.action == "call_offer"
        else PromptTargetConstraints()
    )
    if build.action == "call_offer":
        while _violates_offer_constraints(assembled()):
            removable_index = next(
                (index for index, section in enumerate(retained_history) if not section.mandatory),
                None,
            )
            if removable_index is not None:
                retained_history.pop(removable_index)
                dropped_history_count += 1
                continue
            if retained_examples:
                retained_examples.pop(0)
                dropped_example_group_count += 1
                continue
            sections = assembled()
            limit = (
                "message_count"
                if len(_message_candidates(sections)) > CALL_OFFER_MAX_MESSAGES
                else "message_content_length"
            )
            raise PromptBudgetExceeded(
                input_budget=input_budget,
                estimated_tokens=_estimated_total(sections),
                limit=limit,
            )

    sections = assembled()
    candidates = _message_candidates(sections)
    warnings = (f"omitted_malformed_example_groups:{malformed_count}",) if malformed_count else ()
    estimated_input_tokens = _estimated_total(sections)
    preview = PromptPreviewProjection(
        action=build.action,
        mode=build.settings.mode,
        prompt_contract_version=PROMPT_CONTRACT_VERSION,
        estimator_version=PROMPT_ESTIMATOR_VERSION,
        sections=sections,
        messages=candidates,
        input_budget=input_budget,
        estimated_input_tokens=estimated_input_tokens,
        dropped_history_count=dropped_history_count,
        dropped_example_group_count=dropped_example_group_count,
        warnings=warnings,
    )
    return PromptBuildResult(
        action=build.action,
        variant=build.thread.variant,
        call_mode=build.call_mode,
        mode=build.settings.mode,
        prompt_contract_version=PROMPT_CONTRACT_VERSION,
        estimator_version=PROMPT_ESTIMATOR_VERSION,
        settings=build.settings,
        character=build.character,
        thread=build.thread,
        history=history,
        sections=sections,
        transmitted_message_candidates=candidates,
        public_preview=preview,
        context_limit=build.settings.context_limit,
        configured_max_output=build.settings.max_tokens,
        safety_margin=safety_margin,
        input_budget=input_budget,
        estimated_input_tokens=estimated_input_tokens,
        dropped_history_count=dropped_history_count,
        dropped_example_group_count=dropped_example_group_count,
        warnings=warnings,
        target_constraints=constraints,
    )


async def build_structured_prompt(
    thread_id: str,
    *,
    settings: PromptGenerationSettings,
    repository: PromptContextRepository | None = None,
    until_message_id: str | None = None,
    action: PromptAction = "send",
    composer_text: str | None = None,
) -> PromptBuildResult:
    """Hydrate once, freeze inputs, and delegate to the pure composer."""

    if repository is None:
        async with async_session_factory() as session:
            return await build_structured_prompt(
                thread_id,
                settings=settings,
                repository=SqlAlchemyPromptRepository(session),
                until_message_id=until_message_id,
                action=action,
                composer_text=composer_text,
            )

    prompt_thread = await repository.get_prompt_thread(thread_id)
    character = _character_snapshot(prompt_thread)
    history = _history_entries(prompt_thread, until_message_id=until_message_id)
    return compose_prompt(
        PromptBuildInput(
            settings=settings,
            character=character,
            thread=PromptThreadSnapshot(thread_id=thread_id),
            history=history,
            action=action,
            call_mode="call" if action in {"call_offer", "call_turn"} else "text",
            composer_text=composer_text,
        )
    )


async def build_prompt_context(
    thread_id: str,
    *,
    repository: PromptContextRepository | None = None,
    settings: PromptGenerationSettings | None = None,
    until_message_id: str | None = None,
    action: PromptAction | None = None,
    composer_text: str | None = None,
) -> list[PromptContextMessage]:
    """Compatibility seam backed exclusively by :func:`build_structured_prompt`."""

    result = await build_structured_prompt(
        thread_id,
        settings=settings or PromptGenerationSettings.defaults(),
        repository=repository,
        until_message_id=until_message_id,
        action=action or "send",
        composer_text=composer_text,
    )
    return [
        {"role": message.role, "content": message.content}
        for message in result.transmitted_message_candidates
    ]


async def build_call_prompt_context(
    thread_id: str,
    *,
    repository: PromptContextRepository | None = None,
    settings: PromptGenerationSettings | None = None,
    max_turns: int = 24,
    action: Literal["call_offer", "call_turn"] = "call_turn",
) -> list[PromptContextMessage]:
    """Legacy call signature delegating to the shared configured-budget composer.

    ``max_turns`` remains accepted for compatibility but no longer creates a
    second call-only context algorithm.
    """

    del max_turns
    return await build_prompt_context(
        thread_id,
        repository=repository,
        settings=settings,
        action=action,
    )


def _resolve_card_prompt(
    *,
    card_text: str | None,
    global_text: str,
    character_name: str,
) -> tuple[str, OverrideState]:
    if card_text is None or not card_text.strip():
        return _expand_names(global_text, character_name), "inherited"
    state: OverrideState = "includes_original" if "{{original}}" in card_text else "replaced"
    with_original = card_text.replace("{{original}}", global_text)
    return _expand_names(with_original, character_name), state


def _expand_names(content: str, character_name: str) -> str:
    values = {"char": character_name, "user": "User"}
    return _NAME_MACRO.sub(lambda match: values[match.group(1)], content)


def _parse_example_groups(value: str | None) -> tuple[tuple[ExampleGroup, ...], int]:
    if value is None or value == "" or "<START>" not in value:
        return (), 0
    parsed: list[ExampleGroup] = []
    malformed = 0
    for raw_group in value.split("<START>")[1:]:
        if not raw_group.strip():
            continue
        turns: list[ExampleTurn] = []
        current_role: Literal["user", "assistant"] | None = None
        current_lines: list[str] = []
        invalid = False
        for line in raw_group.splitlines():
            marker_role: Literal["user", "assistant"] | None = None
            marker = ""
            if line.startswith("{{user}}:"):
                marker_role = "user"
                marker = "{{user}}:"
            elif line.startswith("{{char}}:"):
                marker_role = "assistant"
                marker = "{{char}}:"
            if marker_role is not None:
                if current_role is not None:
                    turns.append(ExampleTurn(current_role, "\n".join(current_lines)))
                current_role = marker_role
                remainder = line[len(marker) :]
                if remainder.startswith(" "):
                    remainder = remainder[1:]
                current_lines = [remainder]
            elif current_role is None:
                if line.strip():
                    invalid = True
                    break
            else:
                current_lines.append(line)
        if invalid or current_role is None:
            malformed += 1
            continue
        turns.append(ExampleTurn(current_role, "\n".join(current_lines)))
        if turns:
            parsed.append(ExampleGroup(group_id=f"example:{len(parsed):03d}", turns=tuple(turns)))
    return tuple(parsed), malformed


def _make_section(
    section_id: str,
    role: PromptRole,
    content: str,
    source: str,
    override_state: OverrideState,
    *,
    mandatory: bool,
    atomic_group_id: str | None = None,
) -> PromptSection:
    return PromptSection(
        section_id=section_id,
        logical_role=role,
        content=content,
        source=source,
        override_state=override_state,
        mandatory=mandatory,
        estimated_tokens=estimate_prompt_tokens(content),
        atomic_group_id=atomic_group_id,
    )


def _estimated_total(sections: Sequence[PromptSection]) -> int:
    return sum(section.estimated_tokens for section in sections)


def _message_candidates(
    sections: Sequence[PromptSection],
) -> tuple[PromptMessageCandidate, ...]:
    return tuple(
        PromptMessageCandidate(
            role=section.logical_role,
            content=section.content,
            section_ids=(section.section_id,),
        )
        for section in sections
        if section.content != ""
    )


def _violates_offer_constraints(sections: Sequence[PromptSection]) -> bool:
    candidates = _message_candidates(sections)
    return len(candidates) > CALL_OFFER_MAX_MESSAGES or any(
        len(candidate.content) > CALL_OFFER_MAX_CONTENT_LENGTH for candidate in candidates
    )


def _ordered_history(
    history: Sequence[PromptHistoryEntry],
) -> tuple[PromptHistoryEntry, ...]:
    return tuple(sorted(history, key=lambda entry: (entry.sequence, entry.id)))


def _character_snapshot(prompt_thread: object) -> PromptCharacterSnapshot:
    thread = _thread(prompt_thread)
    snapshot = _field(prompt_thread, "character_snapshot")
    source = snapshot if snapshot is not None else thread
    return PromptCharacterSnapshot(
        name=str(_first_value(source, "name", "character_name", "character_snapshot_name") or ""),
        description=str(
            _first_value(source, "description", "character_snapshot_description") or ""
        ),
        personality=str(
            _first_value(source, "personality", "character_snapshot_personality") or ""
        ),
        scenario=str(_first_value(source, "scenario", "character_snapshot_scenario") or ""),
        system_prompt=_optional_text(
            _first_value(source, "system_prompt", "character_snapshot_system_prompt")
        ),
        post_history_instructions=_optional_text(
            _first_value(
                source,
                "post_history_instructions",
                "character_snapshot_post_history_instructions",
            )
        ),
        mes_example=_optional_text(
            _first_value(source, "mes_example", "character_snapshot_mes_example")
        ),
    )


def _history_entries(
    prompt_thread: object,
    *,
    until_message_id: str | None,
) -> tuple[PromptHistoryEntry, ...]:
    entries: list[PromptHistoryEntry] = []
    for index, message in enumerate(_messages(prompt_thread)):
        if _is_stale(message):
            continue
        role = _message_role(message)
        if role not in {"user", "assistant"}:
            continue
        content = _selected_content(message)
        if content is not None and content != "":
            sequence = _field(message, "sequence")
            entries.append(
                PromptHistoryEntry(
                    id=str(_field(message, "id") or f"sequence-{index:06d}"),
                    sequence=sequence if isinstance(sequence, int) else index,
                    role=role,
                    content=content,
                )
            )
        if until_message_id is not None and _field(message, "id") == until_message_id:
            break
    return _ordered_history(entries)


def _continue_instruction() -> str:
    return (
        "Continue the previous assistant message. Return the complete assistant message, "
        "including the existing text and the continuation."
    )


def _thread(prompt_thread: object) -> object:
    return _field(prompt_thread, "thread") or prompt_thread


def _messages(prompt_thread: object) -> Iterable[object]:
    messages = _field(prompt_thread, "messages")
    if isinstance(messages, Iterable) and not isinstance(messages, (str, bytes, Mapping)):
        return messages
    return ()


def _selected_content(message: object) -> str | None:
    selected_content = getattr(message, "selected_content", None)
    if callable(selected_content):
        content = selected_content()
        return str(content) if content is not None else None
    selected_alternate_id = _field(message, "selected_alternate_id")
    if selected_alternate_id is not None:
        for alternate in _alternates(message):
            if _field(alternate, "id") == selected_alternate_id:
                content = _field(alternate, "content_text")
                return str(content) if content is not None else None
    content = _field(message, "content_text")
    return str(content) if content is not None else None


def _alternates(message: object) -> Iterable[object]:
    alternates = _field(message, "alternates")
    if isinstance(alternates, Iterable) and not isinstance(alternates, (str, bytes, Mapping)):
        return alternates
    return ()


def _message_role(message: object) -> str | None:
    role = _field(message, "role")
    return str(role) if role is not None else None


def _is_stale(message: object) -> bool:
    return bool(_field(message, "stale_after_edit"))


def _first_value(source: object, *keys: str) -> object | None:
    for key in keys:
        value = _field(source, key)
        if value is not None:
            return value
    return None


def _optional_text(value: object | None) -> str | None:
    return None if value is None else str(value)


def _field(source: object, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


__all__ = [
    "CALL_OFFER_MAX_CONTENT_LENGTH",
    "CALL_OFFER_MAX_MESSAGES",
    "PROMPT_ESTIMATOR_VERSION",
    "ExampleGroup",
    "ExampleTurn",
    "PromptAction",
    "PromptBudgetExceeded",
    "PromptBuildInput",
    "PromptBuildResult",
    "PromptCharacterSnapshot",
    "PromptContextMessage",
    "PromptContextRepository",
    "PromptHistoryEntry",
    "PromptMessageCandidate",
    "PromptPreviewProjection",
    "PromptSection",
    "PromptTargetConstraints",
    "PromptThreadSnapshot",
    "SqlAlchemyPromptRepository",
    "build_call_prompt_context",
    "build_prompt_context",
    "build_structured_prompt",
    "compose_prompt",
    "estimate_prompt_tokens",
    "parse_example_groups",
]
