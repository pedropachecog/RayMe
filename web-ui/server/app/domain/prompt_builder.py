"""Prompt context contract for selected-branch chat history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.thread_service import ThreadService
from app.storage.session import async_session_factory

PromptAction = Literal["send", "regenerate", "swipe", "continue"]


class PromptContextMessage(TypedDict):
    role: str
    content: str


class PromptContextRepository(Protocol):
    """Repository boundary consumed by the prompt builder implementation."""

    async def get_prompt_thread(self, thread_id: str) -> object: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyPromptRepository:
    """Prompt repository backed by the existing thread hydration contract."""

    session: AsyncSession

    async def get_prompt_thread(self, thread_id: str) -> object:
        return await ThreadService(self.session).get_thread_detail(thread_id)


async def build_prompt_context(
    thread_id: str,
    *,
    repository: PromptContextRepository | None = None,
    until_message_id: str | None = None,
    action: PromptAction | None = None,
    composer_text: str | None = None,
) -> list[PromptContextMessage]:
    """Build LLM messages from the selected non-stale branch only."""

    if repository is None:
        async with async_session_factory() as session:
            return await build_prompt_context(
                thread_id,
                repository=SqlAlchemyPromptRepository(session),
                until_message_id=until_message_id,
                action=action,
                composer_text=composer_text,
            )

    prompt_thread = await repository.get_prompt_thread(thread_id)
    context: list[PromptContextMessage] = []
    system_prompt = _system_prompt(prompt_thread)
    if system_prompt:
        context.append({"role": "system", "content": system_prompt})

    for message in _messages(prompt_thread):
        if _is_stale(message):
            continue

        role = _message_role(message)
        if role not in {"user", "assistant"}:
            continue

        content = _selected_content(message)
        if content:
            context.append({"role": role, "content": content})

        if until_message_id is not None and _field(message, "id") == until_message_id:
            break

    if action == "continue":
        context.append(
            {
                "role": "user",
                "content": _continue_instruction(composer_text),
            }
        )

    return context


def _system_prompt(prompt_thread: object) -> str:
    thread = _thread(prompt_thread)
    character_snapshot = _field(prompt_thread, "character_snapshot")
    source = character_snapshot if character_snapshot is not None else thread
    parts: list[str] = []

    explicit_system = _first_present(
        source,
        "system_prompt",
        "character_snapshot_system_prompt",
    )
    if explicit_system:
        parts.append(str(explicit_system).strip())

    persona_lines = []
    persona_fields = (
        ("Name", ("name", "character_name", "character_snapshot_name")),
        ("Description", ("description", "character_snapshot_description")),
        ("Personality", ("personality", "character_snapshot_personality")),
        ("Scenario", ("scenario", "character_snapshot_scenario")),
    )
    for label, keys in persona_fields:
        value = _first_present(source, *keys)
        if value:
            persona_lines.append(f"{label}: {str(value).strip()}")

    if persona_lines:
        parts.append("\n".join(persona_lines))

    post_history = _first_present(
        source,
        "post_history_instructions",
        "character_snapshot_post_history_instructions",
    )
    if post_history:
        parts.append(str(post_history).strip())

    return "\n\n".join(part for part in parts if part)


def _continue_instruction(composer_text: str | None) -> str:
    instruction = (
        "Continue the previous assistant message. Return the complete assistant message, "
        "including the existing text and the continuation."
    )
    stripped_text = composer_text.strip() if composer_text else ""
    if not stripped_text:
        return instruction
    return f"{instruction}\n\nUser continuation note: {stripped_text}"


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


def _first_present(source: object, *keys: str) -> object | None:
    for key in keys:
        value = _field(source, key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _field(source: object, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


__all__ = [
    "PromptAction",
    "PromptContextMessage",
    "PromptContextRepository",
    "SqlAlchemyPromptRepository",
    "build_prompt_context",
]
