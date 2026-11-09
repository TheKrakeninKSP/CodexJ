#!/usr/bin/env bash
# Install / update the CodexJ systemd units and restart the service.
#
# Units installed from packaging/ to /etc/systemd/system/ (each only if it changed):
#   codexj.service         - the headless server
#   codexj-backup.service  - one-shot DB snapshot to backup/ for restic (see RESTIC-README.md)
#   codexj-backup.timer    - triggers codexj-backup.service daily at 00:00
#
# Rebuilds the frontend (python build.py --server) as the service user, then
# reloads systemd, enables + restarts the server, and enables + restarts the
# backup timer so the latest code and unit settings take effect. Safe to re-run
# after every `git pull`.
#
# Usage (from anywhere):
#   bash packaging/install_service.sh              # rebuild frontend + restart
#   bash packaging/install_service.sh --no-build   # skip the frontend rebuild
#
# Re-invokes itself with sudo if not already root.

set -euo pipefail

SERVICE_NAME="codexj"
BACKUP_NAME="codexj-backup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS=(
  "${SERVICE_NAME}.service"
  "${BACKUP_NAME}.service"
  "${BACKUP_NAME}.timer"
)

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo --preserve-env=PATH bash "$0" "$@"
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "error: systemctl not found - this script requires a systemd-based Linux host." >&2
  exit 1
fi

for unit in "${UNITS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/${unit}" ]]; then
    echo "error: unit file not found at ${SCRIPT_DIR}/${unit}" >&2
    exit 1
  fi
done

# Sanity-check the paths the service units point at, so a bad unit doesn't get
# installed and then crash-loop (or fail silently every night).
check_service_paths() {
  local src_unit="$1"
  local working_dir exec_bin
  working_dir="$(sed -n 's/\r$//; s/^WorkingDirectory=//p' "${src_unit}")"
  exec_bin="$(sed -n 's/\r$//; s/^ExecStart=\([^ ]*\).*/\1/p' "${src_unit}")"
  if [[ -n "${working_dir}" && ! -d "${working_dir}" ]]; then
    echo "error: WorkingDirectory '${working_dir}' does not exist - edit ${src_unit}." >&2
    exit 1
  fi
  if [[ -n "${exec_bin}" && ! -x "${exec_bin}" ]]; then
    echo "error: ExecStart binary '${exec_bin}' (in ${src_unit}) is missing or not executable." >&2
    echo "       Create the venv first: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
}
check_service_paths "${SCRIPT_DIR}/${SERVICE_NAME}.service"
check_service_paths "${SCRIPT_DIR}/${BACKUP_NAME}.service"

# Rebuild the frontend. The built bundle (src/frontend/dist -> backend static dir)
# is gitignored, so after a `git pull` the server keeps serving the old UI until
# this runs - restarting the service alone does NOT pick up frontend changes.
# Runs as the service's User= so build output isn't root-owned. Skip with --no-build.
if [[ " $* " != *" --no-build "* ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  svc_user="$(sed -n 's/\r$//; s/^User=//p' "${SCRIPT_DIR}/${SERVICE_NAME}.service")"
  svc_user="${svc_user:-root}"
  echo "Rebuilding frontend as ${svc_user} (python build.py --server)..."
  # PATH is carried through from the invoking user so npm/node (e.g. via nvm) are found.
  if ! runuser -u "${svc_user}" -- env PATH="${PATH}" HOME="$(getent passwd "${svc_user}" | cut -d: -f6)" \
      bash -c 'cd "$1" && .venv/bin/python build.py --server' _ "${REPO_ROOT}"; then
    echo "error: frontend build failed - service not restarted." >&2
    exit 1
  fi
fi

tmp_unit="$(mktemp)"
trap 'rm -f "${tmp_unit}"' EXIT

install_unit() {
  local unit="$1"
  local src_unit="${SCRIPT_DIR}/${unit}"
  local dest_unit="/etc/systemd/system/${unit}"
  # Normalise to LF first (repo is also edited on Windows) so the comparison and
  # the installed file are both CRLF-free.
  sed 's/\r$//' "${src_unit}" > "${tmp_unit}"
  if [[ -f "${dest_unit}" ]] && cmp -s "${tmp_unit}" "${dest_unit}"; then
    echo "Unit file unchanged: ${dest_unit}"
  else
    install -m 0644 -o root -g root "${tmp_unit}" "${dest_unit}"
    echo "Installed unit file: ${dest_unit}"
  fi
}
for unit in "${UNITS[@]}"; do
  install_unit "${unit}"
done

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service" >/dev/null

# The backup service is triggered by its timer, not enabled itself. Restart the
# timer so schedule changes take effect immediately.
systemctl enable "${BACKUP_NAME}.timer" >/dev/null
systemctl restart "${BACKUP_NAME}.timer"
echo "Backup timer active - next snapshot: $(systemctl show "${BACKUP_NAME}.timer" --property=NextElapseUSecRealtime --value)"

echo "Restarting ${SERVICE_NAME}..."
systemctl restart "${SERVICE_NAME}.service"

# Give it a moment, then confirm it actually stayed up.
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
  echo "${SERVICE_NAME} is running."
  systemctl --no-pager --lines=0 status "${SERVICE_NAME}.service" || true
else
  echo "error: ${SERVICE_NAME} failed to start. Recent logs:" >&2
  journalctl -u "${SERVICE_NAME}.service" --no-pager -n 30 >&2 || true
  exit 1
fi
