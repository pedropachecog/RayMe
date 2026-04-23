---
phase: 00-measurement-gate
plan: 02
type: execute
wave: 2
depends_on: [01]
files_modified:
  - .planning/phases/00-measurement-gate/probes/https_serve.py
  - .planning/phases/00-measurement-gate/HTTPS-SETUP.md
  - .planning/phases/00-measurement-gate/results/https_android.json
autonomous: false
requirements: []
user_setup:
  - service: mkcert
    why: "This is the only supported Phase 0 HTTPS path for the builder's Android phone."
    env_vars: []
    dashboard_config:
      - task: "Trust the mkcert root CA on the Android phone, then verify the browser accepts the HTTPS origin."
        location: "Android security settings / browser trust flow"

must_haves:
  truths:
    - "The builder's Android browser loads a local HTTPS URL with no certificate warning"
    - "`window.isSecureContext` returns `true` in that browser at that URL"
    - "`navigator.mediaDevices` is defined (not undefined) in the same Android browser tab"
    - "HTTPS-SETUP.md documents the exact reproducible mkcert-on-LAN steps that worked"
    - "Private key material (mkcert cert key, mkcert CA key) is not committed to git"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/probes/https_serve.py"
      provides: "Minimal Python HTTPS server that serves an isSecureContext + mediaDevices probe page"
      contains: "window.isSecureContext"
    - path: ".planning/phases/00-measurement-gate/HTTPS-SETUP.md"
      provides: "Reproducible builder-facing doc with the single supported Android HTTPS path"
      contains: "# HTTPS on Android - Setup Procedure"
    - path: ".planning/phases/00-measurement-gate/results/https_android.json"
      provides: "Machine-readable Android HTTPS verification result"
      contains: "android_browser_isSecureContext"
  key_links:
    - from: ".planning/phases/00-measurement-gate/probes/https_serve.py"
      to: "cert file + key file"
      via: "ssl.SSLContext.load_cert_chain"
      pattern: "load_cert_chain"
    - from: ".planning/phases/00-measurement-gate/HTTPS-SETUP.md"
      to: "probes/https_serve.py"
      via: "documented invocation"
      pattern: "python .*https_serve.py"
---

<objective>
Empirically verify that the builder can load an HTTPS URL on their Android phone with no certificate warning and `window.isSecureContext === true`, and document the reproducible procedure so Phase 1 can ship this as the LAN HTTPS workflow.

Purpose: This is Phase 0 success criterion #1. The builder device baseline is Android. On this backend there is no Tailscale install or `.ts.net` hostname, so the Phase 0 path is pinned to **mkcert over direct LAN**. The plan does not maintain a second alternate path.

Output: A minimal Python HTTPS server on the chosen hostname, a builder-facing `HTTPS-SETUP.md` describing the exact reproducible steps, and `results/https_android.json` capturing what worked.
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
Key facts the executor must use:

- Execution host for this plan is the real backend `OMEN-PC` at `192.168.1.199`, reached over SSH. Do not substitute the local Codex workstation or its WSL shell for backend commands in this probe.
- Backend hostname: `OMEN-PC`. LAN IP: `192.168.1.199`.
- `mkcert` is the only supported Phase 0 HTTPS path for this plan.
- `mkcert` is not installed by default. Install path if needed: `choco install mkcert` (elevated shell) or equivalent manual install.
- Definitive acceptance check: `window.isSecureContext === true` in the Android browser, and `navigator.mediaDevices` defined in that same tab. A cert can look valid while the origin still fails secure-context rules.
- Do not bind `0.0.0.0` for this probe. Bind only to the LAN IP `192.168.1.199`.

Minimal probe page:
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
  <name>Task 1: Write HTTPS probe server and Android HTTPS setup doc</name>
  <files>
    .planning/phases/00-measurement-gate/probes/https_serve.py
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/00-RESEARCH.md
    .planning/research/PITFALLS.md
  </read_first>
  <action>
    1. Ensure `.planning/phases/00-measurement-gate/probes/https_serve.py` exists and serves a single HTML page that reports `window.isSecureContext`, `navigator.mediaDevices`, `location.href`, `location.protocol`, and `userAgent`.
    2. Ensure the server loads a certificate/key pair via `ssl.SSLContext.load_cert_chain`, accepts `--host`, `--cert`, `--key`, `--bind`, and `--port`, and rejects `0.0.0.0` as a bind target.
    3. Ensure `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` documents the single supported path:
       - install `mkcert`
       - run `mkcert -install`
       - mint a cert for `rayme.local` and `192.168.1.199`
       - start the probe server on `192.168.1.199:8443`
       - verify from Android Chrome
       - stop the probe after verification
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; test -f .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import ast; ast.parse(open('.planning/phases/00-measurement-gate/probes/https_serve.py').read()); print('syntax OK')" &amp;&amp; grep -q "window.isSecureContext" .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; grep -q "load_cert_chain" .planning/phases/00-measurement-gate/probes/https_serve.py &amp;&amp; grep -q "# HTTPS on Android - Setup Procedure" .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; grep -q "mkcert -install" .planning/phases/00-measurement-gate/HTTPS-SETUP.md &amp;&amp; ! grep -q "Strategy B - Tailscale" .planning/phases/00-measurement-gate/HTTPS-SETUP.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/https_serve.py` exists and parses as valid Python.
    - File contains `window.isSecureContext` and `load_cert_chain`.
    - Script accepts `--host`, `--cert`, `--key`, `--bind`, and `--port`.
    - File `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` exists and documents `mkcert` as the single supported path.
    - HTTPS-SETUP.md does not describe Tailscale as an alternate execution path for this plan.
  </acceptance_criteria>
  <done>HTTPS probe server and Android setup doc exist and match the single-path contract.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Builder performs Android verification and records result</name>
  <files>
    .planning/phases/00-measurement-gate/results/https_android.json
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/HTTPS-SETUP.md
    .planning/phases/00-measurement-gate/probes/https_serve.py
  </read_first>
  <action>Human-verification checkpoint. The remaining step requires the builder's Android phone and browser trust flow.</action>
  <what-built>
    Task 1 created a minimal HTTPS probe server and a single-path Android HTTPS setup doc. The remaining step requires physical access to the builder's Android phone.
  </what-built>
  <how-to-verify>
    1. On `OMEN-PC`, from `.planning/phases/00-measurement-gate/`, install and initialize mkcert if needed:
       ```powershell
       choco install mkcert
       mkcert -install
       mkcert rayme.local 192.168.1.199
       ```

    2. Start the probe server:
       ```powershell
       .venv-phase0\Scripts\python.exe probes\https_serve.py `
         --host rayme.local `
         --cert rayme.local+1.pem `
         --key rayme.local+1-key.pem `
         --bind 192.168.1.199 `
         --port 8443
       ```

    3. On the Android phone:
       - trust the mkcert root CA if Android requires an explicit trust/import step
       - open Chrome
       - navigate to `https://rayme.local:8443`
       - if local hostname resolution fails, retry with `https://192.168.1.199:8443` using a cert minted for that IP
       - confirm:
         - no certificate warning
         - the page renders
         - `window.isSecureContext` is `true`
         - `navigator.mediaDevices defined` is `true`

    4. Stop the probe server after verification.

    5. Record the result in `results/https_android.json`:
       ```json
       {
         "meta": { "timestamp": "<ISO8601>", "builder_confirmed": true },
         "strategy": "mkcert",
         "hostname": "rayme.local",
         "bind_ip": "192.168.1.199",
         "port": 8443,
         "cert_path": "<relative path>",
         "key_path": "<relative path, gitignored>",
         "browser": "Chrome",
         "android_browser_isSecureContext": true,
         "android_browser_mediaDevices_defined": true,
         "cert_warning_shown": false,
         "screenshot_path": null,
         "notes": "<free text>"
       }
       ```

    6. Update `HTTPS-SETUP.md` "Chosen Strategy" section to mark mkcert as the path that worked.

    Resume signal: reply `approved` if `android_browser_isSecureContext === true`, `android_browser_mediaDevices_defined === true`, and `cert_warning_shown === false`. Otherwise report the exact failure.
  </how-to-verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/results/https_android.json` exists with valid JSON.
    - `results/https_android.json` has `strategy: "mkcert"`.
    - `results/https_android.json` has `android_browser_isSecureContext: true`.
    - `results/https_android.json` has `android_browser_mediaDevices_defined: true`.
    - `results/https_android.json` has `cert_warning_shown: false`.
    - `HTTPS-SETUP.md` "Chosen Strategy" section marks mkcert as the working path.
    - No `.key`, `.pem`, `.crt`, or `.p12` file is staged for git.
  </acceptance_criteria>
  <resume-signal>
    Reply `approved` once all acceptance criteria are satisfied. If Android is not available right now, reply `defer` and downstream plans can continue.
  </resume-signal>
  <verify><automated>echo "checkpoint: acceptance delegated to <acceptance_criteria> above; pass when resume-signal received"</automated></verify>
  <done>Acceptance criteria above are satisfied and the builder returned the expected resume signal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LAN -> probe server | The probe server listens only on the LAN IP `192.168.1.199`. |
| Backend filesystem -> cert key material | Private keys and CA artifacts must never enter the git repo. |
| Android trust store | mkcert trust is added to the builder's phone and must be removable. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-02-01 | Info Disclosure | Private key files (`*.key`, `*.pem`, `*.crt`) | mitigate | `.gitignore` excludes key/cert artifacts and acceptance criteria include a `git status` check. |
| T-00-02-02 | Tampering | mkcert root CA trusted on Android | accept | Documented as a local, reversible trust change on the builder's own device. |
| T-00-02-03 | Denial of Service | Probe server left running unattended | mitigate | HTTPS-SETUP.md explicitly instructs the builder to stop the probe immediately after verification. |
| T-00-02-04 | Info Disclosure | User-Agent / IP visible in probe page | accept | The page only reflects the client's own data back to the client. |

No high-severity threats. The probe is a short-lived measurement tool.
</threat_model>

<verification>
Final acceptance:

```bash
cat .planning/phases/00-measurement-gate/results/https_android.json | python -c "
import sys, json
d = json.load(sys.stdin)
assert d['strategy'] == 'mkcert'
assert d['android_browser_isSecureContext'] is True
assert d['android_browser_mediaDevices_defined'] is True
assert d['cert_warning_shown'] is False
print('OK')
"

git status --porcelain | grep -E '\.(key|pem|crt|p12)$' && echo "FAIL: key material staged" || echo "OK: no key material staged"

grep -E "^\- \[x\]" .planning/phases/00-measurement-gate/HTTPS-SETUP.md
```
</verification>

<success_criteria>
- [ ] `probes/https_serve.py` runs under the Phase 0 venv and serves the probe page with a valid cert
- [ ] Android Chrome loads the URL with no cert warning
- [ ] `window.isSecureContext === true` on the Android phone
- [ ] `navigator.mediaDevices` is defined on the Android phone
- [ ] `results/https_android.json` records the working mkcert path and pass fields
- [ ] `HTTPS-SETUP.md` tells a future reader exactly how to reproduce the working Android setup
- [ ] No key or cert material is committed
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-02-SUMMARY.md` summarizing:
- Chosen strategy (`mkcert`) and why
- Final URL that worked on Android Chrome
- Any deviations from the documented procedure
- Guidance for Phase 1: use the same mkcert-on-LAN path for development serving
</output>
