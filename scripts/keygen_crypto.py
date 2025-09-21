"""
Minimal helpers to parse, verify, and decrypt Keygen certificates.

Public API surface:
- parse_certificate(cert_text: str) -> Certificate
- verify_signature(cert: Certificate, public_key_hex: Optional[str]) -> None
- verify_http_response_signature(res, uri: str, public_key_hex: str, *, host: str = "api.keygen.sh", method: str = "get") -> None
- decrypt_payload(cert: Certificate, *, license_key: str, machine_fingerprint: Optional[str] = None) -> Dict[str, Any]

Notes
- Parsing is tolerant of CRLF newlines and multi-line base64 payloads.
- AES-GCM decryption validates IV/tag sizes and wraps errors with clearer messages.
"""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterable

from urllib.parse import quote
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = [
    "Certificate",
    "LicenseFileError",
    "UnsupportedAlgorithmError",
    "parse_certificate",
    "verify_signature",
    "verify_http_response_signature",
    "decrypt_payload",
]

@dataclass(frozen=True, slots=True)
class Certificate:
    kind: str            # "LICENSE" or "MACHINE"
    alg: str             # e.g., "aes-256-gcm+ed25519" or "base64+ed25519"
    enc: str             # encrypted or base64 payload
    sig: Optional[str]   # base64 signature over f"{kind.lower()}/{enc}"
    meta: Optional[dict] # includes "expiry" (TTL of the file)
    raw_text: str        # full PEM-ish certificate text

class LicenseFileError(Exception): ...
class UnsupportedAlgorithmError(LicenseFileError): ...

def b64_any_decode(s: str) -> bytes:
    """Decode a base64 or urlsafe-base64 string, tolerating missing padding.

    Raises ValueError if decoding fails for both variants.
    """
    def _pad(x: str) -> str:
        return x + "=" * (-len(x) % 4)

    # Try strict first to catch garbage early; fall back to urlsafe.
    try:
        return base64.b64decode(_pad(s), validate=True)
    except Exception:
        pass
    try:
        return base64.urlsafe_b64decode(_pad(s))
    except Exception as exc:
        raise ValueError("invalid base64 encoding") from exc


def _strip_and_join_base64(lines: Iterable[str]) -> str:
    """Normalize multi-line/CRLF base64 by stripping whitespace and joining."""
    return "".join((ln.strip() for ln in lines if ln.strip()))

# ---------------------------
# Public: Parse + verify + decrypt
# ---------------------------
def parse_certificate(cert_text: str) -> Certificate:
    """Parse a PEM-ish LICENSE/MACHINE FILE into a Certificate object.

    - Accepts CRLF/CR newlines, multi-line base64 payloads.
    - Produces a frozen Certificate instance.
    """
    if not isinstance(cert_text, str):
        raise LicenseFileError("certificate must be a string")

    lines = cert_text.splitlines()
    if not lines:
        raise LicenseFileError("empty certificate")

    first = lines[0].strip()
    if not first.startswith("-----BEGIN ") or not first.endswith(" FILE-----"):
        raise LicenseFileError("malformed certificate header")
    kind = first.replace("-----BEGIN ", "").replace(" FILE-----", "").strip()
    if kind not in {"LICENSE", "MACHINE"}:
        raise LicenseFileError(f"unsupported certificate kind: {kind}")

    expected_footer = f"-----END {kind} FILE-----"
    if not lines[-1].strip() == expected_footer:
        raise LicenseFileError("malformed certificate footer")

    inner_b64 = _strip_and_join_base64(lines[1:-1])
    try:
        decoded = b64_any_decode(inner_b64)
    except Exception as exc:
        raise LicenseFileError("invalid base64 payload") from exc

    try:
        obj = json.loads(decoded)
    except Exception as exc:
        raise LicenseFileError("invalid JSON payload") from exc

    for k in ("enc", "alg", "sig"):
        if k not in obj:
            raise LicenseFileError(f"certificate missing '{k}'")

    alg = obj["alg"]
    enc = obj["enc"]
    sig = obj.get("sig")
    meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else None

    if not isinstance(alg, str) or not isinstance(enc, str) or (sig is not None and not isinstance(sig, str)):
        raise LicenseFileError("invalid certificate fields")

    return Certificate(kind=kind, alg=alg, enc=enc, sig=sig, meta=meta, raw_text=cert_text)

def verify_signature(cert: Certificate, public_key_hex: Optional[str]) -> None:
    """
    Verify Ed25519 signature over f\"{kind.lower()}/{enc}\" if a public key is provided.
    No-op if public_key_hex or cert.sig is None.

    Raises:
        cryptography.exceptions.InvalidSignature
    """
    if not public_key_hex or not cert.sig:
        return
    verify_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    message = f"{cert.kind.lower()}/{cert.enc}".encode("utf-8")
    verify_key.verify(b64_any_decode(cert.sig), message)

def verify_http_response_signature(
    res,
    uri: str,
    public_key_hex: str,
    *,
    host: str = "api.keygen.sh",
    method: str = "get",
) -> None:
    """
    Verify Keygen response signature and digest.

    Parameters
    - res: requests.Response-like object (needs .text and .headers)
    - uri: request URI path used for signing (e.g., '/v1/accounts/<id>/licenses')
    - public_key_hex: hex-encoded Ed25519 public key
    - host: expected host value in the signing string (default 'api.keygen.sh')
    - method: lowercase HTTP method used for signing (default 'get')

    Raises
    - ValueError on missing/invalid headers or inputs
    - cryptography.exceptions.InvalidSignature if signature verification fails
    """
    # 1) Get and parse Keygen-Signature header
    signature_hdr = res.headers.get("Keygen-Signature")
    if not signature_hdr:
        raise ValueError("signature is missing")

    params: dict[str, str] = {}
    for part in re.split(r"\s*,\s*", signature_hdr):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        params[k.strip()] = v.strip().strip('"')

    if params.get("algorithm") != "ed25519":
        raise ValueError("algorithm is unsupported")

    sig_b64 = params.get("signature")
    if not sig_b64:
        raise ValueError("signature parameter missing")

    # 2) Verify Digest header
    body_sha256_b64 = base64.b64encode(hashlib.sha256(res.text.encode()).digest()).decode()
    digest_value = f"sha-256={body_sha256_b64}"
    if digest_value != res.headers.get("Digest"):
        raise ValueError("digest did not match")

    # 3) Build signing data
    date = res.headers.get("Date")
    if not date:
        raise ValueError("Date header missing")

    signing_data = "".join(
        [
            f"(request-target): {method} {quote(uri, safe='/?=&')}\n",
            f"host: {host}\n",
            f"date: {date}\n",
            f"digest: {digest_value}",
        ]
    )

    # 4) Verify Ed25519 signature
    verify_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    verify_key.verify(
        base64.b64decode(sig_b64),
        signing_data.encode(),
    )

def decrypt_payload(
    cert: Certificate,
    *,
    license_key: str,
    machine_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decrypt the certificate payload and return the JSON dict.

    For aes-256-gcm:
      - LICENSE file secret = SHA256(license.key)
      - MACHINE file secret = SHA256(license.key + machine.fingerprint)
    """
    alg = cert.alg
    if alg.startswith("aes-256-gcm"):
        if cert.kind == "LICENSE":
            secret_material = license_key
        elif cert.kind == "MACHINE":
            if not machine_fingerprint:
                raise LicenseFileError("machine_fingerprint is required to decrypt a MACHINE file")
            secret_material = f"{license_key}{machine_fingerprint}"
        else:
            raise LicenseFileError(f"Unknown certificate kind: {cert.kind}")

        secret = hashlib.sha256(secret_material.encode("utf-8")).digest()

        # enc = b64(ciphertext) . b64(iv_12B) . b64(tag_16B)
        try:
            ct_b64, iv_b64, tag_b64 = cert.enc.split(".")
        except ValueError as exc:
            raise LicenseFileError("encrypted 'enc' format is invalid (expect 3 dot-separated parts)") from exc
        try:
            ct = b64_any_decode(ct_b64)
            iv = b64_any_decode(iv_b64)
            tag = b64_any_decode(tag_b64)
        except Exception as exc:
            raise LicenseFileError("invalid base64 in encrypted 'enc' parts") from exc

        if len(iv) != 12:
            raise LicenseFileError("invalid AES-GCM IV length (expected 12 bytes)")
        if len(tag) != 16:
            raise LicenseFileError("invalid AES-GCM tag length (expected 16 bytes)")

        try:
            aes = AESGCM(secret)
            plaintext = aes.decrypt(iv, ct + tag, b"")
        except Exception as exc:
            raise LicenseFileError("AES-GCM decryption failed") from exc
        try:
            return json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise LicenseFileError("decrypted payload is not valid UTF-8 JSON") from exc

    elif alg.startswith("base64+"):
        try:
            return json.loads(b64_any_decode(cert.enc).decode("utf-8"))
        except Exception as exc:
            raise LicenseFileError("invalid base64/JSON payload") from exc

    else:
        raise UnsupportedAlgorithmError(f"Unsupported algorithm: {alg}")
