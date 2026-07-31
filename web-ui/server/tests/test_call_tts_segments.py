"""Contracts for incremental live-call text segmentation."""

from __future__ import annotations

import pytest

from app.domain.call_tts_segments import CallTtsSegmenter


@pytest.mark.parametrize(
    ("tokens", "emitted", "tail"),
    [
        (
            ["This is a complete sentence."],
            ["This is a complete sentence."],
            None,
        ),
        (
            ["Hi.", " This is a longer natural sentence?"],
            ["Hi. This is a longer natural sentence?"],
            None,
        ),
        (
            ["This is one safe line\n", "and this is the final tail"],
            ["This is one safe line"],
            "and this is the final tail",
        ),
        (
            ["Wait", "! This boundary keeps punctuation."],
            ["Wait! This boundary keeps punctuation."],
            None,
        ),
        (["  ", "\n"], [], None),
    ],
)
def test_segmenter_prefers_natural_boundaries_and_flushes_one_tail(
    tokens: list[str],
    emitted: list[str],
    tail: str | None,
) -> None:
    segmenter = CallTtsSegmenter()

    actual = [segment for token in tokens for segment in segmenter.feed(token)]

    assert actual == emitted
    assert segmenter.finish() == tail
    assert segmenter.finish() is None


def test_segmenter_forces_a_bounded_phrase_no_later_than_sixty_words() -> None:
    segmenter = CallTtsSegmenter()
    text = " ".join(f"word{index}" for index in range(1, 66))

    emitted = segmenter.feed(text)
    tail = segmenter.finish()

    assert len(emitted) == 1
    assert len(emitted[0].split()) <= 60
    assert emitted[0].startswith("word1 ")
    assert tail == "word61 word62 word63 word64 word65"


def test_segmenter_uses_a_late_phrase_boundary_before_the_word_ceiling() -> None:
    segmenter = CallTtsSegmenter()
    prefix = " ".join(f"word{index}" for index in range(1, 56))

    emitted = segmenter.feed(f"{prefix}, and five more words follow now")

    assert emitted == [f"{prefix},"]
    assert segmenter.finish() == "and five more words follow now"
