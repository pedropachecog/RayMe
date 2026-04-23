#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(
  CDPATH= cd -- "$(dirname -- "$0")"
  pwd
)
REPO_ROOT=$(
  CDPATH= cd -- "$SCRIPT_DIR/.."
  pwd
)

PERSIST_DIR="${RAYME_SSH_PERSIST_DIR:-$REPO_ROOT/.local/phase0-ssh}"
PERSIST_KEY="$PERSIST_DIR/rayme_omen_phase0_ed25519"
PERSIST_PUB="$PERSIST_DIR/rayme_omen_phase0_ed25519.pub"

RUNTIME_DIR="${HOME}/.ssh"
RUNTIME_KEY="$RUNTIME_DIR/rayme_omen_phase0_ed25519"
RUNTIME_PUB="$RUNTIME_DIR/rayme_omen_phase0_ed25519.pub"
RUNTIME_CONFIG="$RUNTIME_DIR/config"
RUNTIME_KNOWN_HOSTS="$RUNTIME_DIR/known_hosts"

HOST_ALIAS="${RAYME_SSH_ALIAS:-rayme-ssh}"
HOST_NAME="${RAYME_SSH_HOST:-192.168.1.199}"
HOST_USER="${RAYME_SSH_USER:-rayme-ssh}"
HOST_KEY_LINE="|1|LQzkMlPBqXf8ePYptjPlykXbouc=|ouEQLKiH3I2PUADyDtJMWx8cPoo= ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMVVdInDujPHww5clxsjn+BEa014hFRlt0Wu11pwjnWL"

CONFIG_BEGIN="# >>> RayMe Phase 0 SSH ($HOST_ALIAS) >>>"
CONFIG_END="# <<< RayMe Phase 0 SSH ($HOST_ALIAS) <<<"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  status        Show persistent and runtime SSH state
  restore       Copy the persisted repo-local key into ~/.ssh and write config
  save          Copy the current ~/.ssh key into the persisted repo-local path
  connect-test  Run 'ssh rayme-ssh whoami' after restore

Persistent source:
  $PERSIST_KEY

Runtime target:
  $RUNTIME_KEY

Optional overrides:
  RAYME_SSH_ALIAS   Host alias written to ~/.ssh/config (default: rayme-ssh)
  RAYME_SSH_HOST    Host/IP to connect to (default: 192.168.1.199)
  RAYME_SSH_USER    Windows account to log in as (default: rayme-ssh)
EOF
}

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
  chmod 700 "$RUNTIME_DIR"
}

ensure_persist_dir() {
  mkdir -p "$PERSIST_DIR"
  chmod 700 "$PERSIST_DIR"
}

write_runtime_config() {
  local temp_config
  temp_config="$(mktemp "$RUNTIME_DIR/config.rayme-phase0.XXXXXX")"

  if [[ -f "$RUNTIME_CONFIG" ]]; then
    awk -v begin="$CONFIG_BEGIN" -v end="$CONFIG_END" '
      $0 == begin { skip = 1; next }
      $0 == end { skip = 0; next }
      !skip { print }
    ' "$RUNTIME_CONFIG" >"$temp_config"
  else
    : >"$temp_config"
  fi

  cat >>"$temp_config" <<EOF
$CONFIG_BEGIN
Host $HOST_ALIAS
  HostName $HOST_NAME
  User $HOST_USER
  IdentityFile $RUNTIME_KEY
  IdentitiesOnly yes
  StrictHostKeyChecking no
  UserKnownHostsFile $RUNTIME_KNOWN_HOSTS
$CONFIG_END
EOF

  mv "$temp_config" "$RUNTIME_CONFIG"
  chmod 600 "$RUNTIME_CONFIG"
}

write_runtime_known_hosts() {
  touch "$RUNTIME_KNOWN_HOSTS"
  chmod 600 "$RUNTIME_KNOWN_HOSTS"

  if ! grep -Fqx "$HOST_KEY_LINE" "$RUNTIME_KNOWN_HOSTS"; then
    printf '%s\n' "$HOST_KEY_LINE" >>"$RUNTIME_KNOWN_HOSTS"
  fi
}

save_public_key_if_missing() {
  if [[ ! -f "$PERSIST_PUB" ]]; then
    ssh-keygen -y -f "$PERSIST_KEY" >"$PERSIST_PUB"
    chmod 644 "$PERSIST_PUB"
  fi
}

command_status() {
  printf 'host_alias=%s\n' "$HOST_ALIAS"
  printf 'host_name=%s\n' "$HOST_NAME"
  printf 'host_user=%s\n' "$HOST_USER"
  printf 'repo_root=%s\n' "$REPO_ROOT"
  printf 'persist_dir=%s\n' "$PERSIST_DIR"
  printf 'persist_key=%s\n' "$([[ -f "$PERSIST_KEY" ]] && echo present || echo missing)"
  printf 'persist_pub=%s\n' "$([[ -f "$PERSIST_PUB" ]] && echo present || echo missing)"
  printf 'runtime_key=%s\n' "$([[ -f "$RUNTIME_KEY" ]] && echo present || echo missing)"
  printf 'runtime_pub=%s\n' "$([[ -f "$RUNTIME_PUB" ]] && echo present || echo missing)"
  printf 'runtime_config=%s\n' "$([[ -f "$RUNTIME_CONFIG" ]] && echo present || echo missing)"
  printf 'runtime_known_hosts=%s\n' "$([[ -f "$RUNTIME_KNOWN_HOSTS" ]] && echo present || echo missing)"
}

command_restore() {
  [[ -f "$PERSIST_KEY" ]] || die "Missing persisted key at $PERSIST_KEY. Restore the verified Phase 0 key there first."

  ensure_runtime_dir
  cp "$PERSIST_KEY" "$RUNTIME_KEY"
  chmod 600 "$RUNTIME_KEY"

  if [[ -f "$PERSIST_PUB" ]]; then
    cp "$PERSIST_PUB" "$RUNTIME_PUB"
    chmod 644 "$RUNTIME_PUB"
  else
    ssh-keygen -y -f "$RUNTIME_KEY" >"$RUNTIME_PUB"
    chmod 644 "$RUNTIME_PUB"
  fi

  write_runtime_config
  write_runtime_known_hosts

  printf 'Restored runtime SSH state for %s.\n' "$HOST_ALIAS"
  printf 'Next: ssh %s whoami\n' "$HOST_ALIAS"
}

command_save() {
  [[ -f "$RUNTIME_KEY" ]] || die "Missing runtime key at $RUNTIME_KEY. Nothing to persist."

  ensure_persist_dir
  cp "$RUNTIME_KEY" "$PERSIST_KEY"
  chmod 600 "$PERSIST_KEY"

  if [[ -f "$RUNTIME_PUB" ]]; then
    cp "$RUNTIME_PUB" "$PERSIST_PUB"
    chmod 644 "$PERSIST_PUB"
  else
    save_public_key_if_missing
  fi

  printf 'Persisted runtime SSH key into %s.\n' "$PERSIST_DIR"
}

command_connect_test() {
  command_restore
  ssh "$HOST_ALIAS" whoami
}

main() {
  local command="${1:-status}"

  case "$command" in
    status)
      command_status
      ;;
    restore)
      command_restore
      ;;
    save)
      command_save
      ;;
    connect-test)
      command_connect_test
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
