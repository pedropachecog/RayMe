from __future__ import annotations

import re

HALLUCINATION_BLOCKLIST = (
    "thank you for watching",
    "thanks for watching",
    "subscribe to my channel",
)


def normalize_transcript_text(text: str) -> str:
    lowered = text.strip().lower()
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def is_blocklisted_transcript(text: str) -> bool:
    return normalize_transcript_text(text) in HALLUCINATION_BLOCKLIST
