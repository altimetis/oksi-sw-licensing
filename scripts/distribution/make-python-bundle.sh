#!/usr/bin/env bash
set -euo pipefail

# Package the Python licensing app into a tarball suitable for install.sh

ROOT_DIR=$(cd "$(dirname "$0")/../.." && pwd)
OUT_DIR="$ROOT_DIR/dist"
mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

if [[ ! -d src/sw-licensing ]]; then
  echo "src/sw-licensing not found" >&2; exit 1
fi

TMPDIR=$(mktemp -d -t oksi-pybundle.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/sw-licensing"
cp -r src/sw-licensing/*.py "$TMPDIR/sw-licensing/"
if [[ -f requirements.txt ]]; then
  cp requirements.txt "$TMPDIR/requirements.txt"
fi

VERSION_VALUE="X.X.X"
if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  VERSION_VALUE=$(git -C "$ROOT_DIR" describe --tags --dirty --always 2>/dev/null || echo "X.X.X")
elif [[ -f "$ROOT_DIR/VERSION" ]]; then
  VERSION_VALUE=$(tr -d '\r' < "$ROOT_DIR/VERSION" | head -n 1)
fi
printf '%s\n' "$VERSION_VALUE" > "$TMPDIR/sw-licensing/VERSION"

tar -czf "$OUT_DIR/oksi-sw-licensing-python.tar.gz" -C "$TMPDIR" .
echo "Wrote $OUT_DIR/oksi-sw-licensing-python.tar.gz"

