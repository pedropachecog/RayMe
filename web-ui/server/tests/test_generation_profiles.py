"""Exact logical-to-wire generation adapter contracts."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError

import pytest

from app.domain.generation_profiles import (
    RETRY_CORRECTION,
    GenerationAdapterError,
    ProviderEvidence,
    build_generation_request,
    resolve_generation_profile,
    validate_provider_evidence,
)
from app.domain.prompt_builder import PROMPT_ESTIMATOR_VERSION, PromptMessageCandidate
from app.domain.prompt_profiles import PromptGenerationSettings


REJECTED_PROSE = "I cannot help with that request because policy forbids it."
PREFILL = "The lantern"


def test_retry_correction_explicitly_grounds_the_in_world_continuation_as_fiction() -> None:
    assert RETRY_CORRECTION == (
        "The prior draft broke character. Continue the fictional scene and respond only with the "
        "in-world reply."
    )


def _logical_messages() -> tuple[PromptMessageCandidate, ...]:
    return (
        PromptMessageCandidate("system", "Main \N{SNOWMAN}", ("resolved_main",)),
        PromptMessageCandidate("system", "Name: Rhea", ("character_name",)),
        PromptMessageCandidate("system", "Persona e\u0301", ("character_personality",)),
        PromptMessageCandidate("system", "Auxiliary", ("resolved_auxiliary",)),
        PromptMessageCandidate("user", "User history", ("history:newest-user",)),
        PromptMessageCandidate("system", "Late PHI", ("resolved_post_history",)),
        PromptMessageCandidate("assistant", PREFILL, ("assistant_prefill",)),
    )


@pytest.mark.parametrize(
    ("configured", "model", "effective"),
    [
        ("qwen_llama_server", "anything", "qwen_llama_server"),
        ("generic_openai_compatible", "Qwen/ignored", "generic_openai_compatible"),
        ("auto", "UnSlOtH/QwEn3.8-27B", "qwen_llama_server"),
        ("auto", "meta-llama/Llama-3", "generic_openai_compatible"),
    ],
)
def test_adapter_selection_keeps_configured_and_effective_observable(
    configured: str, model: str, effective: str
) -> None:
    resolution = resolve_generation_profile(configured, model)

    assert resolution.configured == configured
    assert resolution.effective == effective


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_qwen_exact_request_goldens_keep_late_instructions_user_consumed(
    attempt: int,
) -> None:
    settings = PromptGenerationSettings(
        model_profile="qwen_llama_server",
        max_tokens=1024,
        temperature=0.65,
        top_p=0.91,
        min_p=0.07,
        top_k=37,
        repetition_penalty=1.11,
        presence_penalty=0.2,
        frequency_penalty=-0.1,
    )

    request = build_generation_request(
        model="unsloth/Qwen3.8-27B",
        messages=_logical_messages(),
        settings=settings,
        seed=100 + attempt,
        attempt=attempt,
        disable_thinking=True,
        extra_body={"chat_template_kwargs": {"custom_flag": "kept"}},
    )

    expected_messages = [
        {
            "role": "system",
            "content": "Main \N{SNOWMAN}\n\nName: Rhea\n\nPersona e\u0301\n\nAuxiliary",
        },
        {"role": "user", "content": "User history"},
        {"role": "user", "content": "Late PHI"},
    ]
    if attempt > 1:
        expected_messages.append({"role": "user", "content": RETRY_CORRECTION})
    expected_messages[-1]["content"] += "\n\n/no_think"
    expected_messages.append({"role": "assistant", "content": PREFILL})

    assert request.configured_adapter == "qwen_llama_server"
    assert request.effective_adapter == "qwen_llama_server"
    assert request.estimator_version == PROMPT_ESTIMATOR_VERSION
    assert request.to_openai_kwargs() == {
        "model": "unsloth/Qwen3.8-27B",
        "messages": expected_messages,
        "seed": 100 + attempt,
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.65,
        "top_p": 0.91,
        "presence_penalty": 0.2,
        "frequency_penalty": -0.1,
        "extra_body": {
            "top_k": 37,
            "min_p": 0.07,
            "repeat_penalty": 1.11,
            "chat_template_kwargs": {
                "custom_flag": "kept",
                "enable_thinking": False,
            },
        },
    }
    assert _recursive_absent(request.to_openai_kwargs(), REJECTED_PROSE)


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_generic_exact_request_goldens_preserve_roles_and_exact_strings(
    attempt: int,
) -> None:
    settings = PromptGenerationSettings(
        model_profile="generic_openai_compatible",
        max_tokens=512,
        temperature=0.8,
        top_p=0.95,
        min_p=0.05,
        top_k=40,
        repetition_penalty=1.05,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    )

    request = build_generation_request(
        model="meta-llama/Llama-3",
        messages=_logical_messages(),
        settings=settings,
        seed=200 + attempt,
        attempt=attempt,
    )

    expected_messages = [
        {"role": message.role, "content": message.content} for message in _logical_messages()
    ]
    if attempt > 1:
        expected_messages.insert(-1, {"role": "system", "content": RETRY_CORRECTION})
    assert request.to_openai_kwargs() == {
        "model": "meta-llama/Llama-3",
        "messages": expected_messages,
        "seed": 200 + attempt,
        "stream": True,
        "max_tokens": 512,
        "temperature": 0.8,
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    }
    assert request.messages[-1].role == "assistant"
    assert request.messages[-1].content == PREFILL
    assert _recursive_absent(request.to_openai_kwargs(), REJECTED_PROSE)


def test_provider_evidence_is_required_to_be_unambiguous_and_matching() -> None:
    valid = ProviderEvidence(
        model_id="unsloth/Qwen3.8-27B",
        chat_template_id="unsloth/Qwen3.8-27B",
        chat_template_sha256="6e1439c913ad7df4a966493ad70de7e7fc5a548d41bbe417c1571f766603629b",
        context_capacity=150_528,
        assistant_prefill=True,
    )
    expectation = validate_provider_evidence(valid)
    assert expectation.effective_adapter == "qwen_llama_server"
    assert expectation.context_capacity == 150_528

    for bad in (
        ProviderEvidence(None, None, None, None, None),
        ProviderEvidence("qwen-a", "qwen-b", "a" * 64, 150_528, True),
        ProviderEvidence("qwen-a", "qwen-a", "a" * 64, 150_528, False),
    ):
        with pytest.raises(GenerationAdapterError) as exc_info:
            validate_provider_evidence(bad)
        assert exc_info.value.code == "provider_evidence_mismatch"


async def test_concurrent_requests_own_immutable_messages_settings_and_seeds() -> None:
    settings = PromptGenerationSettings(model_profile="auto")

    async def create(seed: int):
        await asyncio.sleep(0)
        return build_generation_request(
            model="qwen/test",
            messages=_logical_messages(),
            settings=settings,
            seed=seed,
            attempt=2,
        )

    first, second = await asyncio.gather(create(301), create(302))
    assert first is not second
    assert first.messages is not second.messages
    assert first.seed == 301
    assert second.seed == 302
    with pytest.raises(FrozenInstanceError):
        first.seed = 999  # type: ignore[misc]
    first_copy = first.to_openai_kwargs()
    first_copy["messages"][0]["content"] = "mutated"
    assert second.to_openai_kwargs()["messages"][0]["content"] != "mutated"


def _recursive_absent(value: object, canary: str) -> bool:
    if isinstance(value, dict):
        return all(
            _recursive_absent(key, canary) and _recursive_absent(item, canary)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_recursive_absent(item, canary) for item in value)
    return canary not in str(value)
