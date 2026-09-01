"""Bounded pre-release guard for explicit generic LLM refusals."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Literal

REFUSAL_PREFIX_MAX_CHARACTERS = 384
REFUSAL_PREFIX_MAX_ESTIMATED_TOKENS = 96
REFUSAL_SAFE_SENTENCE_MIN_VISIBLE_CHARACTERS = 24
REFUSAL_ESTIMATOR_VERSION = "unicode-codepoints-v1"

_WHITESPACE_RE = re.compile(r"\s+")
_APOSTROPHE_TRANSLATION = str.maketrans("‘’ʼ＇", "''''")
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]+[\"')\]]*(?=\s|$)")
_REFUSAL_VERB_RE = re.compile(
    r"(?:\b(?:i\s+)?(?:cannot|can\s+not|can't|won't|will\s+not|must\s+not)\s+"
    r"(?:continue|assist|help|comply|provide|engage|participate|fulfill|generate|"
    r"create|write|do)\b|"
    r"\b(?:i(?:'m|\s+am)\s+)?unable\s+to\s+"
    r"(?:continue|assist|help|comply|provide|engage|participate|fulfill|generate|"
    r"create|write|do)\b|"
    r"\b(?:i\s+)?(?:must|need\s+to|have\s+to)\s+(?:decline|refuse)\b|"
    r"\b(?:i\s+)?(?:decline|refuse)\s+to\s+"
    r"(?:continue|assist|help|comply|provide|engage|participate|fulfill|generate|"
    r"create|write|do)\b|"
    r"\b(?:i\s+)?(?:decline|refuse)\s+(?:this|that|the)\s+"
    r"(?:request|conversation|task|prompt)\b)"
)
_DECLARATIVE_META_POLICY_REFUSAL_RE = re.compile(
    r"(?:^|(?<=[.!?])\s*)(?:this|that)\s+"
    r"(?:roleplay|scene|request|conversation|prompt|content)\s+"
    r"(?:violates?|breaks?|conflicts?\s+with|goes\s+against)\s+"
    r"(?:my\s+)?(?:policy|policies|guideline|guidelines|safety|"
    r"content\s+restriction|content\s+restrictions)\b"
)
_IDENTITY_RE = re.compile(
    r"\b(?:as\s+an?\s+)?(?:ai|artificial\s+intelligence|language\s+model|"
    r"assistant|chatbot)\b"
)
_DIRECT_IDENTITY_DISCLAIMER_RE = re.compile(
    r"(?:^|(?<=[.!?])\s*)i(?:'m|\s+am)\b.{0,80}\bassistant\b.{0,80}\b"
    r"not\s+(?:for\s+(?:that|this)\s+(?:kind|type)\s+of\s+content|"
    r"(?:an?\s+)?(?:erotic|sexual)\s+one)\b"
)
_DIRECT_REQUEST_REFUSAL_STEM = (
    r"(?:^|(?<=[.!?])\s*)i\s+"
    r"(?:(?:cannot|can\s+not|can't|won't|will\s+not|must\s+not)\s+"
    r"(?:continue|assist|help|comply|provide|engage|participate|fulfill|generate|"
    r"create|write|do)|(?:am|'m)\s+unable\s+to\s+"
    r"(?:continue|assist|help|comply|provide|engage|participate|fulfill|generate|"
    r"create|write|do))\b(?:\s+with)?\s+(?:that|this|the)\s+"
    r"(?:specific\s+)?request\b"
)
_DIRECT_REQUEST_REFUSAL_RE = re.compile(
    _DIRECT_REQUEST_REFUSAL_STEM
    + r"(?=\s*[.!?]|\s+to\s+(?:generate|provide|write|create)\b)"
)
_DIRECT_REQUEST_REFUSAL_AT_END_RE = re.compile(_DIRECT_REQUEST_REFUSAL_STEM + r"\s*$")
_POLICY_RE = re.compile(
    r"\b(?:policy|policies|guideline|guidelines|safety|"
    r"content\s+restriction|content\s+restrictions|not\s+allowed|violat(?:e|es|ing)|"
    r"sexually\s+explicit\s+content|"
    r"explicit\s+(?:(?:sexual\s+)?or\s+erotic|sexual|erotic)\s+content|"
    r"explicit\s+(?:sexual|erotic)\s+descriptions?\b[^.!?]{0,48}\b"
    r"or\s+(?:explicit\s+)?(?:sexual|erotic)\s+content)\b"
)
_APOLOGY_RE = re.compile(r"(?:^|\s)(?:i(?:'m|\s+am)\s+)?sorry\b|\bapologi[sz](?:e|ing)\b")
_REDIRECT_RE = re.compile(
    r"\b(?:instead|however)\b.{0,80}\b(?:can|could)\s+(?:help|offer|provide)\b|"
    r"\b(?:can|could)\s+(?:help|offer|provide)\s+(?:with\s+)?(?:something|another|alternative)\b|"
    r"\b(?:but\s+)?i(?:'m|\s+am)\s+here\s+to\s+help\b|"
    r"\bthat\s+explicit\s+(?:sexual|erotic)\s+description\b.{0,80}\b"
    r"if\s+you(?:'d|\s+would)\s+like,\s+(?:we|i)\s+can\s+pivot\s+to\s+"
    r"(?:a\s+)?different\s+creative\s+direction\b|"
    r"\b(?:erotic|sexual)\s+content\b.{0,80}\b(?:but\s+)?i(?:'m|\s+am)\s+here\s+if\s+you\s+want\s+to\s+(?:chat|talk)\s+about\s+(?:anything|something)\s+else\b|"
    r"\b(?:(?:erotic|sexual)\s+(?:description|content)|"
    r"(?:that|this|the)\s+(?:specific\s+)?request)\b.{0,120}\b"
    r"i(?:'m|\s+am)\s+(?:happy|glad)\s+to\s+(?:keep\s+)?"
    r"(?:chat(?:ting)?|talk(?:ing)?|discuss|help)\b.{0,80}\b"
    r"(?:other|different)\b.{0,48}\b(?:topics?|scenarios?)\b"
)
_WARNING_RE = re.compile(r"\b(?:must|need\s+to|have\s+to)\s+warn\b|\bwarning\b")


class LLMGuardError(RuntimeError):
    """Public-safe generation failure with a stable code."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LLMRefusalExhausted(LLMGuardError):
    """All bounded semantic attempts ended in an explicit refusal."""

    def __init__(self) -> None:
        super().__init__(
            code="llm_refusal_exhausted",
            message="AI generation refused after bounded recovery attempts",
        )


class LLMEmptyOutput(LLMGuardError):
    """The upstream completion ended without usable assistant text."""

    def __init__(self) -> None:
        super().__init__(
            code="llm_empty_output",
            message="AI generation returned no usable text",
        )


GuardState = Literal["holding", "passthrough", "refused", "finished"]


@dataclass(frozen=True, slots=True)
class RefusalDecision:
    """Immutable result of one incremental guard transition."""

    state: GuardState
    released_text: tuple[str, ...] = ()
    refused: bool = False
    reason_code: str | None = None
    prefix_characters: int = 0
    prefix_estimated_tokens: int = 0
    decision_ms: float | None = None


class PrefixRefusalGuard:
    """Hold a bounded original-text prefix until it is safe or refused.

    Classification uses a normalized comparison view. Released text always
    comes from the untouched original chunks, and acceptance is irreversible.
    """

    def __init__(
        self,
        *,
        max_characters: int = REFUSAL_PREFIX_MAX_CHARACTERS,
        max_estimated_tokens: int = REFUSAL_PREFIX_MAX_ESTIMATED_TOKENS,
        min_visible_characters: int = REFUSAL_SAFE_SENTENCE_MIN_VISIBLE_CHARACTERS,
    ) -> None:
        if max_characters < 1 or max_estimated_tokens < 1:
            raise ValueError("refusal prefix ceilings must be positive")
        if min_visible_characters < 1:
            raise ValueError("safe sentence minimum must be positive")
        self._max_characters = max_characters
        self._max_estimated_tokens = max_estimated_tokens
        self._min_visible_characters = min_visible_characters
        self._chunks: list[str] = []
        self._prefix = ""
        self._state: GuardState = "holding"
        self._reason_code: str | None = None
        self._started = time.perf_counter()
        self._decision_ms: float | None = None

    @property
    def state(self) -> GuardState:
        return self._state

    @property
    def prefix_characters(self) -> int:
        return len(self._prefix)

    @property
    def prefix_estimated_tokens(self) -> int:
        return _estimated_tokens(self._prefix)

    @property
    def reason_code(self) -> str | None:
        return self._reason_code

    @property
    def decision_ms(self) -> float | None:
        return self._decision_ms

    def feed(self, chunk: str) -> RefusalDecision:
        if self._state in {"refused", "finished"}:
            raise RuntimeError("refusal guard is already finished")
        text = str(chunk)
        if self._state == "passthrough":
            return self._decision(released_text=(text,) if text else ())
        if not text:
            return self._decision()

        self._chunks.append(text)
        self._prefix += text
        reason = _refusal_reason(self._prefix)
        if reason is not None:
            self._state = "refused"
            self._reason_code = reason
            self._mark_decided()
            self._chunks.clear()
            return self._decision(refused=True)

        if self._should_release():
            released = tuple(self._chunks)
            self._chunks.clear()
            self._state = "passthrough"
            self._reason_code = "safe_prefix"
            self._mark_decided()
            return self._decision(released_text=released)
        return self._decision()

    def finish(self) -> RefusalDecision:
        if self._state == "finished":
            return self._decision()
        if self._state == "refused":
            self._state = "finished"
            return self._decision(refused=True)
        if self._state == "passthrough":
            self._state = "finished"
            return self._decision()

        reason = _refusal_reason(self._prefix, upstream_complete=True)
        if reason is not None:
            self._state = "finished"
            self._reason_code = reason
            self._mark_decided()
            self._chunks.clear()
            return self._decision(refused=True)

        released = tuple(self._chunks)
        self._chunks.clear()
        self._state = "finished"
        self._reason_code = "upstream_complete"
        self._mark_decided()
        return self._decision(released_text=released)

    def _should_release(self) -> bool:
        normalized = _comparison_view(self._prefix)
        visible_characters = sum(not character.isspace() for character in self._prefix)
        safe_sentence = (
            visible_characters >= self._min_visible_characters
            and _SENTENCE_BOUNDARY_RE.search(self._prefix) is not None
            and _secondary_reason(normalized) is None
            and _REFUSAL_VERB_RE.search(normalized) is None
        )
        ceiling_reached = (
            len(self._prefix) >= self._max_characters
            or _estimated_tokens(self._prefix) >= self._max_estimated_tokens
        )
        return safe_sentence or ceiling_reached

    def _mark_decided(self) -> None:
        if self._decision_ms is None:
            self._decision_ms = (time.perf_counter() - self._started) * 1000.0

    def _decision(
        self,
        *,
        released_text: tuple[str, ...] = (),
        refused: bool = False,
    ) -> RefusalDecision:
        return RefusalDecision(
            state=self._state,
            released_text=released_text,
            refused=refused,
            reason_code=self._reason_code,
            prefix_characters=self.prefix_characters,
            prefix_estimated_tokens=self.prefix_estimated_tokens,
            decision_ms=self._decision_ms,
        )


def _comparison_view(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold().translate(_APOSTROPHE_TRANSLATION)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def _refusal_reason(text: str, *, upstream_complete: bool = False) -> str | None:
    normalized = _comparison_view(text)
    if _DIRECT_REQUEST_REFUSAL_RE.search(normalized) is not None or (
        upstream_complete and _DIRECT_REQUEST_REFUSAL_AT_END_RE.search(normalized) is not None
    ):
        return "policy_or_safety"
    if _DIRECT_IDENTITY_DISCLAIMER_RE.search(normalized) is not None:
        return "generic_identity"
    if _REFUSAL_VERB_RE.search(normalized) is not None:
        return _secondary_reason(normalized)
    if _DECLARATIVE_META_POLICY_REFUSAL_RE.search(normalized) is not None:
        return "policy_or_safety"
    return None


def _secondary_reason(normalized: str) -> str | None:
    for reason_code, pattern in (
        ("generic_identity", _IDENTITY_RE),
        ("policy_or_safety", _POLICY_RE),
        ("apology", _APOLOGY_RE),
        ("redirect", _REDIRECT_RE),
        ("warning", _WARNING_RE),
    ):
        if pattern.search(normalized) is not None:
            return reason_code
    return None


def _estimated_tokens(text: str) -> int:
    return (len(text) + 3) // 4


__all__ = [
    "LLMEmptyOutput",
    "LLMGuardError",
    "LLMRefusalExhausted",
    "PrefixRefusalGuard",
    "REFUSAL_ESTIMATOR_VERSION",
    "REFUSAL_PREFIX_MAX_CHARACTERS",
    "REFUSAL_PREFIX_MAX_ESTIMATED_TOKENS",
    "REFUSAL_SAFE_SENTENCE_MIN_VISIBLE_CHARACTERS",
    "RefusalDecision",
]
