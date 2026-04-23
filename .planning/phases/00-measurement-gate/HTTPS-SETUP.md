# HTTPS on Android - Setup Procedure

**Purpose:** Reproducible steps for Phase 3+ to serve the RayMe Web UI over HTTPS
on the builder's LAN so the builder's Android browser allows mic capture.

**Acceptance:** `window.isSecureContext === true` and `navigator.mediaDevices`
defined when the Android phone loads the served URL.

## Chosen Strategy

- [x] mkcert on LAN (the only supported Phase 0 path)

## mkcert on LAN

### Prerequisites

- Direct LAN access from the Android phone to `192.168.1.199`.
- `mkcert` installed on the backend machine.
- The generated mkcert root CA trusted on the Android phone if the mkcert path is used.

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
  --host 192.168.1.199 `
  --cert rayme.local+1.pem `
  --key rayme.local+1-key.pem `
  --bind 192.168.1.199 `
  --port 8443
```

### On the Android Phone

1. Open Chrome first. If Chrome behaves differently on your Android build, try another Android browser as a fallback and record which one worked.
2. Navigate to `https://192.168.1.199:8443` first. Use `https://rayme.local:8443` only if local hostname resolution is configured on the LAN.
3. Confirm there is no certificate warning.
4. Confirm the page shows all green rows.

## Security Notes

- `*.key`, `*.pem`, `*.crt`, and other cert material remain gitignored. Never commit them.
- mkcert's root CA is trusted by every device it is installed on. Its private key lives in `%LOCALAPPDATA%\mkcert\`. Do not share it.
- Stop the probe server immediately after verification. It is only a Phase 0 acceptance probe.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Android browser shows a cert warning | Root CA not trusted, wrong hostname, or wrong cert/key pair | Recreate the cert, reinstall the root CA if using mkcert, and load the exact hostname the cert covers |
| `window.isSecureContext` is `false` | Wrong origin, wrong hostname, or an HTTP fallback | Load the HTTPS URL again and confirm the hostname matches the certificate |
| `navigator.mediaDevices` is undefined | The Android browser does not trust the origin yet | Fix the certificate trust problem first; `mediaDevices` is the real acceptance signal |
| Probe server fails to bind | Port 443 requires elevation or the IP is wrong | Use `--port 8443` first and confirm the bind IP is `192.168.1.199` |
| Android phone cannot resolve `rayme.local` | LAN hostname resolution is missing | Use the direct LAN IP first, or add local DNS/Bonjour resolution later |

## What Actually Worked

- Chosen path: mkcert on LAN
- Probe URL: `https://192.168.1.199:8443`
- Browser: Android Chrome
- Certificate source: `mkcert rayme.local 192.168.1.199`, with the mkcert root CA installed on the Android phone
- `window.isSecureContext`: `true`
- `navigator.mediaDevices`: defined / `true`
- Notes: `rayme.local` was included in the cert SANs, but the actual passing verification used the direct LAN IP because local hostname resolution was not configured. A temporary HTTP file-transfer helper on `8081` was used only to move `mkcert-rootCA.crt` onto the phone and was removed immediately after the certificate import and HTTPS pass.
