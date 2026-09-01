"""Credential-free, side-effect-free effective prompt request inspection."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.origin import enforce_same_origin, get_runtime_settings
from app.config import Settings
from app.domain.generation_profiles import GenerationRequest, build_generation_request
from app.domain.llm_stream import MAX_SEMANTIC_ATTEMPTS
from app.domain.message_actions import (
    InvalidMessageActionError,
    MessageActionNotFoundError,
    SqlAlchemyMessageActionRepository,
)
from app.domain.prompt_builder import (
    PromptBudgetExceeded,
    PromptBuildResult,
    SqlAlchemyPromptRepository,
    build_structured_prompt,
)
from app.domain.refusal_activity import (
    RefusalActivityStore,
    get_process_local_refusal_activity_store,
)
from app.domain.refusal_guard import (
    REFUSAL_ESTIMATOR_VERSION,
    REFUSAL_PREFIX_MAX_CHARACTERS,
    REFUSAL_PREFIX_MAX_ESTIMATED_TOKENS,
    REFUSAL_SAFE_SENTENCE_MIN_VISIBLE_CHARACTERS,
)
from app.domain.settings_service import SettingsService
from app.domain.thread_service import ThreadNotFoundError
from app.storage.session import get_session

PROMPT_PREVIEW_REQUEST_SHAPE_VERSION = "rayme-generation-request-v1"
PROMPT_PREVIEW_INVALID = "invalid_prompt_preview_request"
PROMPT_PREVIEW_NOT_FOUND = "prompt_preview_thread_not_found"
_NO_STORE = {"Cache-Control": "no-store"}


class SanitizedValidationRoute(APIRoute):
    """Prevent rejected request bodies from being reflected by validation errors."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def sanitized(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={
                        "detail": {
                            "code": PROMPT_PREVIEW_INVALID,
                            "message": "Prompt preview request is invalid.",
                        }
                    },
                    headers=_NO_STORE,
                )

        return sanitized


router = APIRouter(
    prefix="/api/prompt-preview",
    tags=["prompt-preview"],
    route_class=SanitizedValidationRoute,
)


class PromptPreviewRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1, max_length=128)

    @field_validator("thread_id")
    @classmethod
    def require_visible_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class ComposerPromptPreviewRequest(PromptPreviewRequestBase):
    composer_text: str = Field(min_length=1, max_length=20_000)

    @field_validator("composer_text")
    @classmethod
    def require_visible_composer_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class SendPromptPreviewRequest(ComposerPromptPreviewRequest):
    action: Literal["send"]


class RegeneratePromptPreviewRequest(PromptPreviewRequestBase):
    action: Literal["regenerate"]
    target_message_id: str = Field(min_length=1, max_length=128)


class SwipePromptPreviewRequest(PromptPreviewRequestBase):
    action: Literal["swipe"]
    target_message_id: str = Field(min_length=1, max_length=128)


class ContinuePromptPreviewRequest(PromptPreviewRequestBase):
    action: Literal["continue"]
    target_message_id: str = Field(min_length=1, max_length=128)
    composer_text: str = Field(default="", max_length=20_000)


class CallOfferPromptPreviewRequest(PromptPreviewRequestBase):
    action: Literal["call_offer"]


class CallTurnPromptPreviewRequest(ComposerPromptPreviewRequest):
    action: Literal["call_turn"]


PromptPreviewRequest = Annotated[
    SendPromptPreviewRequest
    | RegeneratePromptPreviewRequest
    | SwipePromptPreviewRequest
    | ContinuePromptPreviewRequest
    | CallOfferPromptPreviewRequest
    | CallTurnPromptPreviewRequest,
    Field(discriminator="action"),
]


class PreviewAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: Literal["auto", "qwen_llama_server", "generic_openai_compatible"]
    effective: Literal["qwen_llama_server", "generic_openai_compatible"]
    name: Literal["qwen_llama_server", "generic_openai_compatible"]
    version: Literal["rayme-generation-request-v1"]


class PreviewSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=0)
    section_id: str
    logical_role: Literal["system", "user", "assistant"]
    content: str
    source: str
    override_state: str
    mandatory: bool
    estimated_tokens: int = Field(ge=0)
    atomic_group_id: str | None
    included: Literal[True] = True


class PreviewWireMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=0)
    role: Literal["system", "user", "assistant"]
    content: str
    section_ids: list[str]


class PreviewTemplateOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_thinking: bool


class PreviewExtraBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int
    min_p: float
    repeat_penalty: float
    chat_template_kwargs: PreviewTemplateOptions | None = None


class PreviewEffectiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[dict[Literal["role", "content"], str]]
    stream: Literal[True]
    max_tokens: int
    temperature: float
    top_p: float
    presence_penalty: float
    frequency_penalty: float
    extra_body: PreviewExtraBody | None
    seed_policy: Literal["generated_at_send_time"]
    omitted_fields: list[str]


class PreviewConfiguredSampler(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens: int
    temperature: float
    top_p: float
    min_p: float
    top_k: int
    repetition_penalty: float
    presence_penalty: float
    frequency_penalty: float


class PreviewBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_limit: int
    configured_max_output: int
    safety_margin: int
    input_budget: int
    estimator_version: str
    estimated_input_tokens: int
    included_history_count: int
    dropped_history_count: int
    included_example_group_count: int
    dropped_example_group_count: int
    max_messages: int | None
    max_content_length: int | None
    content_truncated: Literal[False] = False


class PreviewRefusalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int
    max_retries: int
    prefix_max_characters: int
    prefix_max_estimated_tokens: int
    safe_sentence_min_visible_characters: int
    estimator_version: str
    retry_correction_present: Literal[True] = True
    correction_role: Literal["system", "user"]
    seed_policy: Literal["fresh_at_send_time_per_attempt"]
    correction_prose_exposed: Literal[False] = False
    rejected_prose_exposed: Literal[False] = False
    exhausted_error_code: Literal["llm_refusal_exhausted"]


class PreviewRefusalActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    attempt: int
    reason_code: str
    prefix_characters: int
    prefix_estimated_tokens: int
    retry_count: int
    release_ms: float | None
    decision_ms: float | None
    terminal_outcome: str
    timestamp: str


class PromptPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["send", "regenerate", "swipe", "continue", "call_offer", "call_turn"]
    variant: str
    mode: str
    prompt_contract_version: str
    request_shape_version: Literal["rayme-generation-request-v1"]
    thread_id: str
    configured_model: str
    adapter: PreviewAdapter
    configured_sampler: PreviewConfiguredSampler
    sections: list[PreviewSection]
    wire_messages: list[PreviewWireMessage]
    effective_request: PreviewEffectiveRequest
    budget: PreviewBudget
    warnings: list[str]
    refusal_policy: PreviewRefusalPolicy
    recent_refusal_activity: list[PreviewRefusalActivity]


async def get_prompt_preview_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_prompt_preview_refusal_activity_store() -> RefusalActivityStore:
    return get_process_local_refusal_activity_store()


@router.post(
    "",
    response_model=PromptPreviewResponse,
    dependencies=[Depends(enforce_same_origin)],
)
async def preview_prompt(
    payload: PromptPreviewRequest,
    response: Response,
    session: AsyncSession = Depends(get_prompt_preview_session),
    runtime_settings: Settings = Depends(get_runtime_settings),
    refusal_activity: RefusalActivityStore = Depends(get_prompt_preview_refusal_activity_store),
) -> PromptPreviewResponse:
    """Compose and serialize a request snapshot without generation or persistence."""

    response.headers.update(_NO_STORE)
    endpoint_settings = await SettingsService(session, runtime_settings).read()
    try:
        prompt = await _build_action_prompt(
            payload,
            session=session,
            settings=endpoint_settings.prompt_generation,
        )
    except (ThreadNotFoundError, MessageActionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": PROMPT_PREVIEW_NOT_FOUND,
                "message": "Prompt preview thread was not found.",
            },
            headers=_NO_STORE,
        ) from exc
    except InvalidMessageActionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_prompt_preview_target",
                "message": "Prompt preview target is invalid.",
            },
            headers=_NO_STORE,
        ) from exc
    except PromptBudgetExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.to_public_dict(),
            headers=_NO_STORE,
        ) from exc

    generation = build_generation_request(
        model=endpoint_settings.llm_model,
        messages=prompt.transmitted_message_candidates,
        settings=endpoint_settings.prompt_generation,
        seed=0,
        attempt=1,
        disable_thinking=endpoint_settings.llm_disable_thinking,
    )
    return _response_projection(
        payload.thread_id,
        prompt=prompt,
        generation=generation,
        activity=refusal_activity,
    )


def _response_projection(
    thread_id: str,
    *,
    prompt: PromptBuildResult,
    generation: GenerationRequest,
    activity: RefusalActivityStore,
) -> PromptPreviewResponse:
    request_kwargs = generation.to_openai_kwargs()
    extra_body = request_kwargs.get("extra_body")
    example_groups = {
        section.atomic_group_id
        for section in prompt.sections
        if section.atomic_group_id and section.section_id.startswith("example:")
    }
    sections = [
        PreviewSection(
            order=order,
            section_id=section.section_id,
            logical_role=section.logical_role,
            content=section.content,
            source=section.source,
            override_state=section.override_state,
            mandatory=section.mandatory,
            estimated_tokens=section.estimated_tokens,
            atomic_group_id=section.atomic_group_id,
        )
        for order, section in enumerate(prompt.sections)
    ]
    wire_messages = [
        PreviewWireMessage(
            order=order,
            role=message.role,
            content=message.content,
            section_ids=list(message.section_ids),
        )
        for order, message in enumerate(generation.messages)
    ]
    sampler = generation.sampler
    if sampler is None:
        raise RuntimeError("prompt preview requires configured generation settings")
    return PromptPreviewResponse(
        action=prompt.action,
        variant=prompt.variant,
        mode=prompt.mode,
        prompt_contract_version=prompt.prompt_contract_version,
        request_shape_version=PROMPT_PREVIEW_REQUEST_SHAPE_VERSION,
        thread_id=thread_id,
        configured_model=generation.model,
        adapter=PreviewAdapter(
            configured=generation.configured_adapter,
            effective=generation.effective_adapter,
            name=generation.effective_adapter,
            version=PROMPT_PREVIEW_REQUEST_SHAPE_VERSION,
        ),
        configured_sampler=PreviewConfiguredSampler(
            max_tokens=sampler.max_tokens,
            temperature=sampler.temperature,
            top_p=sampler.top_p,
            min_p=sampler.min_p,
            top_k=sampler.top_k,
            repetition_penalty=sampler.repetition_penalty,
            presence_penalty=sampler.presence_penalty,
            frequency_penalty=sampler.frequency_penalty,
        ),
        sections=sections,
        wire_messages=wire_messages,
        effective_request=PreviewEffectiveRequest(
            model=generation.model,
            messages=[message.to_openai_dict() for message in generation.messages],
            stream=True,
            max_tokens=sampler.max_tokens,
            temperature=sampler.temperature,
            top_p=sampler.top_p,
            presence_penalty=sampler.presence_penalty,
            frequency_penalty=sampler.frequency_penalty,
            extra_body=PreviewExtraBody.model_validate(extra_body) if extra_body else None,
            seed_policy="generated_at_send_time",
            omitted_fields=_omitted_request_fields(
                generation,
                has_template_options=bool(
                    isinstance(extra_body, dict)
                    and extra_body.get("chat_template_kwargs") is not None
                ),
            ),
        ),
        budget=PreviewBudget(
            context_limit=prompt.context_limit,
            configured_max_output=prompt.configured_max_output,
            safety_margin=prompt.safety_margin,
            input_budget=prompt.input_budget,
            estimator_version=prompt.estimator_version,
            estimated_input_tokens=prompt.estimated_input_tokens,
            included_history_count=sum(
                section.section_id.startswith("history:") for section in prompt.sections
            ),
            dropped_history_count=prompt.dropped_history_count,
            included_example_group_count=len(example_groups),
            dropped_example_group_count=prompt.dropped_example_group_count,
            max_messages=prompt.target_constraints.max_messages,
            max_content_length=prompt.target_constraints.max_content_length,
        ),
        warnings=list(prompt.warnings),
        refusal_policy=PreviewRefusalPolicy(
            max_attempts=MAX_SEMANTIC_ATTEMPTS,
            max_retries=MAX_SEMANTIC_ATTEMPTS - 1,
            prefix_max_characters=REFUSAL_PREFIX_MAX_CHARACTERS,
            prefix_max_estimated_tokens=REFUSAL_PREFIX_MAX_ESTIMATED_TOKENS,
            safe_sentence_min_visible_characters=REFUSAL_SAFE_SENTENCE_MIN_VISIBLE_CHARACTERS,
            estimator_version=REFUSAL_ESTIMATOR_VERSION,
            correction_role=(
                "user" if generation.effective_adapter == "qwen_llama_server" else "system"
            ),
            seed_policy="fresh_at_send_time_per_attempt",
            exhausted_error_code="llm_refusal_exhausted",
        ),
        recent_refusal_activity=[
            PreviewRefusalActivity.model_validate(record.to_dict())
            for record in activity.list_recent(thread_id)
        ],
    )


async def _build_action_prompt(
    payload: PromptPreviewRequest,
    *,
    session: AsyncSession,
    settings: Any,
) -> PromptBuildResult:
    repository: Any = SqlAlchemyPromptRepository(session)
    until_message_id: str | None = None
    composer_text: str | None = getattr(payload, "composer_text", None)

    if isinstance(
        payload,
        (
            RegeneratePromptPreviewRequest,
            SwipePromptPreviewRequest,
            ContinuePromptPreviewRequest,
        ),
    ):
        repository = SqlAlchemyMessageActionRepository(session)
        context = await repository.get_generation_context(
            payload.target_message_id,
            include_target=False,
        )
        if context.thread_id != payload.thread_id:
            raise MessageActionNotFoundError(payload.target_message_id)
        if context.role != "assistant" or not context.message_kind.startswith("ai_"):
            raise InvalidMessageActionError("Message action requires an AI message")
        until_message_id = context.until_message_id
        if isinstance(payload, ContinuePromptPreviewRequest):
            composer_text = payload.composer_text or context.selected_content
            if not composer_text:
                context = await repository.get_generation_context(
                    payload.target_message_id,
                    include_target=True,
                )
                until_message_id = context.until_message_id

    return await build_structured_prompt(
        payload.thread_id,
        settings=settings,
        repository=repository,
        until_message_id=until_message_id,
        action=payload.action,
        composer_text=composer_text,
    )


def _omitted_request_fields(
    generation: GenerationRequest,
    *,
    has_template_options: bool,
) -> list[str]:
    if generation.effective_adapter == "generic_openai_compatible":
        return [
            "extra_body.top_k",
            "extra_body.min_p",
            "extra_body.repeat_penalty",
            "extra_body.chat_template_kwargs",
        ]
    if not has_template_options:
        return ["extra_body.chat_template_kwargs"]
    return []


__all__ = [
    "PROMPT_PREVIEW_REQUEST_SHAPE_VERSION",
    "PromptPreviewResponse",
    "PromptPreviewRequest",
    "SendPromptPreviewRequest",
    "get_prompt_preview_refusal_activity_store",
    "get_prompt_preview_session",
    "router",
]
