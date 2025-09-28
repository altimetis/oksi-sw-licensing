#!/usr/bin/env bash
set -euo pipefail

# OKSI Software Licensing Installer
# - Installs Python licensing app into a self-contained venv under /opt/oksi/sw-licensing
# - Installs native fingerprint binary to /usr/local/bin/oksi_fingerprint
# - Does not touch global Python modules
#
# Usage (remote):
#   curl -fsSL https://github.com/altimetis/oksi-sw-licensing/releases/latest/download/install.sh | sudo bash
#
# Env overrides:
#   OKSI_DOWNLOAD_BASE   Base URL for release assets (default: https://github.com/altimetis/oksi-sw-licensing/releases/latest/download)
#   OKSI_PREFIX          Install prefix for binaries (default: /usr/local)
#   OKSI_ROOT            Install root for app (default: /opt/oksi)
#   OKSI_PYTHON          Python interpreter to use for venv (default: python3)
#   OKSI_SKIP_FP         If set to 1, skip installing oksi_fingerprint
#
# Optional flags (when running locally):
#   --base <url>         Override download base URL
#   --prefix <dir>       Override /usr/local
#   --root <dir>         Override /opt/oksi
#   --python <path>      Override python3
#   --skip-fingerprint   Do not install fingerprint binary

umask 022

log() { echo "[oksi-install] $*"; }
err() { echo "[oksi-install][error] $*" >&2; }

BASE_URL=${OKSI_DOWNLOAD_BASE:-"https://github.com/altimetis/oksi-sw-licensing/releases/latest/download"}
PREFIX=${OKSI_PREFIX:-"/usr/local"}
OKSI_ROOT=${OKSI_ROOT:-"/opt/oksi"}
PYTHON_BIN=${OKSI_PYTHON:-"python3"}
INSTALL_FP=${OKSI_SKIP_FP:-0}
if [[ "$INSTALL_FP" != "1" ]]; then INSTALL_FP=1; else INSTALL_FP=0; fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE_URL="$2"; shift 2;;
    --prefix) PREFIX="$2"; shift 2;;
    --root) OKSI_ROOT="$2"; shift 2;;
    --python) PYTHON_BIN="$2"; shift 2;;
    --skip-fingerprint) INSTALL_FP=0; shift;;
    *) err "unknown option: $1"; exit 2;;
  esac
done

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    err "must run as root (use sudo)"; exit 1
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "missing required command: $1"; exit 1; }
}

detect_arch() {
  local os arch
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  arch=$(uname -m)
  case "$arch" in
    x86_64|amd64) arch=amd64;;
    aarch64|arm64) arch=arm64;;
    *) err "unsupported architecture: $arch"; exit 1;;
  esac
  echo "$os" "$arch"
}

download() {
  # download <url> <outpath>
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    err "need curl or wget to download $url"; exit 1
  fi
}

require_root
require_cmd "$PYTHON_BIN"

# Enforce Python >= 3.10
PYV=$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
case "$PYV" in
  3.10|3.11|3.12|3.13) ;; # allowed minors
  3.1[0-9]) ;;            # future 3.1x
  *) err "Python >= 3.10 required (found $PYV at $PYTHON_BIN)"; exit 1;;
esac

read -r OS ARCH < <(detect_arch)
TMPDIR=$(mktemp -d -t oksi-install.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

APP_DIR="$OKSI_ROOT/sw-licensing"
VENVDIR="$APP_DIR/venv"
MANDIR="$APP_DIR"
BIN_DIR="$PREFIX/bin"
mkdir -p "$APP_DIR" "$BIN_DIR"

log "Installing to root=$OKSI_ROOT prefix=$PREFIX (os=$OS arch=$ARCH)"

# 1) Fetch Python app bundle (tar.gz containing src/sw-licensing and requirements.txt)
PY_TGZ_URL="$BASE_URL/oksi-sw-licensing-python.tar.gz"
PY_TGZ="$TMPDIR/oksi-sw-licensing-python.tar.gz"
log "Downloading licensing app bundle..."
download "$PY_TGZ_URL" "$PY_TGZ" || { err "failed to download $PY_TGZ_URL"; exit 1; }
mkdir -p "$TMPDIR/py"
tar -xzf "$PY_TGZ" -C "$TMPDIR/py"

if [[ ! -d "$TMPDIR/py/sw-licensing" ]]; then
  err "bundle missing sw-licensing/ directory"; exit 1
fi
cp -r "$TMPDIR/py/sw-licensing" "$APP_DIR/app"
if [[ -f "$TMPDIR/py/requirements.txt" ]]; then
  cp "$TMPDIR/py/requirements.txt" "$APP_DIR/requirements.txt"
else
  # fallback: minimal requirements if not provided
  cat > "$APP_DIR/requirements.txt" << 'REQ'
cryptography>=41.0.0
requests>=2.31.0
tomli>=2.0.1; python_version < "3.11"
tomli_w>=1.0.0
REQ
fi

# 2) Create venv and install requirements (isolated from system Python)
log "Creating virtualenv..."
"$PYTHON_BIN" -m venv "$VENVDIR"
"$VENVDIR/bin/python" -m pip install --upgrade pip >/dev/null
log "Installing Python dependencies..."
"$VENVDIR/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null

# 3) Write launcher script for CLI (optional helper)
CLI_SHIM="$BIN_DIR/oksi-sw-license"
cat > "$CLI_SHIM" << EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$APP_DIR/app"
exec "$VENVDIR/bin/python" "$APP_DIR/app/cli.py" "\$@"
EOF
chmod +x "$CLI_SHIM"

# 4) Install fingerprint helper binary
MANIFEST_PATH="$APP_DIR/manifest.txt"
echo "$CLI_SHIM" > "$MANIFEST_PATH"

if [[ "$INSTALL_FP" -eq 1 ]]; then
  FP_URL="$BASE_URL/oksi_fingerprint-${OS}-${ARCH}"
  FP_DST="$BIN_DIR/oksi_fingerprint"
  log "Downloading fingerprint helper..."
  if download "$FP_URL" "$TMPDIR/oksi_fingerprint"; then
    install -m 0755 "$TMPDIR/oksi_fingerprint" "$FP_DST"
    log "Installed $FP_DST"
    echo "$FP_DST" >> "$MANIFEST_PATH"
  else
    err "could not download $FP_URL — continuing without native helper (Python fallback will be used)"
  fi
fi

# 5) Write uninstall script
UNINSTALL="$APP_DIR/uninstall.sh"
cat > "$UNINSTALL" << EOS
#!/usr/bin/env bash
set -euo pipefail
echo "[oksi-uninstall] Removing OKSI Software Licensing..."
if [[ -f "$MANIFEST_PATH" ]]; then
  while IFS= read -r p; do
    if [[ -n "\$p" && -e "\$p" ]]; then
      rm -f "\$p" || true
      echo "[oksi-uninstall] removed \$p"
    fi
  done < "$MANIFEST_PATH"
fi
rm -rf "$APP_DIR"
echo "[oksi-uninstall] done"
EOS
chmod +x "$UNINSTALL"

# Convenience symlink in prefix for uninstall
UNINSTALL_SHIM="$BIN_DIR/oksi-sw-license-uninstall"
ln -sf "$UNINSTALL" "$UNINSTALL_SHIM"
echo "$UNINSTALL_SHIM" >> "$MANIFEST_PATH"

log "Installation complete. Commands available:"
log "  - oksi-sw-license (Python CLI)"
if [[ -x "$BIN_DIR/oksi_fingerprint" ]]; then
  log "  - oksi_fingerprint (native helper)"
fi
log "To uninstall: sudo $UNINSTALL_SHIM"
