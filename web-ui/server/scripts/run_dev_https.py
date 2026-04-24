from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings, get_settings  # noqa: E402

BROWSER_URL_EXAMPLE = "https://192.168.1.199:8443"


def build_parser(settings: Settings | None = None) -> argparse.ArgumentParser:
    runtime_settings = settings or get_settings()
    parser = argparse.ArgumentParser(
        description=(
            "Run the RayMe Web UI FastAPI/static host over HTTPS for LAN development."
        ),
        epilog=(
            "mkcert direct-IP example:\n"
            "  RAYME_WEB_BIND_HOST=192.168.1.199\n"
            "  RAYME_WEB_PORT=8443\n"
            "  RAYME_TLS_CERT=.certs/rayme.local+1.pem\n"
            "  RAYME_TLS_KEY=.certs/rayme.local+1-key.pem\n"
            f"  Browser URL: {BROWSER_URL_EXAMPLE}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=runtime_settings.web_bind_host,
        help="Explicit loopback or LAN IP to bind; 0.0.0.0 is rejected.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=runtime_settings.web_port,
        help="HTTPS port to serve; default comes from RAYME_WEB_PORT.",
    )
    parser.add_argument(
        "--cert",
        default=str(runtime_settings.tls_cert) if runtime_settings.tls_cert else None,
        help="Path to the mkcert TLS certificate file, or RAYME_TLS_CERT.",
    )
    parser.add_argument(
        "--key",
        default=str(runtime_settings.tls_key) if runtime_settings.tls_key else None,
        help="Path to the mkcert TLS private key file, or RAYME_TLS_KEY.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate bind and TLS settings, then exit without starting the server.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[Path, Path]:
    if args.host.strip() == "0.0.0.0":
        parser.error("0.0.0.0 is not allowed; use an explicit loopback or LAN IP.")
    if args.port <= 0 or args.port > 65535:
        parser.error("--port must be between 1 and 65535.")
    if not args.cert:
        parser.error("--cert or RAYME_TLS_CERT is required for HTTPS.")
    if not args.key:
        parser.error("--key or RAYME_TLS_KEY is required for HTTPS.")

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
        print(f"OK: https://{args.host}:{args.port} (direct-IP example: {BROWSER_URL_EXAMPLE})")
        return 0

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
