from __future__ import annotations

import re
from pathlib import Path


PRODUCTION_ROOTS = (
    "ai-backend/app",
    "web-ui/server/app",
    "web-ui/client/src",
    "scripts",
)
SYNTHETIC_SUCCESS_WORD = "fa" + "ke"
BANNED_PATTERN = re.compile(
    rf"\b({SYNTHETIC_SUCCESS_WORD}|mock|stub)\b|"
    rf"(?:^|_){SYNTHETIC_SUCCESS_WORD}_|_{SYNTHETIC_SUCCESS_WORD}(?:$|_)",
    re.IGNORECASE,
)
ALLOWLIST = {
    Path("web-ui/client/src/lib/components/call/VoiceVisualizer.svelte"): {
        "waveform-fallback",
    },
}


def test_production_code_has_no_scripted_mock_or_stub_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for relative_root in PRODUCTION_ROOTS:
        root = repo_root / relative_root
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".svelte", ".sh"}:
                continue
            relative_path = path.relative_to(repo_root)
            allowed_fragments = ALLOWLIST.get(relative_path, set())
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if any(fragment in line for fragment in allowed_fragments):
                    continue
                if BANNED_PATTERN.search(line):
                    violations.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert violations == []
