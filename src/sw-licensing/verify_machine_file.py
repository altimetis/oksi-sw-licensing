#!/usr/bin/env python3
from fingerprint import generate_fingerprint
import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--path', dest='path', required=True, help='Path to machine file (required)')
parser.add_argument('--license-key', dest='license_key', required=True, help='License key (required)')
parser.add_argument('--fingerprint', dest='fingerprint',
                    default=generate_fingerprint(), help='Machine fingerprint')
parser.add_argument("--pubkey", required=True, help="Ed25519 public key (hex) to verify signature")
args = parser.parse_args()

# Use shared implementation from keygen_files.py instead of duplicating logic
from keygen_crypto import parse_certificate, verify_signature, decrypt_payload

# Read the machine file
try:
    with open(args.path, 'r', encoding='utf-8') as f:
        machine_file = f.read().rstrip()
except (FileNotFoundError, PermissionError) as e:
    print(f'[error] path does not exist or permission denied: {e}')
    sys.exit(1)

# Parse certificate
try:
    cert = parse_certificate(machine_file)
except Exception as e:
    print(f'[error] failed to parse machine file certificate: {e}')
    sys.exit(1)

# Verify signature
try:
    verify_signature(cert, args.pubkey)
except Exception as e:
    print(f'[error] certificate signature verification failed: {e}')
    sys.exit(1)

print('[info] certificate signature verification successful!')

# Decrypt payload
try:
    payload = decrypt_payload(cert, license_key=args.license_key, machine_fingerprint=args.fingerprint)
except Exception as e:
    print(f'[error] decryption failed: {e}')
    sys.exit(1)

print('[info] decryption successful!')
try:
    # Expected to be a dict; pretty-print if possible
    print(json.dumps(payload, indent=2))
except Exception:
    print(str(payload))
