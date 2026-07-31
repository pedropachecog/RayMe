#!/usr/bin/env python3
"""Phase 09 real OMEN Qwen live-call hardware tracer."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

AUTHORIZED_SCOPE = "rayme_lan_call_testing"


@dataclass(frozen=True)
class ReferenceSelection:
    reference_path: Path
    transcript_path: Path
    steward_id: str
    authorization_basis: str
    use_scope: str
    reference_sha256: str
    transcript_sha256: str
    source: str


def _resolve_authorized_reference(
    *,
    reference_path: Path | None,
    transcript_path: Path | None,
    sidecar_path: Path | None,
    fallback_factory: Callable[[], ReferenceSelection],
) -> ReferenceSelection:
    raise NotImplementedError("authorization resolver is not implemented")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_candidate(root: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    reference = root / "reference.wav"
    transcript = root / "reference.txt"
    sidecar = root / "reference.authorization.json"
    reference.write_bytes(b"RIFF-authorized-reference")
    transcript.write_text("Matching authorized transcript.\n", encoding="utf-8")
    metadata = {
        "voice_data_steward": "steward-test-opaque",
        "authorization_basis": "speaker-provided test fixture",
        "use_scope": AUTHORIZED_SCOPE,
        "reference_sha256": _sha256(reference),
        "transcript_sha256": _sha256(transcript),
    }
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    return reference, transcript, sidecar, metadata


def _self_test_reference_authorization() -> None:
    with tempfile.TemporaryDirectory(prefix="rayme-qwen-auth-") as raw_root:
        root = Path(raw_root)
        fallback_calls: list[int] = []

        def fallback() -> ReferenceSelection:
            fallback_calls.append(1)
            fallback_reference = root / "synthetic.wav"
            fallback_transcript = root / "synthetic.txt"
            fallback_reference.write_bytes(b"RIFF-generated-non-person")
            fallback_transcript.write_text(
                "Generated deterministic non person fixture.\n",
                encoding="utf-8",
            )
            return ReferenceSelection(
                reference_path=fallback_reference,
                transcript_path=fallback_transcript,
                steward_id="generated_non_person_fixture",
                authorization_basis="generated_non_person_fixture",
                use_scope=AUTHORIZED_SCOPE,
                reference_sha256=_sha256(fallback_reference),
                transcript_sha256=_sha256(fallback_transcript),
                source="generated_non_person_fixture",
            )

        reference, transcript, sidecar, metadata = _write_candidate(root)
        selected = _resolve_authorized_reference(
            reference_path=reference,
            transcript_path=transcript,
            sidecar_path=sidecar,
            fallback_factory=fallback,
        )
        assert selected.source == "authorized_phase005_reference"
        assert selected.reference_sha256 == metadata["reference_sha256"]
        assert selected.transcript_sha256 == metadata["transcript_sha256"]
        assert fallback_calls == []

        invalid_cases: list[tuple[str, Callable[[Path, dict[str, str]], None]]] = [
            ("missing", lambda path, _metadata: path.unlink()),
            ("malformed", lambda path, _metadata: path.write_text("{", encoding="utf-8")),
            (
                "wrong-reference-hash",
                lambda path, value: path.write_text(
                    json.dumps({**value, "reference_sha256": "0" * 64}),
                    encoding="utf-8",
                ),
            ),
            (
                "wrong-transcript-hash",
                lambda path, value: path.write_text(
                    json.dumps({**value, "transcript_sha256": "f" * 64}),
                    encoding="utf-8",
                ),
            ),
            (
                "wrong-scope",
                lambda path, value: path.write_text(
                    json.dumps({**value, "use_scope": "not-authorized"}),
                    encoding="utf-8",
                ),
            ),
        ]
        for label, mutate in invalid_cases:
            case_root = root / label
            case_root.mkdir()
            case_reference, case_transcript, case_sidecar, case_metadata = _write_candidate(case_root)
            mutate(case_sidecar, case_metadata)
            fallback_before = len(fallback_calls)
            selected = _resolve_authorized_reference(
                reference_path=case_reference,
                transcript_path=case_transcript,
                sidecar_path=case_sidecar,
                fallback_factory=fallback,
            )
            assert selected.source == "generated_non_person_fixture", label
            assert len(fallback_calls) == fallback_before + 1, label

    print("reference authorization self-test passed")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test-reference-authorization", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.self_test_reference_authorization:
        _self_test_reference_authorization()
        return 0
    raise SystemExit("a tracer operation is required")


if __name__ == "__main__":
    raise SystemExit(main())
