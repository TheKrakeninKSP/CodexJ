#!/usr/bin/env bash
# Install / update the CodexJ systemd unit and restart the service.
#
# Copies packaging/codexj.service to /etc/systemd/system/ (only if it changed),
# reloads systemd, enables the unit at boot, and restarts it so the latest code
# and unit settings take effect. Safe to re-run after every `git pull`.
#
# Usage (from anywhere):
#   bash packaging/install_service.sh
#
# Re-invokes itself with sudo if not already root.

set -euo pipefail

SERVICE_NAME="codexj"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_UNIT="${SCRIPT_DIR}/${SERVICE_NAME}.service"
DEST_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo --preserve-env=PATH bash "$0" "$@"
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "error: systemctl not found - this script requires a systemd-based Linux host." >&2
  exit 1
fi

if [[ ! -f "${SRC_UNIT}" ]]; then
  echo "error: unit file not found at ${SRC_UNIT}" >&2
  exit 1
fi

# Sanity-check the paths the unit points at, so a bad unit doesn't get
# installed and then crash-loop.
working_dir="$(sed -n 's/^WorkingDirectory=//p' "${SRC_UNIT}")"
exec_bin="$(sed -n 's/^ExecStart=\([^ ]*\).*/\1/p' "${SRC_UNIT}")"
if [[ -n "${working_dir}" && ! -d "${working_dir}" ]]; then
  echo "error: WorkingDirectory '${working_dir}' does not exist - edit ${SRC_UNIT}." >&2
  exit 1
fi
if [[ -n "${exec_bin}" && ! -x "${exec_bin}" ]]; then
  echo "error: ExecStart binary '${exec_bin}' is missing or not executable." >&2
  echo "       Create the venv first: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# Normalise to LF first (repo is also edited on Windows) so the comparison and
# the installed file are both CRLF-free.
tmp_unit="$(mktemp)"
trap 'rm -f "${tmp_unit}"' EXIT
sed 's/\r$//' "${SRC_UNIT}" > "${tmp_unit}"

if [[ -f "${DEST_UNIT}" ]] && cmp -s "${tmp_unit}" "${DEST_UNIT}"; then
  echo "Unit file unchanged: ${DEST_UNIT}"
else
  install -m 0644 -o root -g root "${tmp_unit}" "${DEST_UNIT}"
  echo "Installed unit file: ${DEST_UNIT}"
fi

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service" >/dev/null
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
