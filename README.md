# OKSI Software Licensing

Customer-facing CLI and lightweight native helper for machine fingerprinting and license activation against Keygen.

## Install (Customers)

- One-liner:
  - `curl -fsSL https://github.com/altimetis/oksi-sw-licensing/releases/latest/install.sh | sudo bash`
- Installs:
  - CLI shim: `/usr/local/bin/oksi-license`
  - Native helper: `/usr/local/bin/oksi_fingerprint` (if available for your platform)
  - App + venv: `/opt/oksi/licensing`
- Requirements on target machine:
  - Linux with `bash` and `curl` or `wget`
  - Python `>= 3.10` (for creating an isolated virtualenv)
  - Root privileges (to write under `/usr/local` and `/opt`)

## Quick Start

- Login: `oksi-license login`
- Who am I: `oksi-license whoami`
- List products: `oksi-license list-products`
- Activate a machine: `oksi-license activate <PRODUCT_ID>`
- Validate a license key: `oksi-license validate-key <KEY>`
- Deactivate the machine: `oksi-license deactivate <PRODUCT_ID>`

## Uninstall

- `sudo /usr/local/bin/oksi-sw-licensing-uninstall`

## Configuration

- Global flags:
  - `--base-url` (default `https://api.keygen.sh`)
  - `--account-id` (your Keygen Account ID)
  - `--api-token` (overrides other token sources)
  - `--interactive` (REPL mode)
- Token precedence (highest → lowest):
  - `--api-token` flag
  - env `OKSI_API_TOKEN`
  - token file (default `./.oksi/api_token`; override path via `OKSI_API_TOKEN_FILE`)
  - config file `~/.oksi/license-cli.toml`
- Files written:
  - Token file: `./.oksi/api_token`
  - License key: `.oksi/license.<PRODUCT_ID>.key` (0600 when possible)
  - REPL history: `~/.oksi/oksi-license.history`

## Fingerprinting

- Prefers native helper if present in PATH: `oksi_fingerprint`
- Fallback: Python implementation in `src/sw-licensing/fingerprint.py`
- Deterministic input: Linux `/etc/machine-id`; optional salt for scoping
- Override per command: `--fingerprint <value>`

## From Source (Developers)

- Setup:
  - `python -m venv .venv && . .venv/bin/activate`
  - `pip install -r requirements.txt`
- Run CLI directly:
  - `python src/sw-licensing/cli.py --help`
  - or `python -m sw-licensing.cli --help` (ensure `src` is on `PYTHONPATH`)
- Build native fingerprint helper (optional):
  - Manual (host build):
    - `cmake -S src/fingerprint -B build -DCMAKE_BUILD_TYPE=Release`
    - `cmake --build build --config Release`
    - Output: `build/bin/oksi_fingerprint`
  - Scripted (host or cross):
    - Host only: `bash scripts/distribution/make-fingerprint.sh`
    - Cross-compile (Linux): `TARGETS="linux-amd64 linux-arm64" bash scripts/distribution/make-fingerprint.sh`
    - Requirements for cross: `x86_64-linux-gnu-g++` and/or `aarch64-linux-gnu-g++`
    - Outputs: `dist/bin/oksi_fingerprint-<os>-<arch>`

## Repo Layout

- CLI: `src/sw-licensing/cli.py`
- Python fingerprint fallback: `src/sw-licensing/fingerprint.py`
- Crypto helpers: `src/sw-licensing/keygen_crypto.py`
- Native helper (C++): `src/fingerprint/fingerprint.cpp`
- Distribution tooling: `scripts/distribution/`
  - Installer: `scripts/distribution/install.sh`
  - Uninstaller: `scripts/distribution/uninstall.sh`
  - Bundlers: `scripts/distribution/make-python-bundle.sh`, `scripts/distribution/make-fingerprint.sh`
  - Makefile helpers: `make dist-fingerprint TARGETS="linux-amd64 linux-arm64"`, `make dist-python`, `make release-stage`

## Keygen Setup Notes

- Account ID: obtain from your Keygen dashboard
- Create product(s) and license pool(s) with machine activation policy
- API token: user token (via CLI `login`) or customer token
- HTTP response signing (recommended):
  - The CLI verifies signature using an Ed25519 public key
  - Update `DEFAULT_KEYGEN_PUBKEY` in `src/sw-licensing/cli.py` if your account key differs
  - If self-hosting, set `--base-url`; host is enforced during signature checks

## Docker (Optional)

- Activation convenience script: `run-activate.sh`
- Verification convenience script: `run-oksi-sw.sh`
- Both mount `/etc/machine-id` (read-only) and `./.oksi` for tokens/keys

## Troubleshooting

- Signature verification failed:
  - Ensure `--base-url` matches your Keygen domain
  - Update `DEFAULT_KEYGEN_PUBKEY` in `src/sw-licensing/cli.py`
- Auth errors:
  - Pass `--api-token` explicitly to rule out precedence issues
  - Check `./.oksi/api_token` and `~/.oksi/license-cli.toml`
- Pool exhausted:
  - Add licenses or deactivate existing machine activations for the product

## GitHub Releases

- Prerequisites:
  - Install GitHub CLI (`gh`) and authenticate: `gh auth login`

- Build artifacts:
  - `make dist-python`
  - `make dist-fingerprint TARGETS="linux-amd64 linux-arm64"` (optional cross-compile)

- Create tag and release (uploads artifacts):
  - `make gh-release VERSION=v0.1.0`
  - This will:
    - Create/push the Git tag `v0.1.0` if it does not exist
    - Create a GitHub Release and upload: `install.sh`, `uninstall.sh`, the Python bundle, and any built fingerprint binaries
    - Mark the release as “latest”

- Latest download base URL (for installers):
  - `GH_BASE="https://github.com/<owner>/<repo>/releases/latest/download"`
  - Example install from GitHub Releases:
    - `curl -fsSL "$GH_BASE/install.sh" | sudo OKSI_DOWNLOAD_BASE="$GH_BASE" bash`

- Asset layout:
  - Python bundle: `$BASE/oksi-sw-licensing-python.tar.gz`
  - Fingerprint binaries: `$BASE/oksi_fingerprint-<os>-<arch>`
