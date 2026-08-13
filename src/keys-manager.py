#!/usr/bin/env python3
"""
keys-manager.py — master key registry + provisioning.

One key per service, stored once in ~/.hermes/toolkit/keys/ and provisioned
to every consuming tool (subfinder, uncover, gh/git, nvd, vulners, wpscan,
ngrok, vpn, .env, config.yaml).

Usage:
    python3 keys-manager.py add <service> <key>   # add/update + provision
    python3 keys-manager.py provision             # rebuild tool configs
    python3 keys-manager.py list                  # show keys (masked)

Example:
    python3 keys-manager.py add shodan ABC123...
    python3 keys-manager.py list
"""

from __future__ import annotations

import sys

from installer_core import HERMES_HOME, SECRET_FIELDS, mask, provision_keys

KEYS_DIR = HERMES_HOME / "toolkit" / "keys"
KNOWN = {fid: label for _g, fid, label, _s, _t in SECRET_FIELDS}


def load_registry() -> dict:
    out: dict = {}
    if KEYS_DIR.is_dir():
        for path in KEYS_DIR.glob("*.key"):
            out[path.stem] = path.read_text(encoding="utf-8").strip()
    return out


def cmd_add(service: str, key: str) -> None:
    if service not in KNOWN:
        print(f"unknown service '{service}'. Known: {', '.join(KNOWN)}")
        sys.exit(1)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    path = KEYS_DIR / f"{service}.key"
    path.write_text(key, encoding="utf-8")
    path.chmod(0o600)
    print(f"{service} saved to master registry ({mask(key)})")
    cmd_provision()


def cmd_provision() -> None:
    reg = load_registry()
    if not reg:
        print("registry is empty — add keys first: keys-manager.py add <service> <key>")
        return
    provision_keys(reg)
    print("provisioned " + ", ".join(sorted(reg)))


def cmd_list() -> None:
    reg = load_registry()
    if not reg:
        print("(empty)")
        return
    for service, value in sorted(reg.items()):
        label = KNOWN.get(service, service)
        print(f"{service:12} {label:42} {mask(value)}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 4:
        cmd_add(sys.argv[2], sys.argv[3])
    elif cmd == "provision":
        cmd_provision()
    elif cmd == "list":
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
