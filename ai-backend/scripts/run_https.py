from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import uvicorn
from uvicorn.config import LOGGING_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HEALTH_URL_EXAMPLE = "https://192.168.1.199:9443/health"


def build_log_config() -> dict[str, Any]:
    """Return uvicorn's default log config with `app.*` loggers wired to stderr.

    Uvicorn's default LOGGING_CONFIG only attaches handlers to `uvicorn.*`
    loggers. Module loggers like `app.api.webrtc` therefore have no handler
    and propagate to a handlerless root logger, which silently discards their
    records. Without this override, `[rayme-call]` post-offer instrumentation
    is invisible in the OMEN log files.
    """
    config = copy.deepcopy(LOGGING_CONFIG)
    loggers = config.setdefault("loggers", {})
    loggers["app"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    loggers["aiortc"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the RayMe AI backend HTTPS health service. "
            f"Example check: {HEALTH_URL_EXAMPLE}"
        )
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Explicit interface or LAN IP to bind; 0.0.0.0 is rejected.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9443,
        help="HTTPS port to serve; default: 9443.",
    )
    parser.add_argument("--cert", required=True, help="Path to the TLS certificate file.")
    parser.add_argument("--key", required=True, help="Path to the TLS private key file.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate bind and TLS arguments, then exit without starting the server.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[Path, Path]:
    if args.host.strip() == "0.0.0.0":
        parser.error("0.0.0.0 is not allowed; use an explicit loopback or LAN IP.")
    if args.port <= 0 or args.port > 65535:
        parser.error("--port must be between 1 and 65535.")

    cert_path = Path(args.cert)
    key_path = Path(args.key)
    if not cert_path.is_file():
        parser.error(f"--cert file does not exist: {cert_path}")
    if not key_path.is_file():
        parser.error(f"--key file does not exist: {key_path}")

    return cert_path, key_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cert_path, key_path = validate_args(parser, args)

    if args.check_config:
        print(f"OK: {args.host}:{args.port} -> {HEALTH_URL_EXAMPLE}")
        return 0

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_config=build_log_config(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
