#!/usr/bin/env python3
"""
OKSI Software License CLI (customer-facing)

Features
- login: obtain and store a user token from email/password (stores token in a file in the current directory for Docker access).
- logout: remove any stored token (file and config).
- whoami: display the authenticated identity.
- status: fetch license pool pages and summarize totals (valid/invalid).
- activate: fingerprint this machine, consume an unactivated license, and write the license key to a file.
- deactivate: deactivate this machine's activation.
- validate-key: online validation of a license key for this machine's fingerprint.

Environment / Config
- API token precedence:
  1) `--api-token` CLI flag
  2) env `OKSI_API_TOKEN`
  3) token file (default: `./.oksi/api_token`, override path with `OKSI_API_TOKEN_FILE`)
  4) config file `~/.oksi/license-cli.toml` (key = `api_token`)
- Defaults: license key file `.oksi/license.key`.
- Fingerprint: pass `--fingerprint` to override; otherwise auto-detected.
- Requires Python 3.10+
"""

from __future__ import annotations
from fingerprint import generate_fingerprint
from keygen_crypto import verify_http_response_signature

import argparse
import atexit
import shlex
import dataclasses
import functools
import getpass
import json
import datetime
import os
import pathlib
try:
    import readline  # builtin on Unix; provides in-process line editing/history
except Exception:  # pragma: no cover - Windows or minimal Python builds
    try:
        # Windows-compatible readline implementation
        import pyreadline3 as readline  # type: ignore
    except Exception:
        class _NoReadline:
            def read_history_file(self, *a, **kw):
                pass
            def write_history_file(self, *a, **kw):
                pass
            def set_history_length(self, *a, **kw):
                pass
            def parse_and_bind(self, *a, **kw):
                pass
            def add_history(self, *a, **kw):
                pass
            def get_current_history_length(self):
                return 0
            def get_history_item(self, *a, **kw):
                return None
        readline = _NoReadline()  # type: ignore
import platform
import sys
import time
import typing as t

import requests
from urllib.parse import urlparse, unquote, urljoin

# ----------------------------
# Constants & Simple Utilities
# ----------------------------

DEFAULT_BASE_URL = "https://api.keygen.sh"         # adjust if self-hosting
DEFAULT_ACCOUNT_ID = "b4ddeca5-0b33-485f-94bb-20c229fecd44"
DEFAULT_KEYGEN_PUBKEY = "89d96e37fe21302d0a8ff8f9c2509f480ec6c6f28ec9645514a4043e3b29142b"

# Persistent interactive history
HISTORY_FILE = pathlib.Path.home() / ".oksi" / "oksi-license.history"
CONFIG_PATH = pathlib.Path.home() / ".oksi" / "license-cli.toml"
USER_AGENT = "OKSI-License-CLI/1.0 (+https://oksi.ai)"

# File-based token path (cwd by default)
DEFAULT_TOKEN_FILE = (pathlib.Path(os.getenv("OKSI_API_TOKEN_FILE"))
                      if os.getenv("OKSI_API_TOKEN_FILE")
                      else (pathlib.Path.cwd() / ".oksi" / "api_token"))

# License key file resolver: use filename license.<product_id>.key under the given base path
def resolve_license_key_file_path(license_key_file: str | None, product_id: str) -> pathlib.Path:
    if not license_key_file:
        return (pathlib.Path.cwd() / ".oksi" / f"license.{product_id}.key")
    return pathlib.Path(license_key_file)

# ------------
# Exceptions
# ------------

class LicenseError(Exception):
    """Generic licensing failure."""

class AuthError(LicenseError):
    """Authentication / authorization problems."""

class PoolExhaustedError(LicenseError):
    """No remaining activations in pool."""

class NetworkError(LicenseError):
    """Transient network or server issues."""

# -----------------------
# Config (token storage)
# -----------------------

@dataclasses.dataclass
class Config:
    api_token: str | None = None
    base_url: str = DEFAULT_BASE_URL
    account_id: str = DEFAULT_ACCOUNT_ID
    token_file: pathlib.Path = DEFAULT_TOKEN_FILE

    # Service identifier no longer used; kept minimal config

    @staticmethod
    def load() -> "Config":
        cfg = Config()
        # 1) env
        env_token = os.getenv("OKSI_API_TOKEN")
        if env_token:
            cfg.api_token = env_token

        # token file override via env (path)
        token_file_env = os.getenv("OKSI_API_TOKEN_FILE")
        if token_file_env:
            cfg.token_file = pathlib.Path(token_file_env)

        # 2) toml file (for non-token settings)
        if CONFIG_PATH.exists():
            try:
                import tomllib  # py311+; use 'tomli' if older
            except Exception:
                import tomli as tomllib  # type: ignore
            text = CONFIG_PATH.read_bytes()
            try:
                data = tomllib.loads(text.decode("utf-8"))
            except Exception:
                data = {}
            cfg.api_token = cfg.api_token or data.get("api_token")
            cfg.base_url = data.get("base_url", cfg.base_url)
            cfg.account_id = data.get("account_id", cfg.account_id)

        return cfg

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            import tomli_w  # pip install tomli-w
        except Exception as exc:
            raise RuntimeError("tomli-w is required to write config: pip install tomli-w") from exc
        doc = {
            "api_token": self.api_token,
            "base_url": self.base_url,
            "account_id": self.account_id,
        }
        CONFIG_PATH.write_bytes(tomli_w.dumps(doc).encode("utf-8"))

    # --- Token storage helpers ---
    def load_api_token(self) -> str | None:
        # precedence: existing cfg.api_token (CLI/env/config) > token file
        if self.api_token:
            return self.api_token
        try:
            if self.token_file.exists():
                tok = self.token_file.read_text(encoding="utf-8").strip()
                if tok:
                    self.api_token = tok
                    return tok
        except Exception:
            pass
        return None

    def save_api_token(self, token: str) -> None:
        # Persist token to repo-local file for Docker accessibility
        self.api_token = token
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(token, encoding="utf-8")
            try:
                os.chmod(self.token_file, 0o600)
            except Exception:
                pass  # best-effort permissions
        except Exception as exc:
            raise RuntimeError(f"failed to write api token file at {self.token_file}: {exc}")

    def clear_api_token(self) -> None:
        self.api_token = None
        try:
            if self.token_file.exists():
                self.token_file.unlink()
        except Exception:
            pass
        # also clear from config file if present (backward compatibility)
        if CONFIG_PATH.exists():
            try:
                import tomllib  # py311+
            except Exception:
                import tomli as tomllib  # type: ignore
            try:
                data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            data.pop("api_token", None)
            try:
                import tomli_w
            except Exception as exc:
                raise RuntimeError("tomli-w is required to write config: pip install tomli-w") from exc
            CONFIG_PATH.write_bytes(tomli_w.dumps(data).encode("utf-8"))

# ----------------------
# HTTP (with retries)
# ----------------------

def with_retries(fn: t.Callable[..., requests.Response]) -> t.Callable[..., requests.Response]:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc = None
        for i in range(4):
            try:
                resp = fn(*args, **kwargs)
                # Retry on 5xx and some 429s
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise NetworkError(f"Server busy ({resp.status_code}): {resp.text[:200]}")
                return resp
            except (requests.RequestException, NetworkError) as exc:
                last_exc = exc
                time.sleep(0.6 * (2 ** i))
        if last_exc:
            raise NetworkError(str(last_exc))
    return wrapper

# ----------------------
# Keygen API Client
# ----------------------

class KeygenClient:
    """
    Minimal wrapper. Replace placeholder endpoints with your real ones.
    Token is a customer-scoped API token (created in their portal) OR a User Token (login).
    """

    def __init__(self, cfg: Config, api_token: str):
        self.cfg = cfg
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "User-Agent": USER_AGENT,
        })
        if api_token:
            self.session.headers["Authorization"] = f"Bearer {api_token}"

    @with_retries
    def _post(self, path: str, payload: dict) -> requests.Response:
        url = f"{self.cfg.base_url}/v1/accounts/{self.cfg.account_id}{path}"
        resp = self.session.post(url, data=json.dumps(payload), timeout=20)
        try:
            host = urlparse(self.cfg.base_url).netloc or "api.keygen.sh"
            uri = unquote(resp.raw.url)
            verify_http_response_signature(
                resp,
                uri=uri,
                public_key_hex=DEFAULT_KEYGEN_PUBKEY,
                host=host,
                method="post",
            )
        except Exception as exc:
            raise LicenseError(f"HTTP response signature verification failed: {exc}")
        return resp

    @with_retries
    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.cfg.base_url}/v1/accounts/{self.cfg.account_id}{path}"
        resp = self.session.get(url, params=params or {}, timeout=20)
        try:
            host = urlparse(self.cfg.base_url).netloc or "api.keygen.sh"
            uri = unquote(resp.raw.url)
            verify_http_response_signature(
                resp,
                uri=uri,
                public_key_hex=DEFAULT_KEYGEN_PUBKEY,
                host=host,
                method="get",
            )
        except Exception as exc:
            raise LicenseError(f"HTTP response signature verification failed: {exc}")
        return resp

    def paginate_each(
        self,
        path: str,
        params: dict | None,
        page_size: int,
        page_number: int,
        max_pages: int,
        all_pages: bool,
        on_page: t.Callable[[dict, int], t.Optional[bool]],
    ) -> int:
        """
        Iterate through JSON:API pages and invoke `on_page` for each response.

        - Does not aggregate results; callback receives the raw payload per page.
        - Uses `links.next` exclusively to advance to subsequent pages.
        - Stops when `max_pages` reached (unless `all_pages`), when `links.next` is
          missing/null, or when `on_page` returns a falsy value to signal stop.

        Returns the number of pages processed.
        """
        params = dict(params or {})
        params["page[size]"] = max(1, int(page_size))
        params["page[number]"] = max(1, int(page_number))
        limit = (10**9) if all_pages else max(1, int(max_pages))

        pages = 0
        next_absolute_url: str | None = None

        while pages < limit:
            # Fetch next page
            if next_absolute_url:
                r = self.session.get(next_absolute_url, timeout=20)
                if r.status_code == 401:
                    raise AuthError("Not authorized.")
                if r.status_code != 200:
                    raise LicenseError(f"Request failed ({r.status_code}): {r.text[:200]}")
                # Verify response signature (mirror _get)
                try:
                    host = urlparse(self.cfg.base_url).netloc or "api.keygen.sh"
                    uri = unquote(r.raw.url)
                    verify_http_response_signature(
                        r,
                        uri=uri,
                        public_key_hex=DEFAULT_KEYGEN_PUBKEY,
                        host=host,
                        method="get",
                    )
                except Exception as exc:
                    raise LicenseError(f"HTTP response signature verification failed: {exc}")
            else:
                r = self._get(path, params=params)
                if r.status_code == 401:
                    raise AuthError("Not authorized.")
                if r.status_code != 200:
                    raise LicenseError(f"Request failed ({r.status_code}): {r.text[:200]}")

            payload = r.json()

            pages += 1
            cont = on_page(payload, pages)
            if cont is False:
                break

            # Determine next page source via links
            next_link = (payload.get("links") or {}).get("next") or None
            if not next_link:
                break
            # Resolve relative links against base_url
            if next_link.startswith("http://") or next_link.startswith("https://"):
                next_absolute_url = next_link
            else:
                base = self.cfg.base_url.rstrip('/') + '/'
                next_absolute_url = urljoin(base, next_link.lstrip('/'))

    # ---- Login: user/password -> token (adjust to your deployment) ----
    def login_with_credentials(self, email: str, password: str) -> str:
        """
        Exchange user credentials for a bearer token.
        """
        auth = (email, password)

        # Use a temporary header set without Authorization
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "User-Agent": USER_AGENT,
        }
        url = f"{self.cfg.base_url}/v1/accounts/{self.cfg.account_id}/tokens"
        r = requests.post(url, auth=auth, headers=headers, timeout=20)

        if r.status_code in (401, 403):
            raise AuthError("Invalid credentials.")
        if r.status_code not in (200, 201):
            raise LicenseError(f"Login failed ({r.status_code}): {r.text[:200]}")

        data = r.json()
        # Adapt extraction to your response format:
        token = (
            data.get("data", {})
                .get("attributes", {})
                .get("token")
        ) or data.get("meta", {}).get("token")

        if not token:
            raise LicenseError("Login response did not include a token.")

        return token

    def whoami(self) -> dict:
        r = self._get("/me")
        if r.status_code == 401:
            raise AuthError("Invalid API token.")
        return r.json()

    def get_machines(self, fingerprint: str, product_id: str) -> dict | None:
        params: dict[str, str] = {
            "fingerprint": fingerprint,
            "product": product_id,
            "limit": "1"
            }
        r = self._get("/machines", params=params)
        if r.status_code == 401:
            raise AuthError("Invalid API token.")
        if r.status_code != 200:
            raise LicenseError(f"Request failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    def retrieve_machine(self, fingerprint: str) -> dict | None:
        """Retrieve machine details by fingerprint. Returns None if not found (404)."""
        r = self._get(f"/machines/{fingerprint}")
        if r.status_code == 401:
            raise AuthError("Invalid API token.")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise LicenseError(f"Request failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    def get_unactivated_license(self, product_id: str | None = None) -> dict | None:
        """
        Return the first license that appears unactivated (no machines attached).

        Optionally scope the search to a specific product by `product_id`.
        """
        params: dict[str, str] = {"activations[eq]": "0", "limit": "1"}
        if product_id:
            # Filter by product relationship if provided
            params["product"] = product_id
        r = self._get("/licenses", params=params)
        if r.status_code == 401:
            raise AuthError("Invalid API token.")
        if r.status_code not in (200, 201):
            raise LicenseError(f"Request failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    def activate(self, fingerprint: str, license_id: str, metadata: dict | None = None) -> dict:
        """
        Activate this machine (by fingerprint) against the given license ID.
        """
        payload = {
            "data": {
                "type": "machines",
                "attributes": {
                    "fingerprint": fingerprint,
                    "metadata": metadata or {},
                },
                "relationships": {
                    "license": {
                        "data": { "type": "licenses", "id": license_id }
                    }
                }
            }
        }
        r = self._post("/machines", payload)
        if r.status_code == 401:
            raise AuthError("Token lacks activation rights.")
        if r.status_code == 402:
            raise PoolExhaustedError("No remaining activations.")
        if r.status_code not in (200, 201):
            raise LicenseError(f"Activation failed ({r.status_code}): {r.text[:500]}")
        return r.json()

    def deactivate(self, machine_id: str) -> None:
        r = self.session.delete(
            f"{self.cfg.base_url}/v1/accounts/{self.cfg.account_id}/machines/{machine_id}",
            timeout=20,
        )
        if r.status_code == 401:
            raise AuthError("Token lacks permission to deactivate.")
        if r.status_code not in (200, 202, 204):
            raise LicenseError(f"Deactivate failed ({r.status_code}): {r.text[:500]}")

# ------------------------
# CLI Commands
# ------------------------

def cmd_login(cfg: Config, client: KeygenClient, args: argparse.Namespace) -> int:
    email = args.email or input("Email: ").strip()

    # Choose password source: flag > stdin > env > prompt
    if args.password and args.password_stdin:
        print("[error] specify only one of --password or --password-stdin", file=sys.stderr)
        return 2

    if args.password:
        password = args.password
    elif args.password_stdin:
        # Read entire stdin (trim trailing newline)
        password = sys.stdin.read().rstrip("\n\r")
        if not password:
            print("[error] empty password from stdin", file=sys.stderr)
            return 2
    else:
        password = os.getenv("KEYGEN_PASSWORD") or getpass.getpass("Password: ")

    token = client.login_with_credentials(email=email, password=password)
    cfg.save_api_token(token)
    print("[info] login successful; token saved")
    return 0

def cmd_logout(cfg: Config, _client: KeygenClient, _args: argparse.Namespace) -> int:
    cfg.clear_api_token()
    print("[info] logged out; token removed")
    return 0

def cmd_whoami(client: KeygenClient, _args: argparse.Namespace) -> int:
    payload = client.whoami()
    attrs = (payload.get("data") or {}).get("attributes") or {}
    full_name = (
        attrs.get("fullName")
        or " ".join(x for x in [attrs.get("firstName"), attrs.get("lastName")] if x)
        or "(unknown)"
    )
    email = attrs.get("email") or "(unknown)"
    print(f"{full_name} <{email}>")
    return 0

def cmd_list_products(client: KeygenClient, _args: argparse.Namespace) -> int:
    print("Name (id)")
    def on_page(payload: dict, _page_idx: int) -> bool:
        items = payload.get("data", []) if isinstance(payload, dict) else []
        for it in items:
            pid = it.get("id")
            name = (it.get("attributes", {}) or {}).get("name")
            print(f"{name}\t({pid})")
        return True
    client.paginate_each(
        path="/products",
        params={},
        page_size=100,
        page_number=1,
        max_pages=10**9,
        all_pages=True,
        on_page=on_page,
    )
    return 0

def cmd_status(client: KeygenClient, args: argparse.Namespace) -> int:
    def parse_expiry(exp: str | None) -> datetime.datetime | None:
        if not exp:
            return None
        try:
            # Support "Z" suffix and timezone-aware parsing
            iso = exp.replace("Z", "+00:00")
            return datetime.datetime.fromisoformat(iso)
        except Exception:
            return None

    def is_active_license(item: dict) -> bool:
        attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
        status = str(attrs.get("status", "")).upper()
        suspended = bool(attrs.get("suspended", False))
        expiry_dt = parse_expiry(attrs.get("expiry"))
        now = datetime.datetime.now(datetime.timezone.utc)
        if expiry_dt is not None and expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=datetime.timezone.utc)
        not_expired = (expiry_dt is None) or (expiry_dt > now)
        activated = item.get("relationships", {}).get("machines", {}).get("meta", {}).get("count", 0) > 0
        return (status == "ACTIVE") and (not suspended) and not_expired and activated

    total = 0
    activated_total = 0

    # Per-product tallies
    # structure: { product_id: { 'total': int, 'activated': int } }
    per_product: dict[str, dict[str, int]] = {}

    def on_page(payload: dict, _page_idx: int) -> bool:
        nonlocal total, activated_total
        items = payload.get("data", []) if isinstance(payload, dict) else []
        for it in items:
            total += 1
            rel = (it.get("relationships") or {}).get("product") or {}
            pid = ((rel.get("data") or {}) or {}).get("id")
            # Ensure a product bucket exists
            if pid:
                bucket = per_product.setdefault(pid, {"total": 0, "activated": 0})
                bucket["total"] += 1
            # Count activated license if it meets criteria
            if is_active_license(it):
                activated_total += 1
                if pid:
                    per_product[pid]["activated"] += 1
        return True

    client.paginate_each(
        path="/licenses",
        params={},
        page_size=50,
        page_number=1,
        max_pages=10**9,
        all_pages=True,
        on_page=on_page,
    )

    # Print per-product breakdown (by product ID)
    if per_product:
        print("[info] licenses by product:")
        for pid in sorted(per_product.keys()):
            data = per_product[pid]
            tot = int(data.get("total", 0))
            act = int(data.get("activated", 0))
            inact = tot - act
            print(f" {pid}: total={tot} activated={act} inactive={inact}")

    inactive_total = total - activated_total
    print(f"[info] licenses (all): total={total} activated={activated_total} inactive={inactive_total}")
    return 0

def cmd_activate(client: KeygenClient, args: argparse.Namespace) -> int:
    fingerprint = args.fingerprint or generate_fingerprint()
    target_product_id = args.product_id

    payload = client.get_machines(fingerprint, target_product_id)
    items = payload.get("data", []) if isinstance(payload, dict) else []
    if items:
        print(
            f"[info] machine already activated for product {target_product_id}"
        )
        return 0

    unactivated_license = client.get_unactivated_license(product_id=target_product_id)
    if not unactivated_license or not (unactivated_license.get("data") or []):
        raise PoolExhaustedError("No unactivated licenses available in pool.")

    license_key = unactivated_license["data"][0].get("attributes", {}).get("key")

    meta = {"hostname": platform.node()}
    resp = client.activate(fingerprint, license_id=unactivated_license["data"][0]["id"], metadata=meta)

    # Persist license key to plaintext file named license.<product_id>.key
    try:
        out_path = resolve_license_key_file_path(args.license_key_file, args.product_id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(license_key, encoding="utf-8")
        try:
            os.chmod(out_path, 0o600)
        except Exception:
            # Best-effort on platforms/filesystems that don't support chmod
            pass
    except Exception as e:
        print(f"[warning] failed to write license key {license_key} to file: {e}", file=sys.stderr)

    # Extract activation_id
    activation_id = resp.get("data", {}).get("id") or "unknown"

    print(f"[info] activation successful (activation_id: {activation_id})")
    return 0

def cmd_deactivate(client: KeygenClient, args: argparse.Namespace) -> int:
    fingerprint = args.fingerprint or generate_fingerprint()
    target_product_id = args.product_id
    payload = client.get_machines(fingerprint, target_product_id)
    items = payload.get("data", []) if isinstance(payload, dict) else []
    if not items:
        print(f"[info] no activation found for this product on this machine (product: {target_product_id}, fingerprint: {fingerprint})")
        return 0
    machine = items[0]
    machine_id = machine.get("id")
    client.deactivate(machine_id)
    print(f"[info] deactivated machine {fingerprint}")
    return 0

def cmd_validate_key(cfg: Config, args: argparse.Namespace) -> int:
    fingerprint = args.fingerprint or generate_fingerprint()
    license_key = (args.license_key or "").strip()
    if not license_key:
        print('[error] license key is empty', file=sys.stderr)
        return 1
    res = requests.post(
        f"{cfg.base_url}/v1/accounts/{cfg.account_id}/licenses/actions/validate-key",
        headers={
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json"
        },
        data=json.dumps({
            "meta": {
                "key": license_key,
                "scope": {
                    "fingerprint": fingerprint
                }
            }
        })
    )
    if res.status_code not in (200, 201):
        raise LicenseError(f"Validation failed ({res.status_code}): {res.text[:500]}")
    data = res.json()
    code = data.get("meta", {}).get("code")
    if code == "VALID":
        print(f"[info] license key is valid for this machine (fingerprint: {fingerprint})")
        return 0
    else:
        print(f"[error] license key is NOT valid for this machine (fingerprint: {fingerprint}, code: {code})", file=sys.stderr)
        return 1

def ensure_token(cfg: Config, cli_token: str | None) -> str:
    tok = cli_token or cfg.load_api_token()
    if not tok:
        raise AuthError(
            "No API token provided. Use 'login', set --api-token, env OKSI_API_TOKEN, "
            f"or put api_token in {CONFIG_PATH}"
        )
    return tok

# ------------------------
# Argparse
# ------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="oksi-license",
        description="OKSI Licensing CLI (customer-facing)",
    )
    p.add_argument("--api-token", help="API token (overrides config/env)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    p.add_argument("--interactive", action="store_true", help="Start interactive mode (REPL)")

    # In interactive mode, a subcommand isn't required. Otherwise it is.
    sub = p.add_subparsers(dest="cmd", required=False)

    sub_login = sub.add_parser("login", help="Authenticate with email/password to obtain a User Token")
    sub_login.add_argument("--email", help="Account email (will prompt if omitted)")
    sub_login.add_argument("--password", help="Password string (unsafe; prefer --password-stdin or env)")
    sub_login.add_argument("--password-stdin", action="store_true",
                           help="Read password from STDIN (safer for scripts)")

    sub.add_parser("logout", help="Forget saved User Token")

    sub.add_parser("whoami", help="Show authenticated identity")

    sub.add_parser("status", help="Show license pool status")

    sub_activate = sub.add_parser("activate", help="Activate this machine")
    sub_activate.add_argument("product_id", help="Product to activate against")
    sub_activate.add_argument("--fingerprint", help="Override machine fingerprint to use for operations")
    sub_activate.add_argument(
        "--license-key-file",
        help=(
            f"Optional license key file. If not specified, key will be written as license.<product_id>.key under {(pathlib.Path.cwd() / '.oksi').resolve()}"
        ),
    )

    sub_deactivate = sub.add_parser("deactivate", help="Deactivate this machine")
    sub_deactivate.add_argument("product_id", help="Product to deactivate against")
    sub_deactivate.add_argument("--fingerprint", help="Override machine fingerprint to use for operations")

    sub_validate_key = sub.add_parser("validate-key", help="Validate a license key (online)")
    sub_validate_key.add_argument("license_key", help="License key to validate")
    sub_validate_key.add_argument("--fingerprint", help="Override machine fingerprint to use for operations")

    # Products
    sub.add_parser("list-products", help="List available products")

    return p

# ------------------------
# Main
# ------------------------

def run_once(cfg: Config, parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    # Allow overriding cfg via flags for the session
    cfg.base_url = args.base_url or cfg.base_url
    cfg.account_id = args.account_id or cfg.account_id

    # Dispatch a single command invocation
    if args.cmd == "login":
        bare = KeygenClient(cfg, api_token="")
        return cmd_login(cfg, bare, args)

    if args.cmd == "logout":
        return cmd_logout(cfg, None, args)

    if args.cmd == "validate-key":
        return cmd_validate_key(cfg, args)

    # For all other commands, ensure we have a token
    token = ensure_token(cfg, args.api_token)
    client = KeygenClient(cfg, token)

    if args.cmd == "whoami":
        return cmd_whoami(client, args)
    if args.cmd == "status":
        return cmd_status(client, args)
    if args.cmd == "list-products":
        return cmd_list_products(client, args)
    if args.cmd == "activate":
        return cmd_activate(client, args)
    if args.cmd == "deactivate":
        return cmd_deactivate(client, args)

    parser.print_help()
    return 1


def interactive_loop(cfg: Config, parser: argparse.ArgumentParser) -> int:
    # Setup history: load existing, persist on exit
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if HISTORY_FILE.exists():
            try:
                readline.read_history_file(str(HISTORY_FILE))
            except Exception:
                pass
        readline.set_history_length(1000)
        # Enable common key bindings (optional; up/down for history works by default)
        try:
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind("set editing-mode emacs")
        except Exception:
            pass
        atexit.register(lambda: _write_history_safely())
    except Exception:
        # History is best-effort; continue without persistence if setup fails
        pass

    print("[interactive] OKSI License CLI — type 'help' or 'exit'")
    try:
        while True:
            try:
                line = input("oksi> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            # Add to history if not a duplicate of the previous entry
            try:
                hlen = readline.get_current_history_length()
                last = readline.get_history_item(hlen) if hlen > 0 else None
                if line and line != last:
                    readline.add_history(line)
            except Exception:
                pass
            if line.lower() in {"exit", "quit", "q"}:
                break
            if line.lower() in {"help", "?"}:
                parser.print_help()
                continue
            if line.lower().startswith("help "):
                # Translate to "<cmd> --help"
                rest = line.split(None, 1)[1]
                line = rest + " --help"

            try:
                tokens = shlex.split(line)
            except ValueError as e:
                print(f"[error] parse: {e}")
                continue

            try:
                args = parser.parse_args(tokens)
            except SystemExit as e:
                # argparse error/help for the line; don't exit REPL
                # e.code may be 0 for --help or 2 for parse error
                continue

            try:
                code = run_once(cfg, parser, args)
            except SystemExit as e:
                # Handle any direct sys.exit from subcommands
                code = int(e.code) if isinstance(e.code, int) else 1
            except AuthError as e:
                print(f"[error] auth: {e}")
                code = 10
            except PoolExhaustedError as e:
                print(f"[error] pool exhausted: {e}")
                code = 11
            except NetworkError as e:
                print(f"[error] network: {e}")
                code = 12
            except LicenseError as e:
                print(f"[error] license: {e}")
                code = 13
            except KeyboardInterrupt:
                print()
                continue
            if code is not None and code != 0:
                print(f"[status] exit code {code}")
    except KeyboardInterrupt:
        print()
        return 130
    return 0

def _write_history_safely() -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(str(HISTORY_FILE))
    except Exception:
        pass

def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    cfg = Config.load()
    parser = build_parser()
    args = parser.parse_args(argv)

    # If interactive mode requested, drop into REPL (apply any global overrides once)
    cfg.base_url = args.base_url or cfg.base_url
    cfg.account_id = args.account_id or cfg.account_id
    if getattr(args, "interactive", False):
        return interactive_loop(cfg, parser)

    try:
        return run_once(cfg, parser, args)
    except AuthError as e:
        print(f"[error] auth: {e}", file=sys.stderr)
        return 10
    except PoolExhaustedError as e:
        print(f"[error] pool exhausted: {e}", file=sys.stderr)
        return 11
    except NetworkError as e:
        print(f"[error] network: {e}", file=sys.stderr)
        return 12
    except LicenseError as e:
        print(f"[error] license: {e}", file=sys.stderr)
        return 13
    except KeyboardInterrupt:
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
