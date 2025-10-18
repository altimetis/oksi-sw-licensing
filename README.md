# OKSI Software Licensing

OKSI Software Licensing is a customer CLI and optional native helper that lets you register, activate, and audit machines against OKSI products backed by Keygen.

## Before You Install

- Linux host with `bash` and either `curl` or `wget`
- Python `>= 3.10` (used to create an isolated virtual environment)
- Root privileges to write under `/usr/local` and `/opt`

## Install

- Recommended one-liner: `curl -fsSL https://github.com/altimetis/oksi-sw-licensing/releases/latest/download/install.sh | sudo bash`
- Installs:
  - CLI shim `oksi-sw-license` at `/usr/local/bin`
  - Native helper `oksi_fingerprint` at `/usr/local/bin` (if a build exists for your platform)
  - Application and virtualenv under `/opt/oksi/licensing`

## First Run Checklist

- Confirm install: `oksi-sw-license --version`
- Log in with your user credentials: `oksi-sw-license login`
- List available products: `oksi-sw-license list-products`
- Activate the current machine: `oksi-sw-license activate <PRODUCT_ID>`

## Everyday Commands

- Check current identity: `oksi-sw-license whoami`
- Validate a license key without activating: `oksi-sw-license validate-key <KEY>`
- Deactivate this machine when repurposing hardware: `oksi-sw-license deactivate <PRODUCT_ID>`

## Configuration and Tokens

- Global flags:
  - `--base-url` (defaults to `https://api.keygen.sh`)
  - `--account-id` (your Keygen Account ID)
  - `--api-token` (overrides other token sources)
  - `--interactive` (launches REPL mode)
- Token lookup order (highest to lowest):
  - `--api-token`
  - Environment variable `OKSI_API_TOKEN`
  - Token file `./.oksi/api_token` (override via `OKSI_API_TOKEN_FILE`)
  - Config file `~/.oksi/sw-license-cli.toml`
- Files created by the CLI:
  - Token cache `./.oksi/api_token`
  - License key file `.oksi/license.<PRODUCT_ID>.key` (written with mode 0600 when possible)
  - REPL history `~/.oksi/sw-license.history`

## Machine Fingerprints

- The CLI uses the native helper `oksi_fingerprint` when available in `PATH`
- Falls back to the Python implementation at `src/sw-licensing/fingerprint.py`
- Fingerprints are derived from `/etc/machine-id` with an optional salt for scoping
- Override per command with `--fingerprint <value>`

## Uninstall

- Remove all installed components: `sudo /usr/local/bin/oksi-sw-license-uninstall`

## Troubleshooting

- Signature verification failed:
  - Ensure `--base-url` matches your Keygen domain
  - Update `DEFAULT_KEYGEN_PUBKEY` in `src/sw-licensing/cli.py` if your account public key changed
- Authentication errors:
  - Pass `--api-token` explicitly to confirm credential precedence
  - Check `./.oksi/api_token` and `~/.oksi/sw-license-cli.toml`
- Pool exhausted:
  - Add licenses or deactivate an existing machine for the product

## Developer Guide

### Local Setup

- Create a virtual environment: `python -m venv .venv && . .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Run the CLI directly:
  - `python src/sw-licensing/cli.py --help`
  - `python -m sw-licensing.cli --help` (ensure `src` is on `PYTHONPATH`)

### Repository Tour

- CLI entry point: `src/sw-licensing/cli.py`
- Python fingerprint fallback: `src/sw-licensing/fingerprint.py`
- Crypto helpers: `src/sw-licensing/keygen_crypto.py`
- Native helper (C++): `src/fingerprint/fingerprint.cpp`
- Distribution tooling: `scripts/distribution/`

### Building the Native Fingerprint Helper

- Manual build:
  - `cmake -S src/fingerprint -B build -DCMAKE_BUILD_TYPE=Release`
  - `cmake --build build --config Release`
  - Output binary at `build/bin/oksi_fingerprint`
- Scripted build:
  - Host build: `bash scripts/distribution/make-fingerprint.sh`
  - Cross-compile (Linux): `TARGETS="linux-amd64 linux-arm64" bash scripts/distribution/make-fingerprint.sh`
  - Cross requirements: `x86_64-linux-gnu-g++` and/or `aarch64-linux-gnu-g++`
  - Outputs under `dist/bin/oksi_fingerprint-<os>-<arch>`

### GitHub Releases

- Prerequisite: authenticate `gh` with `gh auth login`
- Build artifacts:
  - `make dist-python`
  - `make dist-fingerprint TARGETS="linux-amd64 linux-arm64"`
- Publish release: `make gh-release VERSION=v0.1.0`
  - Creates and pushes the Git tag if missing
  - Uploads installer, uninstaller, Python bundle, and any fingerprint binaries
  - Marks the release as latest
- Latest download base URL:
  - `GH_BASE="https://github.com/<owner>/<repo>/releases/latest/download"`
  - Example install: `curl -fsSL "$GH_BASE/install.sh" | sudo OKSI_DOWNLOAD_BASE="$GH_BASE" bash`
- Release asset layout:
  - Python bundle `oksi-sw-licensing-python.tar.gz`
  - Fingerprint binaries `oksi_fingerprint-<os>-<arch>`

### Docker Helpers

- Activation helper: `run-activate.sh`
- Verification helper: `run-oksi-sw.sh`
- Both mount `/etc/machine-id` (read-only) and `./.oksi` for tokens and license keys

### Keygen Setup Notes

- Retrieve your Keygen Account ID from the Keygen dashboard
- Create product(s) and machine-activation license pools
- Update `DEFAULT_KEYGEN_PUBKEY` and `DEFAULT_KEYGEN_PUBKEY` if they are different
- When self-hosting Keygen, pass a custom `--base-url`; the host is verified during signature checks
