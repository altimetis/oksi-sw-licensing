#!/usr/bin/env bash
set -uo pipefail

# Run verify against the default machine file path, which should be bind-mounted
python scripts/oksi_license_cli.py validate-key
rc=$?

if [ "$rc" -eq 0 ]; then
  echo "License valid"
else
  echo "license invalid"
fi

exit "$rc"
