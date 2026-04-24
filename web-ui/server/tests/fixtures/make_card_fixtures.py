"""Generate and verify deterministic SillyTavern card fixtures."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin

FIXTURE_DIR = Path(__file__).resolve().parent
CARDS_DIR = FIXTURE_DIR / "cards"

MALICIOUS_HTML = "<img src=x onerror=alert(1)>"
MALICIOUS_JS_URL = "javascript:alert(1)"


def _lorebook(label: str) -> dict[str, Any]:
    return {
        "name": f"{label} Lorebook",
        "description": "Preserved by import, not injected into v1 prompts.",
        "entries": [
            {
                "id": 1,
                "keys": ["clocktower", "blue lantern"],
                "content": f"{label} hidden lore that must stay out of prompt context.",
                "enabled": True,
                "position": "before_char",
            }
        ],
    }


def _card(
    *,
    spec: str,
    spec_version: str,
    name: str,
    description: str,
    version: str,
    greeting_prefix: str,
) -> dict[str, Any]:
    label = name.replace("RayMe Fixture ", "")
    return {
        "spec": spec,
        "spec_version": spec_version,
        "data": {
            "name": name,
            "description": description,
            "personality": f"{label} is observant, warm, and precise.",
            "scenario": f"{label} is helping test RayMe character import behavior.",
            "first_mes": f"{greeting_prefix} Primary opening message.",
            "mes_example": (
                "<START>\n"
                f"{{{{user}}}}: What should this fixture prove?\n"
                f"{{{{char}}}}: It proves deterministic {label} card parsing."
            ),
            "creator_notes": f"{label} creator notes are preserved as untrusted data.",
            "character_version": version,
            "alternate_greetings": [
                f"{greeting_prefix} Alternate greeting one.",
                f"{greeting_prefix} Alternate greeting two.",
            ],
            "character_book": _lorebook(label),
            "extensions": {
                "world_info": {
                    "format": "sillytavern-compatible",
                    "entries": _lorebook(f"{label} World Info")["entries"],
                },
                "rayme_fixture": True,
            },
        },
    }


def v2_card(name: str = "RayMe Fixture V2") -> dict[str, Any]:
    return _card(
        spec="chara_card_v2",
        spec_version="2.0",
        name=name,
        description=(
            "Deterministic v2 JSON card with alternate greetings and preserved lorebook data."
        ),
        version="2.0-fixture",
        greeting_prefix="V2",
    )


def v3_card(name: str = "RayMe Fixture V3") -> dict[str, Any]:
    card = _card(
        spec="chara_card_v3",
        spec_version="3.0",
        name=name,
        description=(
            "Deterministic v3 JSON card with alternate greetings and preserved lorebook data."
        ),
        version="3.0-fixture",
        greeting_prefix="V3",
    )
    card["data"].update(
        {
            "system_prompt": "Stay in character and keep responses concise.",
            "character_notes": "V3-only character notes stay preserved as data.",
            "tags": ["fixture", "v3", "lorebook"],
            "post_history_instructions": "Do not include preserved lorebook fields automatically.",
            "creator": "RayMe test suite",
        }
    )
    return card


def malicious_card() -> dict[str, Any]:
    card = v3_card("RayMe Malicious Fixture")
    card["data"].update(
        {
            "description": f"{MALICIOUS_HTML} should stay inert data, not rendered HTML.",
            "first_mes": f"Unsafe links such as {MALICIOUS_JS_URL} must be sanitized later.",
            "creator_notes": (
                f"Contains literal {MALICIOUS_HTML} and {MALICIOUS_JS_URL} payloads."
            ),
        }
    )
    return card


def png_fixture_payloads() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "v2_card.png": {"chara": v2_card("RayMe PNG V2")},
        "v3_card.png": {"ccv3": v3_card("RayMe PNG V3")},
        "dual_chunk_prefers_ccv3.png": {
            "chara": v2_card("RayMe Dual Chara Fallback"),
            "ccv3": v3_card("RayMe Dual Preferred CCV3"),
        },
    }


def json_fixture_payloads() -> dict[str, dict[str, Any]]:
    return {
        "v2_card.json": v2_card(),
        "v3_card.json": v3_card(),
        "malicious_card.json": malicious_card(),
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _metadata_value(payload: dict[str, Any]) -> str:
    return base64.b64encode(_json_text(payload).encode("utf-8")).decode("ascii")


def _write_png(path: Path, chunks: dict[str, dict[str, Any]]) -> None:
    metadata = PngImagePlugin.PngInfo()
    for key, payload in chunks.items():
        metadata.add_text(key, _metadata_value(payload))

    image = Image.new("RGBA", (1, 1), (58, 42, 94, 255))
    image.save(path, format="PNG", pnginfo=metadata)


def generate() -> None:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    for filename, payload in json_fixture_payloads().items():
        (CARDS_DIR / filename).write_text(_json_text(payload), encoding="utf-8")

    for filename, chunks in png_fixture_payloads().items():
        _write_png(CARDS_DIR / filename, chunks)

    print(f"Generated {len(expected_files())} card fixtures in {CARDS_DIR}.")


def expected_files() -> tuple[Path, ...]:
    names = tuple(json_fixture_payloads()) + tuple(png_fixture_payloads())
    return tuple(CARDS_DIR / name for name in names)


def _decode_metadata_value(value: str) -> dict[str, Any]:
    decoded = base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise ValueError("PNG card metadata did not decode to a JSON object")
    return parsed


def _verify_json_fixture(filename: str, expected: dict[str, Any]) -> list[str]:
    path = CARDS_DIR / filename
    errors: list[str] = []
    if not path.exists():
        return [f"Missing {path}"]

    actual_text = path.read_text(encoding="utf-8")
    if actual_text != _json_text(expected):
        errors.append(f"{path} does not match deterministic fixture payload")

    actual = json.loads(actual_text)
    data = actual.get("data", {})
    for field in (
        "name",
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "creator_notes",
        "character_version",
        "alternate_greetings",
        "character_book",
        "extensions",
    ):
        if field not in data:
            errors.append(f"{path} is missing data.{field}")

    if filename == "malicious_card.json":
        if MALICIOUS_HTML not in actual_text:
            errors.append(f"{path} is missing literal {MALICIOUS_HTML}")
        if MALICIOUS_JS_URL not in actual_text:
            errors.append(f"{path} is missing literal {MALICIOUS_JS_URL}")

    return errors


def _verify_png_fixture(filename: str, expected_chunks: dict[str, dict[str, Any]]) -> list[str]:
    path = CARDS_DIR / filename
    errors: list[str] = []
    if not path.exists():
        return [f"Missing {path}"]

    with Image.open(path) as image:
        if image.size != (1, 1):
            errors.append(f"{path} is {image.size}, expected a 1x1 PNG")
        if image.mode != "RGBA":
            errors.append(f"{path} is {image.mode}, expected RGBA")
        text_chunks = dict(image.text)

    for key, expected_payload in expected_chunks.items():
        if key not in text_chunks:
            errors.append(f"{path} is missing {key} tEXt chunk")
            continue
        actual_payload = _decode_metadata_value(text_chunks[key])
        if actual_payload != expected_payload:
            errors.append(f"{path} {key} tEXt chunk does not match expected payload")

    unexpected_keys = set(text_chunks) - set(expected_chunks)
    if unexpected_keys:
        errors.append(f"{path} has unexpected text chunks: {sorted(unexpected_keys)}")

    if filename == "dual_chunk_prefers_ccv3.png":
        chara = _decode_metadata_value(text_chunks["chara"])
        ccv3 = _decode_metadata_value(text_chunks["ccv3"])
        chara_name = chara["data"]["name"]
        ccv3_name = ccv3["data"]["name"]
        if chara_name == ccv3_name:
            errors.append(f"{path} dual chunks must have different name values")
        if ccv3_name != "RayMe Dual Preferred CCV3":
            errors.append(f"{path} ccv3 chunk does not contain preferred fixture name")

    return errors


def verify() -> None:
    errors: list[str] = []
    for filename, expected in json_fixture_payloads().items():
        errors.extend(_verify_json_fixture(filename, expected))
    for filename, expected_chunks in png_fixture_payloads().items():
        errors.extend(_verify_png_fixture(filename, expected_chunks))

    if errors:
        raise SystemExit("Fixture verification failed:\n- " + "\n- ".join(errors))

    print(f"Verified {len(expected_files())} card fixtures.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify fixtures without modifying them",
    )
    args = parser.parse_args()

    if args.verify:
        verify()
    else:
        generate()


if __name__ == "__main__":
    main()
