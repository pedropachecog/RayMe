"""Deterministic incremental text segmentation for live-call speech."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\S+")
_HARD_BOUNDARY_RE = re.compile(r"(?:[.!?]+[\"')\]]*|\n+)(?=\s|$)")
_SOFT_BOUNDARY_RE = re.compile(r"(?:[,;:]|[—–])(?=\s|$)")


class CallTtsSegmenter:
    """Split an arriving LLM stream into bounded natural speech phrases.

    Hard sentence/newline boundaries are emitted as soon as they are useful.
    Very short fragments stay attached to the next phrase. If the model does
    not provide a sentence ending, the latest safe phrase boundary before the
    word ceiling is preferred, then the ceiling itself is used as a hard bound.
    """

    def __init__(self, *, max_words: int = 60, min_words: int = 4) -> None:
        if max_words < 1:
            raise ValueError("max_words must be positive")
        if min_words < 1 or min_words > max_words:
            raise ValueError("min_words must be between one and max_words")
        self._max_words = max_words
        self._min_words = min_words
        self._buffer = ""
        self._finished = False

    def feed(self, token: str) -> list[str]:
        if self._finished:
            raise RuntimeError("call TTS segmenter is already finished")
        if token:
            self._buffer += token

        emitted: list[str] = []
        while True:
            boundary = self._next_boundary()
            if boundary is None:
                break
            segment = self._buffer[:boundary].strip()
            self._buffer = self._buffer[boundary:].lstrip()
            if segment:
                emitted.append(segment)
        return emitted

    def finish(self) -> str | None:
        if self._finished:
            return None
        self._finished = True
        tail = self._buffer.strip()
        self._buffer = ""
        return tail or None

    def _next_boundary(self) -> int | None:
        words = list(_WORD_RE.finditer(self._buffer))
        if not words:
            if self._buffer and not self._buffer.strip():
                self._buffer = ""
            return None

        for match in _HARD_BOUNDARY_RE.finditer(self._buffer):
            word_count = _word_count(self._buffer[: match.end()])
            if word_count < self._min_words:
                continue
            if word_count <= self._max_words:
                return match.end()
            break

        if len(words) < self._max_words:
            return None

        word_limit = words[self._max_words - 1].end()
        soft_boundaries = [
            match.end()
            for match in _SOFT_BOUNDARY_RE.finditer(self._buffer, 0, word_limit + 1)
            if _word_count(self._buffer[: match.end()]) >= self._min_words
        ]
        if soft_boundaries:
            return soft_boundaries[-1]
        return word_limit


def _word_count(text: str) -> int:
    return sum(1 for _ in _WORD_RE.finditer(text))


__all__ = ["CallTtsSegmenter"]
