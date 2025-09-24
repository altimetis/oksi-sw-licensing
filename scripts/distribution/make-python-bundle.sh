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

tar -czf "$OUT_DIR/oksi-sw-licensing-python.tar.gz" -C "$TMPDIR" .
echo "Wrote $OUT_DIR/oksi-sw-licensing-python.tar.gz"

