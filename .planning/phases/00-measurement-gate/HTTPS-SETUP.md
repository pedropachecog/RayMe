# HTTPS on iPhone - Setup Procedure

**Purpose:** Reproducible steps for Phase 3+ to serve the RayMe Web UI over HTTPS
on the builder's LAN so iPhone Safari allows mic capture.

**Acceptance:** `window.isSecureContext === true` and `navigator.mediaDevices`
defined when the iPhone loads the served URL.

## Chosen Strategy

Filled in by the verification task after the iPhone check is complete.

- [ ] mkcert (primary)
- [ ] Tailscale (optional alternate)

## Strategy A - mkcert (primary on the real backend)

### Prerequisites

- Direct LAN access from the iPhone to `192.168.1.199`.
- `mkcert` installed on the backend machine.
- The generated mkcert root CA trusted on the iPhone.

### One-time setup

```powershell
# On OMEN-PC, from the phase 0 directory:
cd .planning/phases/00-measurement-gate
mkcert -install
mkcert rayme.local 192.168.1.199
# Produces:
#   rayme.local+1.pem
#   rayme.local+1-key.pem
```

### Running the probe

```powershell
.venv-phase0\Scripts\python.exe probes\https_serve.py `
  --host rayme.local `
  --cert rayme.local+1.pem `
  --key rayme.local+1-key.pem `
  --bind 192.168.1.199 `
  --port 8443
```

### On the iPhone

1. Open Safari.
2. Navigate to `https://rayme.local:8443` or the direct LAN IP if hostname resolution is not configured.
3. Confirm there is no certificate warning.
4. Confirm the page shows all green rows.

## Strategy B - Tailscale (optional alternate if installed later)

### Preconditions

- Tailscale installed on the backend machine.
- Tailscale installed on the iPhone.
- A valid tailnet hostname and tailnet IP for this backend.
- `tailscale cert` available on the backend after login to the tailnet.

```powershell
cd .planning/phases/00-measurement-gate
tailscale status
tailscale ip -4
tailscale cert <backend-host>.ts.net
```

### Running the probe

```powershell
.venv-phase0\Scripts\python.exe probes\https_serve.py `
  --host <backend-host>.ts.net `
  --cert <tailscale-cert.pem> `
  --key <tailscale-key.pem> `
  --bind <tailnet-ip> `
  --port 8443
```

### On the iPhone

1. Confirm the iPhone is enrolled in Tailscale and connected to the same tailnet.
2. Open Safari.
3. Navigate to `https://<backend-host>.ts.net:8443`.
4. Confirm there is no certificate warning.
5. Confirm the page shows all green rows.

## Security Notes

- `*.key`, `*-key.pem`, `*.mobileconfig`, and cert material remain gitignored. Never commit them.
- Tailscale certs are valid public certs for a `.ts.net` subdomain; leaking the key would let an attacker on the tailnet impersonate the backend.
- mkcert's root CA is trusted by every device it is installed on. Its private key lives in `%LOCALAPPDATA%\mkcert\`. Do not share it.
- Stop the probe server immediately after verification. It is only a Phase 0 acceptance probe.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Safari shows a cert warning | Root CA not trusted, wrong hostname, or wrong cert/key pair | Recreate the cert, reinstall the root CA, and load the exact hostname the cert covers |
| `window.isSecureContext` is `false` | Wrong origin, wrong hostname, or an HTTP fallback | Load the HTTPS URL again and confirm the hostname matches the certificate |
| `navigator.mediaDevices` is undefined | Safari does not trust the origin yet | Fix the certificate trust problem first; `mediaDevices` is the real acceptance signal |
| Probe server fails to bind | Port 443 requires elevation or the IP is wrong | Use `--port 8443` first and confirm the bind IP is `192.168.1.199` or a valid tailnet IP |
| iPhone cannot resolve `rayme.local` | LAN hostname resolution is missing | Use the direct LAN IP first, or add local DNS/Bonjour resolution later |

## What Actually Worked

Filled in by Task 2 after the real iPhone verification:

- Chosen path:
- Probe URL:
- Certificate source:
- `window.isSecureContext`:
- `navigator.mediaDevices`:
- Notes:
