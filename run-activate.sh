#!/usr/bin/env bash
set -euo pipefail

# Ensure token directory exists on host so it can be mounted
mkdir -p ./.oksi

# Allow overriding image via env var IMAGE, default to requested image
IMAGE="${IMAGE:-oksi/sw-license-activate:latest}"

# Require /etc/machine-id on the host
if [[ ! -f /etc/machine-id ]]; then
  echo "[error] /etc/machine-id not found on host. This script requires it to compute the machine fingerprint." >&2
  exit 1
fi

# Run the container in interactive mode with the token volume mounted
exec docker run --rm -it \
  -v /etc/machine-id:/etc/machine-id:ro \
  -v ./.oksi:/app/.oksi \
  "$IMAGE" "$@"

