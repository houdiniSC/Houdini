#!/usr/bin/env python3
"""
encrypt-config.py -- encrypt/decrypt a Hermes install config with a password.

The encrypted file (.hcfg) can be uploaded from the installer's first page:
the panel asks for the decryption password, decrypts locally, and applies
the settings without the plaintext ever touching the disk on the target.

Format (text, line based):
    HERMESCFG1
    <base64 salt>
    <base64 Fernet token (PBKDF2-HMAC-SHA256, 600k iterations)>

Usage:
    python3 encrypt-config.py install-config.json -o install-config.hcfg   # encrypt
    python3 encrypt-config.py --decrypt install-config.hcfg -o out.json     # verify
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:  # pragma: no cover
    sys.exit("cryptography is required: /home/hermes/hermes-venv/bin/pip install cryptography")

MAGIC = "HERMESCFG1"
ITERATIONS = 600_000


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_bytes(plain: bytes, password: str) -> bytes:
    salt = os.urandom(16)
    key = derive_key(password, salt)
    token = Fernet(key).encrypt(plain)
    return f"{MAGIC}\n{base64.b64encode(salt).decode('ascii')}\n{token.decode('ascii')}\n".encode("ascii")


def decrypt_bytes(raw: bytes, password: str) -> bytes:
    lines = raw.decode("utf-8").splitlines()
    if not lines or lines[0] != MAGIC:
        raise ValueError("not a Hermes encrypted config file")
    if len(lines) < 3:
        raise ValueError("encrypted config file is truncated")
    salt = base64.b64decode(lines[1])
    key = derive_key(password, salt)
    try:
        return Fernet(key).decrypt(lines[2].encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("wrong password or corrupted file") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt/decrypt a Hermes install config")
    parser.add_argument("input", help="input file (.json when encrypting, .hcfg when decrypting)")
    parser.add_argument("-o", "--output", required=True, help="output file path")
    parser.add_argument(
        "--decrypt", action="store_true", help="decrypt instead of encrypt"
    )
    parser.add_argument(
        "--password", default=None, help="password on the command line (avoid: it leaks to history)"
    )
    args = parser.parse_args()

    import getpass

    src = Path(args.input)
    if not src.is_file():
        sys.exit(f"input not found: {src}")

    password = args.password
    if not password:
        password = getpass.getpass("Encryption password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            sys.exit("passwords do not match")
    if not password:
        sys.exit("empty password is not allowed")

    out = Path(args.output)
    if args.decrypt:
        try:
            plain = decrypt_bytes(src.read_bytes(), password)
        except ValueError as exc:
            sys.exit(f"decrypt failed: {exc}")
        json.loads(plain.decode("utf-8-sig"))  # validate (BOM tolerated)
        out.write_bytes(plain)
        os.chmod(out, 0o600)
        print(f"decrypted: {out}  (0600)")
        return

    try:
        json.loads(src.read_text(encoding="utf-8-sig"))  # validate (BOM tolerated)
    except Exception as exc:
        sys.exit(f"invalid JSON in {src}: {exc}")
    encrypted = encrypt_bytes(src.read_bytes(), password)
    out.write_bytes(encrypted)
    os.chmod(out, 0o600)
    print(f"encrypted: {out}  (0600)")
    print("upload this file from the installer's first page with its password.")


if __name__ == "__main__":
    main()
