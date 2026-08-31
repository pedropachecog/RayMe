"""Safe, exact, side-effect-free Prompt Inspector backend contracts."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import Iterator
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

    if preview_module is not None:
        async def override_session() -> Iterator[AsyncSession]:
            async with sessionmaker() as session:
                yield session

        app.dependency_overrides[preview_module.get_prompt_preview_session] = override_session

    with TestClient(app) as client:
        yield PromptPreviewFixture(client=client, app=app, sessionmaker=sessionmaker)

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
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request_schema = schema["components"]["schemas"][request_ref.rsplit("/", 1)[-1]]
    operation_text = _serialized(operation).casefold()

    assert request_schema["additionalProperties"] is False
    assert request_schema["required"] == ["action", "thread_id", "composer_text"]
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
