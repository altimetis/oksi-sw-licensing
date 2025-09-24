#!/usr/bin/env bash
set -euo pipefail

# Build fingerprint helper for one or more targets and stage into dist/bin
# Cross-compilation is supported for Linux targets when the appropriate
# cross toolchains are installed (e.g., aarch64-linux-gnu-g++, x86_64-linux-gnu-g++).
#
# Usage:
#   # Build for current host only
#   scripts/distribution/make-fingerprint.sh
#
#   # Cross-compile for multiple targets
#   TARGETS="linux-amd64 linux-arm64" scripts/distribution/make-fingerprint.sh
#
# Variables:
#   TARGETS: space-separated list of <os>-<arch> (default: host)
#

ROOT_DIR=$(cd "$(dirname "$0")/../.." && pwd)
OUT_DIR="$ROOT_DIR/dist/bin"
mkdir -p "$OUT_DIR"

host_os=$(uname -s | tr '[:upper:]' '[:lower:]')
host_arch=$(uname -m)
case "$host_arch" in
  x86_64|amd64) host_arch=amd64;;
  aarch64|arm64) host_arch=arm64;;
  *) host_arch="unknown";;
esac

default_target="$host_os-$host_arch"
TARGETS=${TARGETS:-$default_target}

build_one() {
  local os="$1" arch="$2"
  local build_dir="$ROOT_DIR/build/fingerprint-$os-$arch"
  local cflags="-O3"
  local cmake_args=( -S "$ROOT_DIR/src/fingerprint" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release )

  case "$os" in
    linux)
      case "$arch" in
        amd64)
          # Prefer native build if host matches, else cross via x86_64-linux-gnu
          if [[ "$host_os-$host_arch" == "linux-amd64" ]]; then
            : # native build, no extra toolchain args
          else
            if command -v x86_64-linux-gnu-g++ >/dev/null 2>&1; then
              cmake_args+=( -DCMAKE_SYSTEM_NAME=Linux \
                            -DCMAKE_SYSTEM_PROCESSOR=x86_64 \
                            -DCMAKE_C_COMPILER=x86_64-linux-gnu-gcc \
                            -DCMAKE_CXX_COMPILER=x86_64-linux-gnu-g++ )
            else
              echo "[cross] missing x86_64-linux-gnu-g++ toolchain for linux-amd64" >&2; return 1
            fi
          fi
          ;;
        arm64)
          if [[ "$host_os-$host_arch" == "linux-arm64" ]]; then
            :
          else
            if command -v aarch64-linux-gnu-g++ >/dev/null 2>&1; then
              cmake_args+=( -DCMAKE_SYSTEM_NAME=Linux \
                            -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
                            -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
                            -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ )
            else
              echo "[cross] missing aarch64-linux-gnu-g++ toolchain for linux-arm64" >&2; return 1
            fi
          fi
          ;;
        *) echo "Unsupported linux arch: $arch" >&2; return 1;;
      esac
      ;;
    *) echo "Unsupported OS target: $os" >&2; return 1;;
  esac

  echo "[build] $os-$arch -> $build_dir"
  cmake "${cmake_args[@]}" >/dev/null
  cmake --build "$build_dir" --config Release -- -j >/dev/null

  local bin_path="$build_dir/bin/oksi_fingerprint"
  if [[ ! -x "$bin_path" ]]; then
    echo "Build did not produce $bin_path" >&2; return 1
  fi
  local out="$OUT_DIR/oksi_fingerprint-$os-$arch"
  cp "$bin_path" "$out"
  chmod 0755 "$out"
  echo "Wrote $out"
}

status=0
for t in $TARGETS; do
  os=${t%-*}
  arch=${t#*-}
  if ! build_one "$os" "$arch"; then
    status=1
  fi
done

exit $status
