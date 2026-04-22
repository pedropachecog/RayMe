"""HTTPS probe server for Phase 0 success criterion #1."""

from __future__ import annotations

import argparse
import http.server
import ssl
import sys

PROBE_HTML = b"""<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RayMe HTTPS probe</title>
<style>
body{font-family:system-ui;padding:2em}
.ok{color:green}
.no{color:red}
h1{font-size:1.2em}
li{margin:.3em 0}
</style>
<h1>RayMe Phase 0 - HTTPS probe</h1>
<p>All rows must be green for Phase 3 voice capture to work on this device.</p>
<ul id="out"></ul>
<script>
  const out = document.getElementById("out");
  const row = (key, value, ok) => {
    const li = document.createElement("li");
    li.className = ok ? "ok" : "no";
    li.textContent = key + ": " + value;
    out.appendChild(li);
  };
  row("window.isSecureContext", window.isSecureContext, window.isSecureContext === true);
  row("navigator.mediaDevices defined", !!navigator.mediaDevices, !!navigator.mediaDevices);
  row("location.protocol", location.protocol, location.protocol === "https:");
  row("location.href", location.href, true);
  row("userAgent", navigator.userAgent, true);
</script>
"""


class ProbeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PROBE_HTML)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PROBE_HTML)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(f"[probe] {self.address_string()} - {fmt % args}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        required=True,
        help="Expected hostname used by the browser (for display only).",
    )
    parser.add_argument("--cert", required=True, help="Path to cert file (.crt or .pem)")
    parser.add_argument("--key", required=True, help="Path to key file (.key or -key.pem)")
    parser.add_argument(
        "--bind",
        default="192.168.1.199",
        help="IP to bind. Use the LAN IP or a future Tailscale IP, never 0.0.0.0.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8443,
        help="HTTPS port. Use 443 only from an elevated shell on Windows.",
    )
    args = parser.parse_args()

    if args.bind == "0.0.0.0":
        parser.error("Do not bind 0.0.0.0 for this probe; use the LAN or Tailscale IP only.")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.cert, keyfile=args.key)

    server = http.server.HTTPServer((args.bind, args.port), ProbeHandler)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    url = f"https://{args.host}"
    if args.port != 443:
        url = f"{url}:{args.port}"

    print(f"[probe] Serving at {url} (bound to {args.bind}:{args.port})", flush=True)
    print(f"[probe] Load this URL on iPhone Safari: {url}", flush=True)
    print("[probe] Press Ctrl+C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[probe] Shutting down.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
