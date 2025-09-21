#!/usr/bin/env bash
set -euo pipefail

# Ensure token directory exists on host so it can be mounted
mkdir -p ./.oksi

# Allow overriding image via env var IMAGE, default to requested image
IMAGE="${IMAGE:-oksi/sw-license-verify:latest}"

# Require /etc/machine-id on the host
if [[ ! -f /etc/machine-id ]]; then
  echo "[error] /etc/machine-id not found on host. This script requires it to compute the machine fingerprint." >&2
  exit 1
fi

# Run the container with required mounts
exec docker run --rm \
  -v /etc/machine-id:/etc/machine-id:ro \
  -v ./.oksi:/app/.oksi \
  "$IMAGE" "$@"
