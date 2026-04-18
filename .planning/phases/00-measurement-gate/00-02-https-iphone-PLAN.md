---
phase: 00-measurement-gate
plan: 02
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/https_serve.py
  - .planning/phases/00-measurement-gate/HTTPS-SETUP.md
  - .planning/phases/00-measurement-gate/results/https_iphone.json
autonomous: false
requirements: []
user_setup:
  - service: tailscale
    why: "Issue a real Let's Encrypt cert for pedro-2023.tailc48d1c.ts.net (zero-install trust on iPhone if iPhone is also on the tailnet)."
    env_vars: []
    dashboard_config:
      - task: "Enroll iPhone on the tailnet OR proceed to mkcert fallback"
        location: "Tailscale admin (https://login.tailscale.com/admin/machines) — confirm iPhone appears as a device"
  - service: mkcert
    why: "HTTPS fallback when iPhone is NOT on the Tailscale tailnet — installs a local CA trusted on the iPhone via Configuration Profile."
    env_vars: []
    dashboard_config:
      - task: "Install the generated rootCA-iphone.mobileconfig to iPhone via AirDrop or email; enable full trust in Settings → General → About → Certificate Trust Settings"
        location: "iPhone Settings app"

must_haves:
  truths:
    - "The builder's iPhone Safari loads a local HTTPS URL with NO cert warning"
    - "`window.isSecureContext` returns `true` from Safari JS console at that URL"
    - "`navigator.mediaDevices` is defined (not undefined) in the same Safari tab"
    - "HTTPS-SETUP.md documents the exact reproducible steps that worked, plus the untaken-path fallback"
    - "Private key material (Tailscale cert key, mkcert CA key) is NOT committed to git"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/https_serve.py"
      provides: "Minimal Python HTTPS server that serves an isSecureContext + mediaDevices probe page"
      contains: "window.isSecureContext"
    - path: ".planning/phases/00-measurement-gate/HTTPS-SETUP.md"
      provides: "Reproducible builder-facing doc — which path worked, exact commands, iPhone steps"
      contains: "# HTTPS on iPhone — Setup Procedure"
    - path: ".planning/phases/00-measurement-gate/results/https_iphone.json"
      provides: "Machine-readable outcome: chosen strategy, cert path, iPhone verification result"
      contains: "strategy"
  key_links:
    - from: ".planning/phases/00-measurement-gate/probes/https_serve.py"
      to: "cert file + key file (Tailscale OR mkcert)"
      via: "ssl.SSLContext.load_cert_chain"
      pattern: "load_cert_chain"
    - from: ".planning/phases/00-measurement-gate/HTTPS-SETUP.md"
      to: "probes/https_serve.py"
      via: "documented invocation"
      pattern: "python .*https_serve.py"
---

<objective>
Empirically verify that the builder can load an HTTPS URL on their iPhone Safari with NO cert warning and `window.isSecureContext === true`, and document the reproducible procedure so Phase 1 can ship this as the LAN HTTPS workflow.

Purpose: This is Phase 0 success criterion #1. Mobile Safari gates `getUserMedia` behind secure contexts; without a trusted cert on the iPhone, Phase 3's first voice call cannot happen. Research discovered Tailscale 1.96.3 is installed and `pedro-2023.tailc48d1c.ts.net` is the node hostname — `tailscale cert` issues real Let's Encrypt certs, eliminating mkcert as the default path IF the iPhone is on the tailnet. iPhone tailnet enrollment is unknown (00-RESEARCH.md Open Q #2); mkcert remains the documented fallback.

Output: A minimal Python HTTPS server on the chosen hostname, a builder-facing HTTPS-SETUP.md describing the exact reproducible steps, and a results JSON capturing which path worked.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/phases/00-measurement-gate/00-VALIDATION.md
@.planning/research/PITFALLS.md
@.planning/phases/00-measurement-gate/.gitignore

<interfaces>
Key facts from 00-RESEARCH.md the executor must use verbatim:

- Tailscale 1.96.3 is installed and active. Node hostname: `pedro-2023.tailc48d1c.ts.net`. Tailnet IP: `100.100.8.103`.
- `tailscale cert <hostname>` issues a real Let's Encrypt cert for the tailnet FQDN. On Windows, run from an elevated PowerShell if the first attempt reports a permission error.
- Writes two files in the current directory: `<hostname>.crt` and `<hostname>.key`.
- mkcert is NOT installed. Installation path if fallback is needed: `choco install mkcert` (requires elevated shell) OR scoop OR download from GitHub releases.
- `tailscale status` at research time showed `pixel-10-pro` (Android) and `siss-macbook-pro` but no iPhone device — iPhone may need tailnet enrollment OR we fall back to mkcert.
- From PITFALLS.md #2: the definitive acceptance check is `window.isSecureContext === true` in Safari, AND `navigator.mediaDevices` being defined (not undefined). Cert-valid + isSecureContext=false can happen on weird hostnames.
- DO NOT bind `0.0.0.0` for this probe. Bind to the Tailscale IP (100.100.8.103) or mkcert hostname only. Binding `0.0.0.0` exposes the probe to the entire LAN and is not needed for this test.

Minimal probe page to serve (HTML + inline JS):
```html
<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RayMe HTTPS probe</title>
<style>body{font-family:system-ui;padding:2em}.ok{color:green}.no{color:red}</style>
<h1>RayMe Phase 0 — HTTPS probe</h1>
<ul id="out"></ul>
<script>
  const out = document.getElementById("out");
  const row = (k, v, ok) => {
    const li = document.createElement("li");
    li.className = ok ? "ok" : "no";
    li.textContent = `${k}: ${v}`;
    out.appendChild(li);
  };
  row("window.isSecureContext", window.isSecureContext, window.isSecureContext);
  row("navigator.mediaDevices defined", !!navigator.mediaDevices, !!navigator.mediaDevices);
  row("location.href", location.href, true);
  row("location.protocol", location.protocol, location.protocol === "https:");
  row("userAgent", navigator.userAgent, true);
</script>
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write HTTPS probe server (tailscale-primary + mkcert-fallback) and HTTPS-SETUP doc skeleton</name>
  <files>
    .planning/phases/00-measurement-gate/probes/https_serve.py
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/00-RESEARCH.md (Common Pitfall #3 — Tailscale tailnet routing; Code Examples → Tailscale HTTPS Server pattern)
    .planning/research/PITFALLS.md (Pitfall #2 — mobile Safari HTTPS requirements, acceptance via window.isSecureContext)
  </read_first>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/https_serve.py`:

       ```python
       """HTTPS probe server for Phase 0 success criterion #1.

       Serves a single page that reports window.isSecureContext + navigator.mediaDevices
       to the browser. The builder loads this URL on their iPhone Safari and checks
       that both are true / defined.

       Usage:
         # Tailscale path (primary):
         #   1. tailscale cert pedro-2023.tailc48d1c.ts.net
         #   2. python https_serve.py --host pedro-2023.tailc48d1c.ts.net \
         #                            --cert pedro-2023.tailc48d1c.ts.net.crt \
         #                            --key  pedro-2023.tailc48d1c.ts.net.key \
         #                            --bind 100.100.8.103
         #
         # mkcert path (fallback):
         #   1. mkcert -install
         #   2. mkcert rayme.local 192.168.x.x
         #   3. python https_serve.py --host rayme.local \
         #                            --cert rayme.local+1.pem \
         #                            --key  rayme.local+1-key.pem \
         #                            --bind 192.168.x.x
       """
       from __future__ import annotations
       import argparse
       import http.server
       import ssl
       import sys

       PROBE_HTML = b"""<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RayMe HTTPS probe</title>
<style>body{font-family:system-ui;padding:2em}.ok{color:green}.no{color:red}
h1{font-size:1.2em}li{margin:.3em 0}</style>
<h1>RayMe Phase 0 - HTTPS probe</h1>
<p>All rows must be green for Phase 3's Voice Call screen to work on this device.</p>
<ul id="out"></ul>
<script>
  const out = document.getElementById("out");
  const row = (k, v, ok) => {
    const li = document.createElement("li");
    li.className = ok ? "ok" : "no";
    li.textContent = k + ": " + v;
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
           def do_GET(self):
               self.send_response(200)
               self.send_header("Content-Type", "text/html; charset=utf-8")
               self.send_header("Content-Length", str(len(PROBE_HTML)))
               self.send_header("Cache-Control", "no-store")
               self.end_headers()
               self.wfile.write(PROBE_HTML)

           def log_message(self, fmt, *args):
               sys.stderr.write(f"[probe] {self.address_string()} - {fmt % args}\n")

       def main() -> int:
           ap = argparse.ArgumentParser()
           ap.add_argument("--host", required=True,
                           help="Expected hostname (informational; goes into SNI-agnostic server_name)")
           ap.add_argument("--cert", required=True, help="Path to cert file (.crt or .pem)")
           ap.add_argument("--key",  required=True, help="Path to key  file (.key or -key.pem)")
           ap.add_argument("--bind", default="0.0.0.0",
                           help="IP to bind. Use the Tailscale IP (100.100.8.103) or LAN IP, NOT 0.0.0.0")
           ap.add_argument("--port", type=int, default=443,
                           help="HTTPS port. 443 on Windows requires admin; use 8443 as unprivileged fallback.")
           args = ap.parse_args()

           ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
           ctx.load_cert_chain(certfile=args.cert, keyfile=args.key)

           addr = (args.bind, args.port)
           srv = http.server.HTTPServer(addr, ProbeHandler)
           srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
           scheme_host = f"https://{args.host}" + ("" if args.port == 443 else f":{args.port}")
           print(f"[probe] Serving at {scheme_host}  (bound to {args.bind}:{args.port})", flush=True)
           print(f"[probe] Load this URL on iPhone Safari: {scheme_host}", flush=True)
           print(f"[probe] Press Ctrl+C to stop.", flush=True)
           try:
               srv.serve_forever()
           except KeyboardInterrupt:
               print("[probe] Shutting down.")
           return 0

       if __name__ == "__main__":
           sys.exit(main())
       ```

    2. Create `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` with a skeleton (task 2 fills in the "what actually worked" section):

       ````markdown
       # HTTPS on iPhone - Setup Procedure

       **Purpose:** Reproducible steps for Phase 3+ to serve Web UI over HTTPS
       on the builder's LAN so iPhone Safari allows mic capture.

       **Acceptance:** `window.isSecureContext === true` AND `navigator.mediaDevices`
       defined when the iPhone loads the served URL.

       ## Chosen Strategy

       _Filled in by Task 2 after measurement._

       - [ ] Tailscale (primary)
       - [ ] mkcert (fallback)

       ## Strategy A - Tailscale (preferred if iPhone is on the tailnet)

       ### Prerequisites
       - Tailscale installed on the backend machine (verify: `tailscale version`).
       - The iPhone must also be on the tailnet.
         - Install the Tailscale iOS app from the App Store.
         - Sign in with the same account that owns `pedro-2023`.
         - Confirm the iPhone appears in `tailscale status` or in https://login.tailscale.com/admin/machines.

       ### One-time setup
       ```powershell
       # On the backend machine, in the phase 0 directory:
       cd .planning/phases/00-measurement-gate
       tailscale cert pedro-2023.tailc48d1c.ts.net
       # Produces:
       #   pedro-2023.tailc48d1c.ts.net.crt
       #   pedro-2023.tailc48d1c.ts.net.key
       # These are real Let's Encrypt certs. Treat them as secrets.
       ```

       ### Running the probe
       ```powershell
       .venv-phase0\Scripts\python.exe probes\https_serve.py `
         --host pedro-2023.tailc48d1c.ts.net `
         --cert pedro-2023.tailc48d1c.ts.net.crt `
         --key  pedro-2023.tailc48d1c.ts.net.key `
         --bind 100.100.8.103 `
         --port 443
       # If port 443 fails with permission error, use --port 8443 and include :8443 in the URL.
       ```

       ### On the iPhone
       1. Open Safari.
       2. Navigate to `https://pedro-2023.tailc48d1c.ts.net` (or `:8443` if used).
       3. Confirm NO cert warning.
       4. Confirm the page renders 5 green rows.

       ## Strategy B - mkcert (fallback if iPhone is not on tailnet)

       ### Install mkcert (Windows, elevated shell)
       ```powershell
       choco install mkcert   # or: scoop install mkcert
       mkcert -install        # installs the local CA into the system trust store
       ```

       ### Generate a cert for a stable hostname
       Pick a hostname reachable from the iPhone. Options:
       - `rayme.local` (mDNS — works on same Wi-Fi)
       - The backend's LAN IP (e.g., `192.168.1.42`)
       - Both, as SANs

       ```powershell
       cd .planning/phases/00-measurement-gate
       mkcert rayme.local 192.168.1.42
       # Produces: rayme.local+1.pem + rayme.local+1-key.pem
       ```

       ### Install the mkcert root CA on iPhone
       mkcert stores the CA at `%LOCALAPPDATA%\mkcert\rootCA.pem`. To trust it on iOS:
       1. Export: `mkcert -CAROOT` to find the CA file.
       2. Email `rootCA.pem` to yourself, open the attachment on iPhone.
       3. iPhone prompts "Profile Downloaded" -> Settings -> Profile Downloaded -> Install.
       4. Settings -> General -> About -> Certificate Trust Settings -> toggle ON for "mkcert <username>".
       5. Reboot Safari.

       ### Running the probe
       ```powershell
       .venv-phase0\Scripts\python.exe probes\https_serve.py `
         --host rayme.local `
         --cert rayme.local+1.pem `
         --key  rayme.local+1-key.pem `
         --bind 192.168.1.42 `
         --port 443
       ```

       ### On the iPhone
       1. Connect to the same Wi-Fi as the backend.
       2. Safari -> `https://rayme.local` (or the LAN IP).
       3. Confirm no cert warning + 5 green rows.

       ## Security notes
       - `*.key` / `*-key.pem` / `*.mobileconfig` files are in .gitignore. Never commit.
       - Tailscale certs are valid real Let's Encrypt certs for a .ts.net subdomain; leaking the key would let an attacker on the tailnet impersonate the backend. Rotate via `tailscale cert` if the key ever leaks.
       - mkcert's root CA is trusted by every device it is installed on. The private key sits in `%LOCALAPPDATA%\mkcert\`. Do NOT share it.
       - This probe server MUST be stopped (Ctrl+C) immediately after the acceptance check. It is a static page with no auth and should not be left running.

       ## Troubleshooting

       | Symptom | Cause | Fix |
       |---|---|---|
       | iPhone shows "Cannot Connect to Server" | iPhone not on tailnet (Strategy A) or wrong Wi-Fi / mDNS (Strategy B) | Confirm `ping rayme.local` resolves from a desktop on the same Wi-Fi; or enroll iPhone in Tailscale. |
       | `window.isSecureContext === false` despite valid cert | Served over http://... or mixed scheme | Hit `https://...` explicitly. |
       | `navigator.mediaDevices === undefined` but isSecureContext is true | Safari private browsing restrictions on some builds | Re-open the page in a normal Safari tab. |
       | Port 443 permission denied on Windows | Requires admin | Use `--port 8443` and include `:8443` in the URL. |
       ````

    3. Commit both files.
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; test -f .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import ast; ast.parse(open('.planning/phases/00-measurement-gate/probes/https_serve.py').read()); print('syntax OK')" &amp;&amp; grep -q "window.isSecureContext" .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; grep -q "load_cert_chain" .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; grep -q "# HTTPS on iPhone - Setup Procedure" .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; grep -q "Strategy A - Tailscale" .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; grep -q "Strategy B - mkcert" .planning/phases/00-measurement-gate/HTTPS-SETUP.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/https_serve.py` exists and parses as valid Python (`python -c "import ast; ast.parse(open(...).read())"` exits 0).
    - File contains `window.isSecureContext` (probe HTML) and `load_cert_chain` (cert loading).
    - Script accepts `--host`, `--cert`, `--key`, `--bind`, `--port` flags (grep for each flag in the source).
    - File `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` exists and documents both Strategy A (Tailscale) and Strategy B (mkcert).
    - HTTPS-SETUP.md references `tailscale cert pedro-2023.tailc48d1c.ts.net` and `mkcert -install` as the respective one-time commands.
  </acceptance_criteria>
  <done>HTTPS probe server and setup doc skeleton are committed.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Builder performs iPhone verification and records result</name>
  <files>
    .planning/phases/00-measurement-gate/results/https_iphone.json
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md  (update "Chosen Strategy" section)
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md (the doc written in Task 1 — follow it step-by-step)
    .planning/phases/00-measurement-gate/probes/https_serve.py (usage flags)
  </read_first>
  <action>Human-verification checkpoint. Claude has already completed the automated work described under &lt;what-built&gt; above. The builder performs the steps in &lt;how-to-verify&gt; below and records the outcome as described; acceptance is gated on &lt;acceptance_criteria&gt;. When `workflow.auto_advance=true`, auto-mode auto-approves this checkpoint.</action>
  <what-built>
    Task 1 created a minimal HTTPS probe server (`probes/https_serve.py`) and a two-strategy setup doc (`HTTPS-SETUP.md`). Claude has now completed everything it can do via CLI. The remaining step requires physical access to the builder's iPhone.
  </what-built>
  <how-to-verify>
    Claude's automated steps first (run on the backend machine, in an elevated PowerShell if needed):

    1. **Try Strategy A (Tailscale).** From `.planning/phases/00-measurement-gate/`:
       ```powershell
       tailscale cert pedro-2023.tailc48d1c.ts.net
       ```
       - If this succeeds and produces `.crt` + `.key` files: proceed.
       - If it fails with a permission error: re-run in an elevated PowerShell.
       - If it fails with a "not logged in" error: run `tailscale up` first.
       - Record the outcome in the results JSON regardless.

    2. Start the probe server (Strategy A):
       ```powershell
       .venv-phase0\Scripts\python.exe probes\https_serve.py `
         --host pedro-2023.tailc48d1c.ts.net `
         --cert pedro-2023.tailc48d1c.ts.net.crt `
         --key  pedro-2023.tailc48d1c.ts.net.key `
         --bind 100.100.8.103 `
         --port 8443
       ```
       (Using port 8443 avoids the admin-required port 443.)

    3. **Builder on iPhone:**
       a. Confirm iPhone is on Tailscale. If not installed: App Store -> "Tailscale" -> sign in with the same account as `pedro-2023`. After sign-in, confirm iPhone appears in `tailscale status` on the backend.
       b. If iPhone cannot be enrolled in Tailscale, STOP Strategy A, fall through to Strategy B.
       c. Open Safari. Navigate to `https://pedro-2023.tailc48d1c.ts.net:8443`.
       d. Check:
          - No cert warning shown.
          - Page renders with 5 rows.
          - All 5 rows are green (especially the first two: `window.isSecureContext: true` and `navigator.mediaDevices defined: true`).
       e. Screenshot the page.

    4. **Fallback (Strategy B - mkcert) IF Strategy A fails:**
       Follow HTTPS-SETUP.md Strategy B end-to-end. Install mkcert via choco in an elevated shell, generate a cert for `rayme.local` + LAN IP, install the root CA on the iPhone via the Configuration Profile flow, re-run the probe server with mkcert paths, and test on Safari.

    5. After verification, Ctrl+C the probe server.

    6. **Record result in `results/https_iphone.json`:**
       ```json
       {
         "meta": { "timestamp": "<ISO8601>", "builder_confirmed": true },
         "strategy": "tailscale" | "mkcert",
         "hostname": "pedro-2023.tailc48d1c.ts.net" | "rayme.local",
         "bind_ip": "100.100.8.103" | "192.168.x.x",
         "port": 8443,
         "cert_path": "<relative path>",
         "key_path": "<relative path, will be gitignored>",
         "iphone_on_tailnet": true | false,
         "iphone_safari_isSecureContext": true,
         "iphone_safari_mediaDevices_defined": true,
         "cert_warning_shown": false,
         "screenshot_path": null,
         "notes": "<free text — any deviations from the doc, e.g., 'had to use mkcert because iPhone is managed by work MDM and cannot install Tailscale'>"
       }
       ```

    7. **Update HTTPS-SETUP.md** "Chosen Strategy" section with the [x] marker for whichever path worked.

    **Resume signal:** Reply with "approved" if `iphone_safari_isSecureContext === true` AND `iphone_safari_mediaDevices_defined === true` AND `cert_warning_shown === false`. Otherwise describe what happened (specific error message, row that was red, iPhone model/iOS version).
  </how-to-verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/https_iphone.json` exists with valid JSON.
    - `results/https_iphone.json` has `strategy` key set to either `"tailscale"` or `"mkcert"` (not null, not empty).
    - `results/https_iphone.json` has `iphone_safari_isSecureContext: true`.
    - `results/https_iphone.json` has `iphone_safari_mediaDevices_defined: true`.
    - `results/https_iphone.json` has `cert_warning_shown: false`.
    - `HTTPS-SETUP.md` "Chosen Strategy" section has exactly one `[x]` marker.
    - No `.key`, `.pem`, or `.mobileconfig` file is staged for git (verify with `git status --porcelain | grep -E '\.(key|pem|mobileconfig)$'` returning empty).
  </acceptance_criteria>
  <resume-signal>
    Reply "approved" once all acceptance criteria are satisfied. If iPhone is not available right now, reply "defer" and downstream plans 03-07 can still proceed in parallel (they do not depend on this plan's result).
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to &lt;acceptance_criteria&gt; above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume-signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Tailnet / LAN -> probe server | The probe server listens on the Tailscale IP (tailnet-scoped) or LAN IP. Only devices on the tailnet or LAN can reach it. |
| Backend filesystem -> cert key material | Private keys (Tailscale cert key, mkcert CA key) must never enter the git repo. |
| iPhone trust store | mkcert strategy modifies the iPhone's trust store via a Configuration Profile. Reversible via Settings → Profile → Remove. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-02-01 | Info Disclosure | Private key files (`*.key`, `*-key.pem`) | mitigate | `.gitignore` in plan 01 explicitly excludes `*.key` and `*.pem`. Task 2 acceptance criteria include `git status` check to confirm no key file is staged. |
| T-00-02-02 | Tampering | mkcert root CA installed on iPhone | accept | Documented in HTTPS-SETUP.md that this trust addition is reversible via iOS Settings. Builder is the sole user and authorized to modify their own device. |
| T-00-02-03 | Spoofing | Tailscale tailnet domain squatting | accept | `*.tailc48d1c.ts.net` cert is issued by Let's Encrypt and scoped to the tailnet only. Not reachable from the public internet. |
| T-00-02-04 | Denial of Service | Probe server left running unattended | mitigate | HTTPS-SETUP.md "Security notes" explicitly instructs builder to Ctrl+C immediately after verification. Server is a static page with no auth. |
| T-00-02-05 | Info Disclosure | User-Agent / IP leak in probe page | accept | Probe page exposes only the client's own data back to the client. Not logged beyond stderr which stays local. |

No high-severity threats. All sensitive material is excluded from git by the .gitignore from plan 01, and the probe server is a short-lived measurement tool.
</threat_model>

<verification>
Final acceptance:

```bash
# Results JSON exists and has the required pass fields
cat .planning/phases/00-measurement-gate/results/https_iphone.json | python -c "
import sys, json
d = json.load(sys.stdin)
assert d['iphone_safari_isSecureContext'] is True
assert d['iphone_safari_mediaDevices_defined'] is True
assert d['cert_warning_shown'] is False
assert d['strategy'] in ('tailscale', 'mkcert')
print('OK')
"

# No cert key material staged
git status --porcelain | grep -E '\.(key|pem|mobileconfig|p12)$' && echo "FAIL: key material staged" || echo "OK: no key material staged"

# HTTPS-SETUP.md marked with chosen strategy
grep -E "^\- \[x\]" .planning/phases/00-measurement-gate/HTTPS-SETUP.md
```
</verification>

<success_criteria>
- [ ] `probes/https_serve.py` runs under the Phase 0 venv and serves the probe page with a valid cert
- [ ] iPhone Safari loads the URL with NO cert warning
- [ ] `window.isSecureContext === true` on the iPhone
- [ ] `navigator.mediaDevices` is defined on the iPhone (not `undefined`)
- [ ] `results/https_iphone.json` records which strategy worked and the pass fields
- [ ] `HTTPS-SETUP.md` tells a future reader exactly how to reproduce the working setup
- [ ] No `.key` / `.pem` / `.mobileconfig` file is committed
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-02-SUMMARY.md` summarizing:
- Chosen strategy (Tailscale or mkcert) and why
- Final URL that worked on iPhone Safari
- Any deviations from the HTTPS-SETUP.md procedure
- Guidance for Phase 1: which HTTPS path to use in production serving
</output>
