"""Safe, exact, side-effect-free Prompt Inspector backend contracts."""

from __future__ import annotations

import asyncio
import importlib
import json
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.domain.prompt_profiles import PromptGenerationSettings
from app.domain.refusal_activity import RefusalActivityRecord, RefusalActivityStore
from app.domain.settings_service import SETTINGS_KEY
from app.main import create_app
from app.storage.models import AppSetting, Base, Character, Message, Thread
from app.storage.session import create_engine

ALLOWED_ORIGIN = "https://rayme.local:8443"
HOSTILE_ORIGIN = "https://hostile.invalid"
THREAD_ID = "thread_prompt_preview"
COMPOSER_CANARY = "draft cafe\u0301 / café / 漢字 / 🫀 <script>not html</script>"
CHARACTER_CANARY = "Mara {{user}} macro-expanded exactly"
PRIVATE_KEY_CANARY = "sk-private-preview-must-never-leak"
PRIVATE_URL_CANARY = "https://private-user:private-pass@llm.internal/v1"
PRIVATE_PATH_CANARY = "C:\\Users\\secret\\voice.wav"
REJECTED_PROSE_CANARY = "rejected-private-prose-must-never-leak"


@dataclass(slots=True)
class PromptPreviewFixture:
    client: TestClient
    app: FastAPI
    sessionmaker: async_sessionmaker[AsyncSession]
    activity: RefusalActivityStore


@pytest.fixture()
def prompt_preview_fixture(tmp_path: Path) -> Iterator[PromptPreviewFixture]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'prompt-preview.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        prompt_settings = PromptGenerationSettings.defaults().merge(
            {
                "model_profile": "qwen_llama_server",
                "context_limit": 4096,
                "max_tokens": 320,
                "temperature": 0.60,
                "top_p": 0.87,
                "min_p": 0.07,
                "top_k": 37,
                "repetition_penalty": 1.08,
                "presence_penalty": 0.1,
                "frequency_penalty": 0.0,
                "roleplay": {
                    "main": "Global system for {{char}} and {{user}}.",
                    "auxiliary": "Stay exact, {{char}}.",
                    "post_history": "Continue as {{char}}.",
                },
            }
        )
        async with sessionmaker() as session:
            session.add(
                Character(
                    id="character_prompt_preview",
                    name="Mara",
                    description=CHARACTER_CANARY,
                    personality="Dry; watchful.",
                    scenario="Rain against the observatory glass.",
                    first_mes="Opening from Mara.",
                    mes_example="<START>\n{{user}}: Example question\n{{char}}: Example answer",
                    system_prompt="Card says {{char}} meets {{user}}.",
                    post_history_instructions="Card ending for {{char}}.",
                    raw_source_json={"private_path": PRIVATE_PATH_CANARY},
                    lorebook_json={"secret": REJECTED_PROSE_CANARY},
                )
            )
            await session.flush()
            session.add(
                Thread(
                    id=THREAD_ID,
                    character_id="character_prompt_preview",
                    title="Inspector thread",
                    character_snapshot_name="Mara",
                    character_snapshot_description=CHARACTER_CANARY,
                    character_snapshot_personality="Dry; watchful.",
                    character_snapshot_scenario="Rain against the observatory glass.",
                    character_snapshot_first_mes="Opening from Mara.",
                    character_snapshot_mes_example=(
                        "<START>\n{{user}}: Example question\n{{char}}: Example answer"
                    ),
                    character_snapshot_system_prompt="Card says {{char}} meets {{user}}.",
                    character_snapshot_post_history_instructions="Card ending for {{char}}.",
                    character_snapshot_raw_source_json={"private_path": PRIVATE_PATH_CANARY},
                    character_snapshot_lorebook_json={"secret": REJECTED_PROSE_CANARY},
                )
            )
            await session.flush()
            session.add_all(
                [
                    Message(
                        id="msg_preview_001",
                        thread_id=THREAD_ID,
                        message_kind="user_text",
                        role="user",
                        sequence=0,
                        content_text="Prior user turn.",
                    ),
                    Message(
                        id="msg_preview_002",
                        thread_id=THREAD_ID,
                        message_kind="ai_text",
                        role="assistant",
                        sequence=1,
                        content_text="Prior assistant turn.",
                    ),
                    AppSetting(
                        key=SETTINGS_KEY,
                        value_json={
                            "llm_base_url": PRIVATE_URL_CANARY,
                            "llm_api_key": PRIVATE_KEY_CANARY,
                            "llm_model": "Qwen3-Preview-Canary",
                            "llm_disable_thinking": True,
                            "prompt_generation": prompt_settings.to_dict(),
                        },
                    ),
                ]
            )
            await session.commit()

    asyncio.run(setup_database())
    app = create_app(
        Settings(
            web_public_url=ALLOWED_ORIGIN,
            llm_base_url=PRIVATE_URL_CANARY,
            llm_api_key=PRIVATE_KEY_CANARY,
        ),
        static_client_dir=None,
    )

    try:
        preview_module = importlib.import_module("app.api.prompt_preview")
    except ModuleNotFoundError:
        preview_module = None

    activity = RefusalActivityStore()
    if preview_module is not None:
        async def override_session() -> Iterator[AsyncSession]:
            async with sessionmaker() as session:
                yield session

        app.dependency_overrides[preview_module.get_prompt_preview_session] = override_session
        app.dependency_overrides[
            preview_module.get_prompt_preview_refusal_activity_store
        ] = lambda: activity

    with TestClient(app) as client:
        yield PromptPreviewFixture(
            client=client,
            app=app,
            sessionmaker=sessionmaker,
            activity=activity,
        )

    asyncio.run(engine.dispose())


def _send_payload(**updates: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": "send",
        "thread_id": THREAD_ID,
        "composer_text": COMPOSER_CANARY,
    }
    payload.update(updates)
    return payload


async def _persistent_counts(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[int, int, int, str]:
    async with sessionmaker() as session:
        message_count = await session.scalar(select(func.count()).select_from(Message))
        thread_count = await session.scalar(select(func.count()).select_from(Thread))
        setting_count = await session.scalar(select(func.count()).select_from(AppSetting))
        stored = await session.get(AppSetting, SETTINGS_KEY)
        return (
            int(message_count or 0),
            int(thread_count or 0),
            int(setting_count or 0),
            json.dumps(stored.value_json, ensure_ascii=False, sort_keys=True) if stored else "",
        )


def _serialized(response: object) -> str:
    return json.dumps(response, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize("origin", [ALLOWED_ORIGIN, None])
def test_send_preview_is_exact_no_store_and_accepts_same_or_missing_origin(
    prompt_preview_fixture: PromptPreviewFixture,
    origin: str | None,
) -> None:
    headers = {"Origin": origin} if origin is not None else {}
    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        headers=headers,
        json=_send_payload(),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "action",
        "variant",
        "mode",
        "prompt_contract_version",
        "request_shape_version",
        "thread_id",
        "configured_model",
        "configured_sampler",
        "adapter",
        "sections",
        "wire_messages",
        "effective_request",
        "budget",
        "warnings",
        "refusal_policy",
        "recent_refusal_activity",
    }
    assert body["action"] == "send"
    assert body["thread_id"] == THREAD_ID
    assert body["configured_model"] == "Qwen3-Preview-Canary"
    assert body["adapter"] == {
        "configured": "qwen_llama_server",
        "effective": "qwen_llama_server",
        "name": "qwen_llama_server",
        "version": "rayme-generation-request-v1",
    }
    assert body["configured_sampler"] == {
        "max_tokens": 320,
        "temperature": 0.6,
        "top_p": 0.87,
        "min_p": 0.07,
        "top_k": 37,
        "repetition_penalty": 1.08,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.0,
    }
    assert [message["order"] for message in body["wire_messages"]] == list(
        range(len(body["wire_messages"]))
    )
    assert body["wire_messages"][-1]["role"] == "user"
    assert body["wire_messages"][-1]["content"] == "Card ending for Mara.\n\n/no_think"
    assert any(message["content"] == COMPOSER_CANARY for message in body["wire_messages"])
    assert body["effective_request"]["messages"] == [
        {"role": message["role"], "content": message["content"]}
        for message in body["wire_messages"]
    ]
    assert body["effective_request"] == {
        "model": "Qwen3-Preview-Canary",
        "messages": body["effective_request"]["messages"],
        "stream": True,
        "max_tokens": 320,
        "temperature": 0.6,
        "top_p": 0.87,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.0,
        "extra_body": {
            "top_k": 37,
            "min_p": 0.07,
            "repeat_penalty": 1.08,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        "seed_policy": "generated_at_send_time",
        "omitted_fields": [],
    }
    assert body["budget"]["context_limit"] == 4096
    assert body["budget"]["configured_max_output"] == 320
    assert body["budget"]["estimated_input_tokens"] > 0
    assert body["budget"]["included_history_count"] == 3
    assert body["budget"]["content_truncated"] is False
    assert any(section["content"] == COMPOSER_CANARY for section in body["sections"])
    assert any("Mara" in section["content"] for section in body["sections"])

    serialized = _serialized(body)
    assert COMPOSER_CANARY in serialized
    assert PRIVATE_KEY_CANARY not in serialized
    assert PRIVATE_URL_CANARY not in serialized
    assert PRIVATE_PATH_CANARY not in serialized
    assert REJECTED_PROSE_CANARY not in serialized
    assert "authorization" not in serialized.casefold()
    assert '"seed"' not in serialized


def test_send_preview_rejects_hostile_origin_and_preserves_call_origin_contract(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        headers={"Origin": HOSTILE_ORIGIN},
        json=_send_payload(),
    )
    call_response = prompt_preview_fixture.client.post(
        "/api/calls/start",
        headers={"Origin": HOSTILE_ORIGIN},
        json={"thread_id": THREAD_ID},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "call_origin_not_allowed"
    assert call_response.status_code == 403
    assert call_response.json()["detail"] == response.json()["detail"]


@pytest.mark.parametrize(
    ("payload", "canary"),
    [
        (_send_payload(private_unknown=PRIVATE_KEY_CANARY), PRIVATE_KEY_CANARY),
        (_send_payload(composer_text="   "), "   "),
        (_send_payload(thread_id="missing-thread-" + PRIVATE_PATH_CANARY), PRIVATE_PATH_CANARY),
    ],
)
def test_send_preview_validation_and_not_found_errors_are_sanitized(
    prompt_preview_fixture: PromptPreviewFixture,
    payload: dict[str, object],
    canary: str,
) -> None:
    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        headers={"Origin": ALLOWED_ORIGIN},
        json=payload,
    )

    assert response.status_code in {404, 422}
    serialized = _serialized(response.json())
    assert canary not in serialized
    assert PRIVATE_KEY_CANARY not in serialized
    assert PRIVATE_URL_CANARY not in serialized


def test_send_preview_never_generates_or_persists(
    prompt_preview_fixture: PromptPreviewFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preview crossed a generation or mutation boundary")

    llm_stream = importlib.import_module("app.domain.llm_stream")
    settings_service = importlib.import_module("app.domain.settings_service")
    chat_repository = importlib.import_module("app.api.chat")
    monkeypatch.setattr(llm_stream, "_random_chat_completion_seed", forbidden)
    monkeypatch.setattr(settings_service.SettingsService, "update", forbidden)
    monkeypatch.setattr(chat_repository.ChatRepository, "append_user_message", forbidden)

    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        headers={"Origin": ALLOWED_ORIGIN},
        json=_send_payload(),
    )

    assert response.status_code == 200
    after = asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker))
    assert after == before


def test_prompt_preview_openapi_is_strict_and_credential_free(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    schema = prompt_preview_fixture.client.get("/openapi.json").json()
    operation = schema["paths"]["/api/prompt-preview"]["post"]
    body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    request_schemas = [
        schema["components"]["schemas"][item["$ref"].rsplit("/", 1)[-1]]
        for item in body_schema["oneOf"]
    ]
    operation_text = _serialized(operation).casefold()

    assert body_schema["discriminator"]["propertyName"] == "action"
    assert len(request_schemas) == 6
    assert all(item["additionalProperties"] is False for item in request_schemas)
    assert request_schemas[0]["required"] == ["thread_id", "composer_text", "action"]
    for forbidden_name in (
        "api_key",
        "authorization",
        "base_url",
        "endpoint",
        "storage_path",
        "seed",
        "rejected_prose",
    ):
        assert forbidden_name not in operation_text


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("send", {"composer_text": COMPOSER_CANARY}),
        ("regenerate", {"target_message_id": "msg_preview_002"}),
        ("swipe", {"target_message_id": "msg_preview_002"}),
        (
            "continue",
            {
                "target_message_id": "msg_preview_002",
                "composer_text": "assistant prefix café 🫀",
            },
        ),
        ("call_offer", {}),
        ("call_turn", {"composer_text": "spoken turn 漢字 🫀"}),
    ],
)
def test_every_action_matches_the_shared_composer_and_adapter_exactly(
    prompt_preview_fixture: PromptPreviewFixture,
    action: str,
    extra: dict[str, str],
) -> None:
    payload = {"action": action, "thread_id": THREAD_ID, **extra}

    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        headers={"Origin": ALLOWED_ORIGIN},
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    expected = asyncio.run(
        _direct_action_projection(
            prompt_preview_fixture,
            action=action,
            target_message_id=extra.get("target_message_id"),
            composer_text=extra.get("composer_text"),
        )
    )
    assert body["action"] == action
    assert [
        (
            section["section_id"],
            section["logical_role"],
            section["content"],
            section["estimated_tokens"],
        )
        for section in body["sections"]
    ] == expected["sections"]
    assert [
        (message["role"], message["content"], tuple(message["section_ids"]))
        for message in body["wire_messages"]
    ] == expected["wire_messages"]
    assert body["effective_request"]["messages"] == expected["request"]["messages"]
    assert body["effective_request"]["max_tokens"] == expected["request"]["max_tokens"]
    assert body["effective_request"]["extra_body"] == expected["request"].get("extra_body")
    assert body["adapter"]["effective"] == expected["effective_adapter"]
    assert body["budget"]["estimated_input_tokens"] == expected["estimated_input_tokens"]
    assert body["budget"]["dropped_history_count"] == expected["dropped_history_count"]


def test_action_specific_branch_prefill_and_call_limits_are_truthful(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    regenerate = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        json={
            "action": "regenerate",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
        },
    ).json()
    continued = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        json={
            "action": "continue",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
            "composer_text": "immutable prefix 🫀",
        },
    ).json()
    call_offer = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        json={"action": "call_offer", "thread_id": THREAD_ID},
    ).json()
    call_turn = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        json={
            "action": "call_turn",
            "thread_id": THREAD_ID,
            "composer_text": "new live turn",
        },
    ).json()

    assert "Prior assistant turn." not in _serialized(regenerate["wire_messages"])
    assert continued["wire_messages"][-1] == {
        "order": len(continued["wire_messages"]) - 1,
        "role": "assistant",
        "content": "immutable prefix 🫀",
        "section_ids": ["assistant_prefill"],
    }
    assert call_offer["budget"]["max_messages"] == 48
    assert call_offer["budget"]["max_content_length"] == 20_000
    assert len(call_offer["wire_messages"]) <= 48
    assert call_turn["budget"]["max_messages"] is None
    assert call_turn["budget"]["max_content_length"] is None


def test_refusal_activity_zero_one_many_is_ordered_and_metadata_only(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    empty = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    ).json()
    assert empty["recent_refusal_activity"] == []

    records = [
        RefusalActivityRecord(
            action="send",
            attempt=index,
            reason_code="policy_or_safety" if index == 1 else "safe_prefix",
            prefix_characters=20 + index,
            prefix_estimated_tokens=6 + index,
            retry_count=index - 1,
            release_ms=None if index == 1 else 12.5,
            decision_ms=3.5 * index,
            terminal_outcome="retry" if index == 1 else "accepted",
            timestamp=f"2026-08-31T00:00:0{index}Z",
        )
        for index in (1, 2)
    ]
    for record in records:
        prompt_preview_fixture.activity.append(THREAD_ID, record)

    populated = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    ).json()["recent_refusal_activity"]
    assert populated == [record.to_dict() for record in records]
    assert [row["timestamp"] for row in populated] == sorted(
        row["timestamp"] for row in populated
    )
    serialized = _serialized(populated).casefold()
    for forbidden in (
        "prompt",
        "history",
        "content",
        "generated",
        "rejected",
        "seed",
        PRIVATE_KEY_CANARY.casefold(),
    ):
        assert forbidden not in serialized


def test_lorebook_stays_persisted_but_never_enters_any_action_preview(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    actions = [
        _send_payload(),
        {
            "action": "regenerate",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
        },
        {
            "action": "swipe",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
        },
        {
            "action": "continue",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
            "composer_text": "prefix",
        },
        {"action": "call_offer", "thread_id": THREAD_ID},
        {"action": "call_turn", "thread_id": THREAD_ID, "composer_text": "turn"},
    ]

    for payload in actions:
        response = prompt_preview_fixture.client.post("/api/prompt-preview", json=payload)
        assert response.status_code == 200
        assert REJECTED_PROSE_CANARY not in response.text

    assert asyncio.run(
        _stored_lorebook(prompt_preview_fixture.sessionmaker)
    ) == {"secret": REJECTED_PROSE_CANARY}


@pytest.mark.parametrize(
    ("examples", "expected_groups"),
    [
        (None, 0),
        ("<START>\n{{user}}: one\n{{char}}: answer", 1),
        (
            "<START>\n{{user}}: one\n{{char}}: answer one\n"
            "<START>\n{{user}}: two\n{{char}}: answer two",
            2,
        ),
    ],
)
def test_zero_one_many_example_groups_and_blank_optional_sections_are_exact(
    prompt_preview_fixture: PromptPreviewFixture,
    examples: str | None,
    expected_groups: int,
) -> None:
    asyncio.run(
        _set_thread_examples_and_optional_sections(
            prompt_preview_fixture.sessionmaker,
            examples,
        )
    )

    body = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    ).json()

    assert body["budget"]["included_example_group_count"] == expected_groups
    example_ids = [
        section["atomic_group_id"]
        for section in body["sections"]
        if section["section_id"].startswith("example:")
    ]
    assert len(set(example_ids)) == expected_groups
    assert any(
        section["section_id"] == "late_phi" and section["content"] == "Continue as Mara."
        for section in body["sections"]
    )


def test_drops_are_counted_and_mandatory_overflow_is_typed(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    asyncio.run(_append_large_preview_history(prompt_preview_fixture.sessionmaker))
    dropped = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    )
    assert dropped.status_code == 200
    assert dropped.json()["budget"]["dropped_history_count"] > 0

    asyncio.run(
        _set_thread_system_prompt(prompt_preview_fixture.sessionmaker, "x" * 20_000)
    )
    overflow = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    )
    assert overflow.status_code == 422
    assert overflow.json()["detail"]["code"] == "prompt_budget_exceeded"
    assert PRIVATE_KEY_CANARY not in overflow.text


def test_barrier_synchronized_previews_do_not_cross_contaminate_or_persist(
    prompt_preview_fixture: PromptPreviewFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_module = importlib.import_module("app.api.prompt_preview")
    original = preview_module.build_structured_prompt
    barrier = threading.Barrier(2)

    async def synchronized(*args: object, **kwargs: object) -> object:
        await asyncio.to_thread(barrier.wait, 3.0)
        return await original(*args, **kwargs)

    monkeypatch.setattr(preview_module, "build_structured_prompt", synchronized)
    before = asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker))
    drafts = ["concurrent alpha café", "concurrent beta 漢字"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                prompt_preview_fixture.client.post,
                "/api/prompt-preview",
                json=_send_payload(composer_text=draft),
            )
            for draft in drafts
        ]
        responses = [future.result(timeout=5.0) for future in futures]

    assert [response.status_code for response in responses] == [200, 200]
    for own, other, response in zip(drafts, reversed(drafts), responses, strict=True):
        assert own in response.text
        assert other not in response.text
    assert asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker)) == before


def test_generic_adapter_omissions_and_qwen_role_remapping_are_explicit(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    qwen = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    ).json()
    asyncio.run(_set_endpoint_adapter(prompt_preview_fixture.sessionmaker))
    generic = prompt_preview_fixture.client.post(
        "/api/prompt-preview", json=_send_payload()
    ).json()

    assert qwen["adapter"]["effective"] == "qwen_llama_server"
    assert qwen["effective_request"]["extra_body"]["top_k"] == 37
    assert any(
        message["role"] == "user" and "Card ending for Mara." in message["content"]
        for message in qwen["wire_messages"]
    )
    assert generic["adapter"] == {
        "configured": "generic_openai_compatible",
        "effective": "generic_openai_compatible",
        "name": "generic_openai_compatible",
        "version": "rayme-generation-request-v1",
    }
    assert generic["effective_request"]["extra_body"] is None
    assert generic["effective_request"]["omitted_fields"] == [
        "extra_body.top_k",
        "extra_body.min_p",
        "extra_body.repeat_penalty",
        "extra_body.chat_template_kwargs",
    ]
    assert generic["configured_sampler"]["top_k"] == 37
    assert generic["configured_sampler"]["repetition_penalty"] == 1.08
    assert any(
        message["role"] == "system" and message["content"] == "Card ending for Mara."
        for message in generic["wire_messages"]
    )


def test_empty_continue_uses_selected_assistant_and_legacy_nulls_remain_truthful(
    prompt_preview_fixture: PromptPreviewFixture,
) -> None:
    asyncio.run(_set_legacy_null_snapshots(prompt_preview_fixture.sessionmaker))

    response = prompt_preview_fixture.client.post(
        "/api/prompt-preview",
        json={
            "action": "continue",
            "thread_id": THREAD_ID,
            "target_message_id": "msg_preview_002",
            "composer_text": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["wire_messages"][-1]["role"] == "assistant"
    assert body["wire_messages"][-1]["content"] == "Prior assistant turn."
    assert any(
        section["section_id"] == "description" and section["content"] == "Description: "
        for section in body["sections"]
    )
    assert all(section["content"] is not None for section in body["sections"])


def test_cancelled_preview_propagates_and_leaves_durable_state_unchanged(
    prompt_preview_fixture: PromptPreviewFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_module = importlib.import_module("app.api.prompt_preview")
    started = asyncio.Event()
    never_release = asyncio.Event()

    async def held_build(*_args: object, **_kwargs: object) -> object:
        started.set()
        await never_release.wait()
        raise AssertionError("cancelled preview resumed unexpectedly")

    monkeypatch.setattr(preview_module, "build_structured_prompt", held_build)
    before = asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker))

    async def cancel_preview() -> None:
        from fastapi import Response

        async with prompt_preview_fixture.sessionmaker() as session:
            task = asyncio.create_task(
                preview_module.preview_prompt(
                    preview_module.SendPromptPreviewRequest(**_send_payload()),
                    Response(),
                    session,
                    prompt_preview_fixture.app.state.settings,
                    prompt_preview_fixture.activity,
                )
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(cancel_preview())
    assert asyncio.run(_persistent_counts(prompt_preview_fixture.sessionmaker)) == before


async def _direct_action_projection(
    fixture: PromptPreviewFixture,
    *,
    action: str,
    target_message_id: str | None,
    composer_text: str | None,
) -> dict[str, object]:
    from app.domain.generation_profiles import build_generation_request
    from app.domain.message_actions import SqlAlchemyMessageActionRepository
    from app.domain.prompt_builder import SqlAlchemyPromptRepository, build_structured_prompt
    from app.domain.settings_service import SettingsService

    async with fixture.sessionmaker() as session:
        endpoint = await SettingsService(session, fixture.app.state.settings).read()
        until_message_id = None
        effective_composer = composer_text
        repository: object = SqlAlchemyPromptRepository(session)
        if action in {"regenerate", "swipe", "continue"}:
            assert target_message_id is not None
            repository = SqlAlchemyMessageActionRepository(session)
            context = await repository.get_generation_context(
                target_message_id,
                include_target=False,
            )
            assert context.thread_id == THREAD_ID
            until_message_id = context.until_message_id
            if action == "continue":
                effective_composer = composer_text or context.selected_content
                if not effective_composer:
                    context = await repository.get_generation_context(
                        target_message_id,
                        include_target=True,
                    )
                    until_message_id = context.until_message_id
        prompt = await build_structured_prompt(
            THREAD_ID,
            settings=endpoint.prompt_generation,
            repository=repository,  # type: ignore[arg-type]
            until_message_id=until_message_id,
            action=action,  # type: ignore[arg-type]
            composer_text=effective_composer,
        )
        request = build_generation_request(
            model=endpoint.llm_model,
            messages=prompt.transmitted_message_candidates,
            settings=endpoint.prompt_generation,
            seed=0,
            attempt=1,
            disable_thinking=endpoint.llm_disable_thinking,
        )
        return {
            "sections": [
                (
                    section.section_id,
                    section.logical_role,
                    section.content,
                    section.estimated_tokens,
                )
                for section in prompt.sections
            ],
            "wire_messages": [
                (message.role, message.content, message.section_ids)
                for message in request.messages
            ],
            "request": request.to_openai_kwargs(),
            "effective_adapter": request.effective_adapter,
            "estimated_input_tokens": prompt.estimated_input_tokens,
            "dropped_history_count": prompt.dropped_history_count,
        }


async def _stored_lorebook(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> object:
    async with sessionmaker() as session:
        thread = await session.get(Thread, THREAD_ID)
        assert thread is not None
        return thread.character_snapshot_lorebook_json


async def _set_thread_examples_and_optional_sections(
    sessionmaker: async_sessionmaker[AsyncSession],
    examples: str | None,
) -> None:
    async with sessionmaker() as session:
        thread = await session.get(Thread, THREAD_ID)
        assert thread is not None
        thread.character_snapshot_mes_example = examples
        thread.character_snapshot_post_history_instructions = ""
        await session.commit()


async def _append_large_preview_history(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        session.add_all(
            [
                Message(
                    id=f"msg_preview_long_{index:03d}",
                    thread_id=THREAD_ID,
                    message_kind="user_text" if index % 2 == 0 else "ai_text",
                    role="user" if index % 2 == 0 else "assistant",
                    sequence=index + 2,
                    content_text=f"long history {index:03d} " + ("漢字🫀" * 150),
                )
                for index in range(40)
            ]
        )
        await session.commit()


async def _set_thread_system_prompt(
    sessionmaker: async_sessionmaker[AsyncSession],
    content: str,
) -> None:
    async with sessionmaker() as session:
        thread = await session.get(Thread, THREAD_ID)
        assert thread is not None
        thread.character_snapshot_system_prompt = content
        await session.commit()


async def _set_endpoint_adapter(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        row = await session.get(AppSetting, SETTINGS_KEY)
        assert row is not None and isinstance(row.value_json, dict)
        values = dict(row.value_json)
        prompt_generation = dict(values["prompt_generation"])
        prompt_generation["model_profile"] = "generic_openai_compatible"
        values["prompt_generation"] = prompt_generation
        values["llm_model"] = "generic-preview-model"
        values["llm_disable_thinking"] = False
        row.value_json = values
        await session.commit()


async def _set_legacy_null_snapshots(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        thread = await session.get(Thread, THREAD_ID)
        assert thread is not None
        thread.character_snapshot_description = None
        thread.character_snapshot_personality = None
        thread.character_snapshot_scenario = None
        thread.character_snapshot_mes_example = None
        thread.character_snapshot_post_history_instructions = None
        await session.commit()
