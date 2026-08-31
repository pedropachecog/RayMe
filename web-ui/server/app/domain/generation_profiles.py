"""Immutable logical-to-wire adapters for OpenAI-compatible generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from app.domain.prompt_builder import (
    PROMPT_ESTIMATOR_VERSION,
    PromptMessageCandidate,
    PromptRole,
)
from app.domain.prompt_profiles import ModelProfile, PromptGenerationSettings

EffectiveModelProfile: TypeAlias = Literal["qwen_llama_server", "generic_openai_compatible"]

RETRY_CORRECTION = (
    "The prior draft broke character. Continue the fictional scene and respond only with the "
    "in-world reply."
)


class GenerationAdapterError(ValueError):
    """Fail-closed adapter or live-provider evidence mismatch."""

    code = "provider_evidence_mismatch"

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True, slots=True)
class AdapterResolution:
    configured: ModelProfile
    effective: EffectiveModelProfile


@dataclass(frozen=True, slots=True)
class ProviderEvidence:
    """Sanitized facts supplied by the read-only provider preflight."""

    model_id: str | None
    chat_template_id: str | None
    chat_template_sha256: str | None
    context_capacity: int | None
    assistant_prefill: bool | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ProviderEvidence:
        return cls(
            model_id=_optional_str(value.get("model_id")),
            chat_template_id=_optional_str(value.get("chat_template_id")),
            chat_template_sha256=_optional_str(value.get("chat_template_sha256")),
            context_capacity=_optional_int(value.get("context_capacity")),
            assistant_prefill=_optional_bool(value.get("assistant_prefill")),
        )


@dataclass(frozen=True, slots=True)
class ProviderExpectation:
    model_id: str
    chat_template_id: str
    chat_template_sha256: str
    context_capacity: int
    assistant_prefill: Literal[True]
    effective_adapter: EffectiveModelProfile


@dataclass(frozen=True, slots=True)
class WireMessage:
    role: PromptRole
    content: str
    section_ids: tuple[str, ...] = ()

    def to_openai_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class SamplerPayload:
    max_tokens: int
    temperature: float
    top_p: float
    min_p: float
    top_k: int
    repetition_penalty: float
    presence_penalty: float
    frequency_penalty: float

    @classmethod
    def from_settings(cls, settings: PromptGenerationSettings) -> SamplerPayload:
        return cls(
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            top_p=settings.top_p,
            min_p=settings.min_p,
            top_k=settings.top_k,
            repetition_penalty=settings.repetition_penalty,
            presence_penalty=settings.presence_penalty,
            frequency_penalty=settings.frequency_penalty,
        )

    def standard_payload(self) -> dict[str, int | float]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }

    def qwen_extra_payload(self) -> dict[str, int | float]:
        return {
            "top_k": self.top_k,
            "min_p": self.min_p,
            "repeat_penalty": self.repetition_penalty,
        }


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    model: str
    configured_adapter: ModelProfile
    effective_adapter: EffectiveModelProfile
    estimator_version: str
    messages: tuple[WireMessage, ...]
    sampler: SamplerPayload | None
    seed: int
    stream: bool
    extra_body_items: tuple[tuple[str, object], ...]

    def to_openai_kwargs(self) -> dict[str, object]:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [message.to_openai_dict() for message in self.messages],
            "seed": self.seed,
            "stream": self.stream,
        }
        if self.sampler is not None:
            request.update(self.sampler.standard_payload())
        if self.extra_body_items:
            request["extra_body"] = _thaw_mapping(self.extra_body_items)
        return request


def resolve_generation_profile(
    configured: ModelProfile | str,
    model: str,
) -> AdapterResolution:
    """Resolve an explicit adapter or deterministic identifier-based auto choice."""

    if configured not in {
        "auto",
        "qwen_llama_server",
        "generic_openai_compatible",
    }:
        raise GenerationAdapterError(f"Unsupported generation adapter: {configured!r}.")
    configured_profile = cast(ModelProfile, configured)
    if configured_profile != "auto":
        effective = cast(EffectiveModelProfile, configured_profile)
    elif "qwen" in model.casefold():
        effective = "qwen_llama_server"
    else:
        effective = "generic_openai_compatible"
    return AdapterResolution(configured=configured_profile, effective=effective)


def validate_provider_evidence(evidence: ProviderEvidence) -> ProviderExpectation:
    """Bind a live adapter expectation only from complete matching preflight facts."""

    model_id = evidence.model_id
    template_id = evidence.chat_template_id
    template_hash = evidence.chat_template_sha256
    capacity = evidence.context_capacity
    if (
        not model_id
        or not template_id
        or model_id != template_id
        or not template_hash
        or len(template_hash) != 64
        or capacity is None
        or capacity <= 0
        or evidence.assistant_prefill is not True
    ):
        raise GenerationAdapterError(
            "Provider identity, template, context, or assistant-prefill evidence is "
            "missing or mismatched."
        )
    resolution = resolve_generation_profile("auto", model_id)
    return ProviderExpectation(
        model_id=model_id,
        chat_template_id=template_id,
        chat_template_sha256=template_hash,
        context_capacity=capacity,
        assistant_prefill=True,
        effective_adapter=resolution.effective,
    )


def build_generation_request(
    *,
    model: str,
    messages: Sequence[PromptMessageCandidate | Mapping[str, object]],
    settings: PromptGenerationSettings | None,
    seed: int,
    attempt: int,
    disable_thinking: bool = False,
    extra_body: Mapping[str, object] | None = None,
    stream: bool = True,
) -> GenerationRequest:
    """Serialize exact logical candidates without mutating composer-owned values."""

    if attempt not in {1, 2, 3}:
        raise ValueError("generation attempt must be 1, 2, or 3")
    configured = settings.model_profile if settings is not None else "auto"
    resolution = resolve_generation_profile(configured, model)
    logical_messages = tuple(_wire_message(message) for message in messages)
    wire_messages = _serialize_messages(
        logical_messages,
        effective=resolution.effective,
        attempt=attempt,
        disable_thinking=disable_thinking,
    )
    sampler = SamplerPayload.from_settings(settings) if settings is not None else None
    merged_extra: dict[str, object] = _deep_copy_mapping(extra_body or {})
    if resolution.effective == "qwen_llama_server":
        if sampler is not None:
            merged_extra.update(sampler.qwen_extra_payload())
        if disable_thinking:
            template_options = merged_extra.get("chat_template_kwargs")
            if isinstance(template_options, Mapping):
                merged_options = _deep_copy_mapping(template_options)
            else:
                merged_options = {}
            merged_options["enable_thinking"] = False
            merged_extra["chat_template_kwargs"] = merged_options
    else:
        merged_extra = {}

    return GenerationRequest(
        model=model,
        configured_adapter=resolution.configured,
        effective_adapter=resolution.effective,
        estimator_version=PROMPT_ESTIMATOR_VERSION,
        messages=wire_messages,
        sampler=sampler,
        seed=seed,
        stream=stream,
        extra_body_items=_freeze_mapping(merged_extra),
    )


def _serialize_messages(
    messages: tuple[WireMessage, ...],
    *,
    effective: EffectiveModelProfile,
    attempt: int,
    disable_thinking: bool,
) -> tuple[WireMessage, ...]:
    final_prefill = bool(messages and messages[-1].role == "assistant")
    body = list(messages[:-1] if final_prefill else messages)
    prefill = messages[-1] if final_prefill else None

    if effective == "qwen_llama_server":
        body = _serialize_qwen_body(body)
        correction_role: PromptRole = "user"
    else:
        correction_role = "system"

    if attempt > 1:
        body.append(
            WireMessage(
                role=correction_role,
                content=RETRY_CORRECTION,
                section_ids=("retry_correction",),
            )
        )
    if effective == "qwen_llama_server" and disable_thinking:
        _append_no_think(body)
    if prefill is not None:
        body.append(prefill)
    return tuple(body)


def _serialize_qwen_body(messages: list[WireMessage]) -> list[WireMessage]:
    leading: list[WireMessage] = []
    index = 0
    while index < len(messages) and messages[index].role == "system":
        leading.append(messages[index])
        index += 1
    serialized: list[WireMessage] = []
    if leading:
        serialized.append(
            WireMessage(
                role="system",
                content="\n\n".join(message.content for message in leading),
                section_ids=tuple(
                    section_id for message in leading for section_id in message.section_ids
                ),
            )
        )
    for message in messages[index:]:
        if message.role == "system":
            serialized.append(
                WireMessage(
                    role="user",
                    content=message.content,
                    section_ids=message.section_ids,
                )
            )
        else:
            serialized.append(message)
    return serialized


def _append_no_think(messages: list[WireMessage]) -> None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role != "user":
            continue
        content = message.content.rstrip()
        if "/no_think" not in content:
            content = f"{content}\n\n/no_think" if content else "/no_think"
        messages[index] = WireMessage(
            role=message.role,
            content=content,
            section_ids=message.section_ids,
        )
        return


def _wire_message(
    value: PromptMessageCandidate | Mapping[str, object],
) -> WireMessage:
    if isinstance(value, PromptMessageCandidate):
        return WireMessage(value.role, value.content, value.section_ids)
    role = value.get("role")
    if role not in {"system", "user", "assistant"}:
        raise ValueError(f"Unsupported logical message role: {role!r}")
    content = value.get("content")
    if not isinstance(content, str):
        raise TypeError("Logical message content must be text")
    raw_section_ids = value.get("section_ids", ())
    if not isinstance(raw_section_ids, Sequence) or isinstance(raw_section_ids, str):
        raise TypeError("Logical section IDs must be a sequence")
    return WireMessage(
        role=cast(PromptRole, role),
        content=content,
        section_ids=tuple(str(item) for item in raw_section_ids),
    )


def _deep_copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    copied: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            copied[str(key)] = _deep_copy_mapping(item)
        elif isinstance(item, list):
            copied[str(key)] = [_deep_copy_value(entry) for entry in item]
        else:
            copied[str(key)] = item
    return copied


def _deep_copy_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _deep_copy_mapping(value)
    if isinstance(value, list):
        return [_deep_copy_value(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple((key, _freeze_value(item)) for key, item in sorted(value.items()))


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_mapping(value: tuple[tuple[str, object], ...]) -> dict[str, object]:
    return {key: _thaw_value(item) for key, item in value}


def _thaw_value(value: object) -> object:
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return _thaw_mapping(cast(tuple[tuple[str, object], ...], value))
        return [_thaw_value(item) for item in value]
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


__all__ = [
    "AdapterResolution",
    "EffectiveModelProfile",
    "GenerationAdapterError",
    "GenerationRequest",
    "ProviderEvidence",
    "ProviderExpectation",
    "RETRY_CORRECTION",
    "SamplerPayload",
    "WireMessage",
    "build_generation_request",
    "resolve_generation_profile",
    "validate_provider_evidence",
]
