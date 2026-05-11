#!/usr/bin/env python3
"""Contract tests for the Phase 8 evidence verifier."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


PHASE_DIR = Path(__file__).resolve().parents[1]
VERIFIER_PATH = PHASE_DIR / "08-verify-evidence.py"


def load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("phase08_verify_evidence", VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Phase8EvidenceVerifierTests(unittest.TestCase):
    def test_synthetic_contract_payload_passes_call_flow_verification(self) -> None:
        module = load_verifier()
        module._verify_call_flow(module._synthetic_contract_payload())

    def test_rejects_attempt_to_satisfy_final_metrics_from_immediate_carrier(self) -> None:
        module = load_verifier()
        payload = copy.deepcopy(module._synthetic_contract_payload())
        voxcpm2_sample = next(sample for sample in payload["samples"] if sample["engine"] == "voxcpm2")
        immediate = voxcpm2_sample["ai_audio_started_event"]["tts_playback"]
        immediate.update(
            {
                "chunk_count": 3,
                "total_generation_ms": 1800.0,
                "total_playback_ms": 1700.0,
            }
        )
        voxcpm2_sample["tts_playback_final"] = {
            "streaming_used": True,
            "fallback_used": False,
            "whole_wav_fallback_used": False,
            "inter_chunk_gaps_ms": [22.0, 31.0],
        }

        with self.assertRaises(module.EvidenceError) as raised:
            module._verify_call_flow(payload)

        self.assertIn("tts_playback_final", str(raised.exception))

    def test_rejects_whole_wav_fallback_and_failing_median_comparison(self) -> None:
        module = load_verifier()
        fallback_payload = copy.deepcopy(module._synthetic_contract_payload())
        first_voxcpm2 = next(sample for sample in fallback_payload["samples"] if sample["engine"] == "voxcpm2")
        first_voxcpm2["tts_playback_final"]["whole_wav_fallback_used"] = True
        with self.assertRaises(module.EvidenceError) as fallback_error:
            module._verify_call_flow(fallback_payload)
        self.assertIn("whole_wav_fallback_used", str(fallback_error.exception))

        median_payload = copy.deepcopy(module._synthetic_contract_payload())
        median_payload["summary"]["voxcpm2_warm_call_ttfa_ms"] = 1200.0
        median_payload["summary"]["f5_warm_call_ttfa_ms"] = 1000.0
        median_payload["summary"]["voxcpm2_beats_f5"] = False
        for sample in median_payload["samples"]:
            if sample["engine"] == "voxcpm2":
                sample["warm_call_ttfa_ms"] = 1200.0
                sample["ai_audio_started_event"]["tts_playback"]["ai_audio_started_ms"] = 1200.0
            elif sample["engine"] == "f5":
                sample["warm_call_ttfa_ms"] = 1000.0
                sample["ai_audio_started_event"]["tts_playback"]["ai_audio_started_ms"] = 1000.0

        with self.assertRaises(module.EvidenceError) as median_error:
            module._verify_call_flow(median_payload)
        self.assertIn("VoxCPM2 median", str(median_error.exception))


if __name__ == "__main__":
    unittest.main()
