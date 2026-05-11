#!/usr/bin/env python3
"""Contract tests for the Phase 8 live call-flow evidence runner."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PHASE_DIR = Path(__file__).resolve().parents[1]
RUNNER_PATH = PHASE_DIR / "08-run-call-flow-evidence.py"


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("phase08_call_flow_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakePeerConnection:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class Phase8CallFlowRunnerTests(unittest.TestCase):
    def test_runner_collects_warm_samples_from_immediate_and_final_metric_carriers(self) -> None:
        module = load_runner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            reference_audio = Path(tmp_dir) / "reference.wav"
            reference_audio.write_bytes(b"RIFFfake-wave")
            output_path = Path(tmp_dir) / "call-flow.json"
            speak_calls: list[dict[str, Any]] = []

            class FakeApi:
                def __init__(self, *, web_base_url: str, ai_base_url: str, timeout: float) -> None:
                    self.web_base_url = web_base_url
                    self.ai_base_url = ai_base_url
                    self.timeout = timeout
                    self.measured_indexes = {"f5": 0, "voxcpm2": 0}

                def post_json(
                    self,
                    base_url: str,
                    path: str,
                    payload: dict[str, Any],
                ) -> Any:
                    if path == "/webrtc/offer":
                        return module.ApiResponse(status=200, payload={"answer": "ok"})
                    if not path.endswith("/speak"):
                        raise AssertionError(f"unexpected path: {path}")
                    engine = str(payload["engine_id"])
                    speak_calls.append({"engine": engine, "payload": payload})
                    call_number = sum(1 for call in speak_calls if call["engine"] == engine)
                    is_warmup = call_number == 1
                    if is_warmup:
                        ttfa = 1800.0 if engine == "f5" else 650.0
                    else:
                        self.measured_indexes[engine] += 1
                        ttfa_values = {
                            "f5": [1110.0, 1120.0, 1130.0],
                            "voxcpm2": [410.0, 420.0, 430.0],
                        }
                        ttfa = ttfa_values[engine][self.measured_indexes[engine] - 1]
                    immediate_metrics = {
                        "streaming_used": engine == "voxcpm2",
                        "fallback_used": False,
                        "whole_wav_fallback_used": False,
                        "chunk_count_at_start": 1,
                        "first_chunk_generated_ms": ttfa - 40.0,
                        "first_chunk_enqueued_ms": ttfa - 15.0,
                        "ai_audio_started_ms": ttfa,
                        "inter_chunk_gaps_ms": [22.0, 31.0] if engine == "voxcpm2" else [],
                    }
                    final_metrics = {
                        "streaming_used": engine == "voxcpm2",
                        "fallback_used": False,
                        "whole_wav_fallback_used": False,
                        "chunk_count": 3 if engine == "voxcpm2" else 1,
                        "total_generation_ms": ttfa + 900.0,
                        "total_playback_ms": ttfa + 700.0,
                        "inter_chunk_gaps_ms": [22.0, 31.0] if engine == "voxcpm2" else [],
                    }
                    return module.ApiResponse(
                        status=200,
                        payload={
                            "state": "listening",
                            "event": {
                                "ai_audio_started_event": {
                                    "audio": True,
                                    "tts_playback": immediate_metrics,
                                },
                                "tts_playback_final": final_metrics,
                            },
                        },
                    )

            async def fake_create_audio_offer() -> tuple[_FakePeerConnection, dict[str, str]]:
                return _FakePeerConnection(), {"sdp": "fake", "type": "offer"}

            original_api = module.RayMeApi
            original_offer = module._create_audio_offer
            module.RayMeApi = FakeApi
            module._create_audio_offer = fake_create_audio_offer
            try:
                args = SimpleNamespace(
                    warm_samples=3,
                    web_base_url="https://web.example",
                    ai_base_url="https://ai.example",
                    reference_audio=str(reference_audio),
                    reference_transcript="reference transcript",
                    call_text="Phase 8 streaming call-flow evidence.",
                    output=str(output_path),
                    timeout=30.0,
                )
                payload = asyncio.run(module.generate_evidence(args))
                module.write_evidence(payload, output_path)
            finally:
                module.RayMeApi = original_api
                module._create_audio_offer = original_offer

            self.assertTrue(output_path.is_file())
            self.assertEqual(
                [sample["engine"] for sample in payload["samples"]],
                ["f5", "f5", "f5", "voxcpm2", "voxcpm2", "voxcpm2"],
            )
            self.assertEqual([call["engine"] for call in speak_calls], ["f5"] * 4 + ["voxcpm2"] * 4)
            first_voxcpm2 = next(sample for sample in payload["samples"] if sample["engine"] == "voxcpm2")
            self.assertEqual(
                first_voxcpm2["warm_call_ttfa_ms"],
                first_voxcpm2["ai_audio_started_event"]["tts_playback"]["ai_audio_started_ms"],
            )
            self.assertIn("chunk_count", first_voxcpm2["tts_playback_final"])
            self.assertNotIn("total_generation_ms", first_voxcpm2["ai_audio_started_event"]["tts_playback"])
            self.assertEqual(payload["summary"]["warm_sample_count"], 3)
            self.assertEqual(payload["summary"]["f5_warm_call_ttfa_ms"], 1120.0)
            self.assertEqual(payload["summary"]["voxcpm2_warm_call_ttfa_ms"], 420.0)
            self.assertIs(payload["summary"]["voxcpm2_beats_f5"], True)
            self.assertEqual(payload["runtime"]["reference_audio_source"], "reference.wav")
            self.assertNotIn(str(reference_audio.parent), payload["runtime"]["reference_audio_source"])


if __name__ == "__main__":
    unittest.main()
