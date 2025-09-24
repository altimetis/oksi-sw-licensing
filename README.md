# OKSI Software Licensing

Customer‑facing CLI and lightweight native helper for machine fingerprinting and license activation against Keygen.

**Repo Points**
- CLI: `scripts/oksi_license_cli.py`
- Fingerprint helper (C++): `src/fingerprint.cpp`
- CMake target: `CMakeLists.txt`
- Python fingerprint fallback: `scripts/fingerprint.py`

**Requirements**
- Python 3.10+ (CLI)
- C++17 toolchain + CMake 3.15+ (optional, native fingerprint helper)

Install Python deps:
- `python -m pip install -r requirements.txt`

**Keygen Setup**
- Account ID: obtain from your Keygen dashboard.
- Product(s): create a product and note its Product ID.
- Licenses: create license(s)/pool for the product and ensure the policy allows machine activations.
- API token: either a user token (via CLI login) or a customer token from dashboard.
- HTTP response signing (recommended):
  - The CLI verifies response signatures using an Ed25519 public key.
  - Update `DEFAULT_KEYGEN_PUBKEY` in `scripts/oksi_license_cli.py` with your account’s public key if different.
  - If self‑hosting, set `--base-url` to your Keygen domain; host is enforced during signature checks (`scripts/keygen_crypto.py`).

**Build Native Fingerprint Helper (optional)**
- Configure + build:
  - `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`
  - `cmake --build build --config Release`
- Binary: `build/bin/oksi_fingerprint`
- Install to PATH (optional): `cmake --install build --prefix ~/.local`
- Usage:
  - `build/bin/oksi_fingerprint`
  - `build/bin/oksi_fingerprint --salt <scope-or-product>`
- The Python CLI prefers this binary when present in PATH or next to the scripts (`scripts/fingerprint.py`).

**CLI Overview**
- Entry: `python scripts/oksi_license_cli.py [GLOBAL FLAGS] <command> [ARGS]`
- Globals:
  - `--base-url` (default `https://api.keygen.sh`)
  - `--account-id` (set to your Account ID)
  - `--api-token` (overrides other token sources)
  - `--interactive` (REPL mode)
- Token precedence (highest → lowest):
  - `--api-token` flag
  - env `OKSI_API_TOKEN`
  - token file (default `./.oksi/api_token`; override path via `OKSI_API_TOKEN_FILE`)
  - config file `~/.oksi/license-cli.toml`

**Subcommands**
- `login` — obtain and save a user token
  - `python scripts/oksi_license_cli.py login --email you@example.com --password-stdin < secret.txt`
- `logout` — forget saved token
  - `python scripts/oksi_license_cli.py logout`
- `whoami` — show authenticated identity
  - `python scripts/oksi_license_cli.py whoami`
- `list-products` — list products (name and id)
  - `python scripts/oksi_license_cli.py list-products`
- `status` — summarize license pool counts by product
  - `python scripts/oksi_license_cli.py status`
- `activate <product_id>` — claim an unactivated license for this machine
  - `python scripts/oksi_license_cli.py activate <PRODUCT_ID>`
  - Writes plaintext key to `.oksi/license.<PRODUCT_ID>.key` by default; override with `--license-key-file`.
  - Fingerprint override: `--fingerprint <value>`.
- `deactivate <product_id>` — release this machine from the product
  - `python scripts/oksi_license_cli.py deactivate <PRODUCT_ID>`
  - Fingerprint override: `--fingerprint <value>`.
- `validate-key <LICENSE_KEY>` — online validation scoped to this machine
  - `python scripts/oksi_license_cli.py validate-key <KEY>`
  - Fingerprint override: `--fingerprint <value>`.

**Interactive Mode (REPL)**
- Start: `python scripts/oksi_license_cli.py --interactive`
- Commands: `login`, `whoami`, `list-products`, `status`, `activate`, `deactivate`, `validate-key`.
- History is persisted to `~/.oksi/oksi-license.history`.

**Fingerprinting**
- Default behavior: use native helper if available; otherwise Python fallback (`scripts/fingerprint.py`).
- Deterministic input: Linux `/etc/machine-id`; optional `--salt` for scoping (`src/fingerprint.cpp`).
- Override fingerprint per command with `--fingerprint`.

**Files Created**
- Token file: `./.oksi/api_token` by default (set by `login` or manually) (`scripts/oksi_license_cli.py`).
- License key file: `.oksi/license.<PRODUCT_ID>.key` on `activate` (permissions 0600 when possible).

**Docker (optional)**
- Interactive activation image: `docker/activate/Dockerfile:1`
  - Convenience script: `./run-activate.sh`
  - Example: `./run-activate.sh --interactive`
- Verification image: `docker/verify/Dockerfile`
  - Convenience script: `./run-oksi-sw.sh`
  - Example: `./run-oksi-sw.sh validate-key <KEY>`
- Both scripts mount `/etc/machine-id` (read‑only) and `./.oksi` for tokens/keys.

**Troubleshooting**
- Signature verification failed:
  - Ensure `--base-url` matches your Keygen domain.
  - Update `DEFAULT_KEYGEN_PUBKEY` in `scripts/oksi_license_cli.py` to your account’s HTTP signing public key.
- Auth errors:
  - Pass `--api-token` explicitly to rule out precedence issues.
  - Check `./.oksi/api_token` and `~/.oksi/license-cli.toml`.
- Pool exhausted:
  - Add licenses or deactivate existing machine activations for the product.

**Notes**
- The CLI verifies HTTP responses with `verify_http_response_signature` (`scripts/keygen_crypto.py`).
- The native fingerprint helper is deterministic and avoids intrusive identifiers; see `src/fingerprint.cpp`.
