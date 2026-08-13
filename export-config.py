#!/usr/bin/env python3
"""
export-config.py — generate an install-config.json from an existing Hermes
environment (the running distro). The output contains REAL secrets —
keep it private (0600) and never ship it with the distribution.

Usage:
    python3 export-config.py [output.json]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from installer_core import TOOLS, mask, tool_path  # noqa: E402

HOME = Path.home()
HERMES = HOME / ".hermes"
OUT = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parent / "install-config.json"
)


def env_get(key: str) -> str:
    env = HERMES / ".env"
    if not env.is_file():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def parse_provider(path: Path) -> dict:
    out: dict = {}
    if not path.is_file():
        return out
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.endswith(":") and not s.startswith("-"):
            current = s[:-1].strip()
        elif current and s.startswith('- "'):
            out[current] = s[3:].rstrip('"')
    return out


def read_first(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def main() -> None:
    tools = {name: tool_path(name) is not None for name, _d, _c in TOOLS}

    secrets: dict = {}
    secrets["deepseek"] = env_get("DEEPSEEK_API_KEY")
    secrets["bot"] = env_get("TELEGRAM_BOT_TOKEN")
    secrets["users"] = env_get("TELEGRAM_ALLOWED_USERS")
    secrets["home_channel"] = env_get("TELEGRAM_HOME_CHANNEL")
    secrets["brave"] = env_get("BRAVE_SEARCH_API_KEY")
    secrets["serpapi"] = env_get("SERPAPI_API_KEY")

    wm = HERMES / "workspace_topics.json"
    if wm.is_file():
        try:
            wdata = json.loads(wm.read_text(encoding="utf-8"))
            hu = (wdata.get("home_user") or {}).get("chat_id")
            if hu:
                secrets["home_user"] = str(hu)
        except Exception:
            pass

    sub = parse_provider(HOME / ".config" / "subfinder" / "provider-config.yaml")
    unc = parse_provider(HOME / ".config" / "uncover" / "provider-config.yaml")
    for src, key in (
        ("github", "github"), ("virustotal", "virustotal"), ("shodan", "shodan"),
        ("urlscan", "urlscan"), ("dnsdumpster", "dnsdumpster"),
        ("zoomeyeapi", "zoomeye"), ("fofa", "fofa"),
    ):
        if src in sub:
            secrets[key] = sub[src]
    for src, key in (("shodan", "shodan"), ("zoomeye", "zoomeye")):
        if src in unc and key not in secrets:
            secrets[key] = unc[src]

    secrets["vulners"] = read_first(HOME / ".config" / "vulners" / "api.key")
    secrets["nvd"] = read_first(HOME / ".config" / "nvd" / "api.key")

    wp = HOME / ".wpscan" / "scan.json"
    if wp.is_file():
        try:
            secrets["wpscan"] = json.loads(wp.read_text()).get("api_token", "")
        except Exception:
            pass

    ng = HOME / ".config" / "ngrok" / "ngrok.yml"
    if ng.is_file():
        for line in ng.read_text(encoding="utf-8").splitlines():
            if "authtoken" in line:
                secrets["ngrok"] = line.split(":", 1)[1].strip()
                break

    vpn = HOME / "vpn-profiles" / "auth.txt"
    if vpn.is_file():
        lines = vpn.read_text(encoding="utf-8").splitlines()
        if lines:
            secrets["vpn_user"] = lines[0]
        if len(lines) > 1:
            secrets["vpn_pass"] = lines[1]

    secrets = {k: v for k, v in secrets.items() if v}
    config = {
        "config_version": 3,
        "tools": tools,
        "secrets": secrets,
        "sudo_mode": "restricted",
    }
    OUT.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(OUT, 0o600)
    print(f"written: {OUT}  (0600)")
    print(f"tools present: {sum(tools.values())}/{len(tools)}")
    print("keys: " + ", ".join(f"{k}({mask(v)})" for k, v in sorted(secrets.items())))
    print("WARNING: contains real secrets — keep private, never ship it.")


if __name__ == "__main__":
    main()
