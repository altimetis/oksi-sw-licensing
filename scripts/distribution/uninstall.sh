#!/usr/bin/env bash
set -euo pipefail

# OKSI Software Licensing Uninstaller (standalone)
# - Removes files recorded in /opt/oksi/sw-licensing/manifest.txt if present
# - Falls back to removing default install paths

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "[oksi-uninstall][error] must run as root (use sudo)" >&2; exit 1
  fi
}

require_root

APP_DIR="/opt/oksi/sw-licensing"
MANIFEST="$APP_DIR/manifest.txt"

echo "[oksi-uninstall] Starting..."

if [[ -f "$MANIFEST" ]]; then
  while IFS= read -r p; do
    if [[ -n "$p" && -e "$p" ]]; then
      rm -f "$p" || true
      echo "[oksi-uninstall] removed $p"
    fi
  done < "$MANIFEST"
fi

# Remove known locations
rm -f \
  /usr/local/bin/oksi-sw-license \
  /usr/local/bin/oksi_fingerprint \
  /usr/local/bin/oksi-sw-licensing-uninstall || true

rm -rf "$APP_DIR" || true

echo "[oksi-uninstall] done"

