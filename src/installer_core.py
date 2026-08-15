#!/usr/bin/env python3
"""
installer_core.py — shared LIVE installation engine for the TUI and GUI frontends.

UI-agnostic: reports progress through callbacks instead of touching widgets.
"""

from __future__ import annotations

import asyncio
import base64
import getpass
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Callable

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
# Knowledge pack source: HOUDINI_PACK_DIR env override wins (set by the
# installers when the TUI runs from a synced copy inside a distro and the
# pack itself lives next to the original package), otherwise the folder
# beside this script (normal local / native-Linux layout).
_PACK_ENV = os.environ.get("HOUDINI_PACK_DIR", "").strip()
PACK_DIR = Path(_PACK_ENV).expanduser() if _PACK_ENV else SCRIPT_DIR.parent / "knowledge-pack"
HERMES_HOME = Path.home() / ".hermes"

# ── Data ──────────────────────────────────────────────────────────────────
APT_TOOLS = {
    "nmap": "nmap",
    "nikto": "nikto",
    "sqlmap": "sqlmap",
    "gobuster": "gobuster",
    "ffuf": "ffuf",
    "whatweb": "whatweb",
    "openvpn": "openvpn",
}
PD_TOOLS = [
    ("nuclei", "v3.11.0", "nuclei_3.11.0_linux_amd64.zip"),
    ("subfinder", "v2.15.0", "subfinder_2.15.0_linux_amd64.zip"),
    ("httpx", "v1.10.0", "httpx_1.10.0_linux_amd64.zip"),
]

TOOLS = [
    ("nuclei", "vuln scanning (templates)", "pd"),
    ("subfinder", "subdomain enumeration", "pd"),
    ("httpx", "HTTP probing / tech detection", "pd"),
    ("nmap", "network scanning", "apt"),
    ("sqlmap", "SQL injection", "apt"),
    ("wpscan", "WordPress scanner", "extra"),
    ("nikto", "web server checks", "apt"),
    ("gobuster", "directory / DNS brute", "apt"),
    ("ffuf", "fast web fuzzing", "apt"),
    ("whatweb", "tech fingerprinting", "apt"),
    ("droopescan", "Drupal scanner", "uv"),
    ("drupwn", "Drupal enumeration", "uv"),
    ("ngrok", "tunnels / callbacks", "ngrok"),
    ("openvpn", "VPN egress (multi-provider)", "apt"),
    ("browser-capture", "browser traffic capture (Playwright + mitmproxy)", "browser"),
    ("apktool", "APK decode / rebuild", "mobile"),
    ("jadx", "APK decompiler", "mobile"),
    ("frida", "runtime instrumentation (Frida + Objection)", "mobile"),
]

# Master key registry — ONE key per service. Tools (subfinder, uncover, gh,
# SDKs...) consume from this registry via provision_keys(); nothing is asked
# twice. Tuple: (group, service_id, label, is_secret, consumers)
SECRET_GROUPS = [
    ("core", "Core"),
    ("recon", "Recon providers"),
    ("vulndb", "Vulnerability databases"),
    ("network", "Network & tunnels"),
    ("search", "Search & web"),
]

SECRET_FIELDS = [
    ("core", "model_provider", "AI provider (deepseek/openai/opencode/custom)", False, "cfg"),
    ("core", "model", "AI model ID (OpenAI-compatible)", False, "cfg"),
    ("core", "model_base_url", "AI base URL (custom only)", False, "cfg"),
    ("core", "api_key", "AI model API key (provider)", True, "env"),
    ("core", "bot", "Telegram bot token", True, "env"),
    ("core", "users", "Allowed Telegram user IDs (comma)", False, "env"),
    ("core", "home_channel", "Home group chat[:topic] (optional, auto on first run)", False, "home"),
    ("core", "home_user", "Home user (private chat) ID (optional, auto on first run)", False, "map"),
    ("recon", "github", "GitHub PAT (subfinder + gh + git)", True, "subfinder|env"),
    ("recon", "shodan", "Shodan (subfinder + uncover)", True, "subfinder|uncover"),
    ("recon", "virustotal", "VirusTotal (subfinder)", True, "subfinder"),
    ("recon", "urlscan", "URLScan (subfinder)", True, "subfinder"),
    ("recon", "dnsdumpster", "DNSDumpster (subfinder)", True, "subfinder"),
    ("recon", "zoomeye", "ZoomEye (subfinder + uncover)", True, "subfinder|uncover"),
    ("recon", "fofa", "Fofa email:key (subfinder)", True, "subfinder"),
    ("vulndb", "nvd", "NVD API key", True, "nvd"),
    ("vulndb", "vulners", "Vulners API key", True, "vulners"),
    ("vulndb", "wpscan", "WPScan API token", True, "wpscan"),
    ("network", "ngrok", "ngrok authtoken", True, "ngrok"),
    ("network", "vpn_user", "VPN username (default provider)", False, "vpn"),
    ("network", "vpn_pass", "VPN password (default provider)", True, "vpn"),
    ("network", "vpn_profiles_dir", "VPN profiles folder (copies *.ovpn)", False, "vpn"),
    ("search", "brave", "Brave Search API key", True, "env"),
    ("search", "serpapi", "SerpAPI key", True, "env"),
]

MODEL_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-flash",
        "preset_models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.4",
        "preset_models": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"],
    },
    "opencode": {
        "label": "OpenCode",
        "base_url": "https://opencode.ai/zen/v1",
        "default_model": "deepseek-v4-flash",
        "preset_models": ["deepseek-v4-flash", "deepseek-v4-flash-free"],
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",
        "default_model": "",
        "preset_models": [],
    },
}

SUDO_MODES = [
    ("restricted", "Restricted (recommended)", "openvpn, systemctl, apt, nmap, tcpdump, docker"),
    ("wide", "Wide (everything)", "NOPASSWD: SETENV: ALL"),
    ("none", "None", "leave sudo as-is"),
]


def fetch_model_list(base_url: str, api_key: str, timeout: float = 12.0) -> list[str] | None:
    """Fetch the live OpenAI-compatible model catalog (GET {base_url}/models).

    Returns a sorted list of model ids, or None when the endpoint is
    unreachable / rejects the key - callers fall back to curated presets.
    """
    import urllib.request

    if not base_url or not api_key:
        return None
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    ids = sorted(
        {str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")}
    )
    return ids or None


def model_choices(provider: str, base_url: str, api_key: str) -> list[str]:
    """Live catalog first (provider endpoint), curated presets as fallback."""
    preset = MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS["custom"])
    live = fetch_model_list(base_url, api_key)
    if live:
        return live
    return list(preset.get("preset_models") or [])


def ensure_holographic_memory(text: str) -> str:
    """Make sure config.yaml enables the local Holographic (SQLite) provider."""
    if "provider: holographic" not in text:
        lines = text.splitlines()
        mem_idx = next(i for i, line in enumerate(lines) if line.strip() == "memory:")
        j = mem_idx + 1
        while j < len(lines) and lines[j].startswith(" "):
            j += 1
        lines.insert(j, "  provider: holographic")
        text = "\n".join(lines)
    if "hermes-memory-store" not in text:
        text = (
            text.rstrip()
            + "\n\nplugins:\n  hermes-memory-store:\n"
            "    auto_extract: false\n    default_trust: 0.5\n"
            "    min_trust_threshold: 0.3\n"
            "    temporal_decay_half_life: 0\n    hrr_dim: 1024\n"
        )
    return text


def strip_holographic_memory(text: str) -> str:
    """Remove the Holographic provider key and its plugin block from config.yaml."""
    lines = [
        line for line in text.splitlines() if line.strip() != "provider: holographic"
    ]
    out = []
    skip_plugins = False
    for line in lines:
        if line.strip() == "plugins:":
            skip_plugins = True
            continue
        if skip_plugins:
            if line and not line.startswith(" "):
                skip_plugins = False
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def seed_workspace_map(secrets: dict, on_log: Callable[[str], None] | None = None) -> None:
    """Pre-seed workspace_topics.json from home_channel / home_user at install.

    Keeps config.yaml / .env / workspace_topics.json consistent from second
    zero: ``home_channel`` (group, negative chat_id) seeds the ``home_channel``
    slot, ``home_user`` (private chat) seeds ``home_user``. Only the chat_ids
    are pinned here — the topic ids themselves are created dynamically on
    first contact (``topics_pending: true`` drives first-run-setup).
    """
    secrets = secrets or {}
    hc = secrets.get("home_channel")
    hu = secrets.get("home_user")
    if not hc and not hu:
        return

    path = HERMES_HOME / "workspace_topics.json"
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}

    def _entry(chat: str, slot: str) -> dict:
        return {
            "chat_id": int(chat) if chat.lstrip("-").isdigit() else chat,
            "flat": slot == "home_user",
            "topics": {},
            "topics_pending": True,
            "preconfigured": True,
        }

    seeded: list[str] = []

    def _seed(slot: str, raw: str) -> None:
        chat = str(raw).split(":", 1)[0].strip()
        if not chat:
            return
        existing = data.get(slot)
        if isinstance(existing, dict) and existing.get("chat_id") is not None:
            return  # slot already seeded — never overwrite
        data[slot] = _entry(chat, slot)
        seeded.append(slot)

    if hc:
        chat = str(hc).split(":", 1)[0].strip()
        slot = "home_channel" if chat.startswith("-") else "home_user"
        _seed(slot, chat)
    if hu:
        _seed("home_user", hu)
    if not seeded:
        return

    HERMES_HOME.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    if on_log:
        on_log(f"workspace map pre-seeded: {', '.join(seeded)} (topics pending)")


SKILL_MODES = [
    (
        "minimal",
        "Minimal (recommended)",
        "Custom operational skills only — no bulk reference library",
    ),
]


INSTALL_STEP_COUNT = 17


def mask(value: str) -> str:
    return value if len(value) <= 8 else f"{value[:4]}...{value[-4:]}"


def tool_path(name: str) -> str | None:
    """Locate a tool on PATH or in common per-user binary dirs
    (~/.local/bin, ~/go/bin, ~/.cargo/bin, uv tool dirs) which may be
    missing from a non-login shell PATH (e.g. uv-installed tools)."""
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    for candidate in (
        home / ".local" / "bin" / name,
        home / "go" / "bin" / name,
        home / ".cargo" / "bin" / name,
        home / ".local" / "share" / "uv" / "tools" / name / "bin" / name,
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


# ── Master key registry + provisioning ────────────────────────────────────
def provision_keys(secrets: dict, on_log: Callable[[str], None] | None = None) -> bool:
    """Write every provided key ONCE into the master registry, then provision
    all consuming tools (subfinder, uncover, gh/git via env, nvd, vulners,
    wpscan, ngrok, vpn, config.yaml) from that registry."""
    log = on_log or (lambda _line: None)
    home = Path.home()
    keys_dir = HERMES_HOME / "toolkit" / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)

    # 1) master registry — one file per service (toolkit-scan indexes this dir)
    for _group, fid, _label, _secret, _consumers in SECRET_FIELDS:
        value = secrets.get(fid)
        if value:
            path = keys_dir / f"{fid}.key"
            path.write_text(str(value), encoding="utf-8")
            os.chmod(path, 0o600)

    # 2) .env (dedupe: remove previous lines for the same keys)
    env_map = {
        "api_key": "OPENAI_API_KEY",
        "bot": "TELEGRAM_BOT_TOKEN",
        "users": "TELEGRAM_ALLOWED_USERS",
        "home_channel": "TELEGRAM_HOME_CHANNEL",
        "brave": "BRAVE_SEARCH_API_KEY",
        "serpapi": "SERPAPI_API_KEY",
        "github": "GITHUB_TOKEN",
    }
    env_lines = {key: secrets[fid] for fid, key in env_map.items() if secrets.get(fid)}
    if env_lines:
        env_file = HERMES_HOME / ".env"
        existing = (
            env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
        )
        kept = [line for line in existing if not any(line.startswith(k + "=") for k in env_map.values())]
        for key, value in env_lines.items():
            kept.append(f"{key}={value}")
        env_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
        os.chmod(env_file, 0o600)
        log(".env updated and locked (0600)")

    # 3) config.yaml (model endpoint + home channel) - OpenAI-compatible
    # provider presets; only the API key + model choice come from the user.
    api_key = (secrets.get("api_key") or "").strip()
    if api_key:
        tpl = HERMES_HOME / "config.template.yaml"
        if tpl.is_file():
            provider = (secrets.get("model_provider") or "deepseek").strip().lower()
            preset = MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS["custom"])
            base_url = (secrets.get("model_base_url") or "").strip() or preset["base_url"]
            model_id = (secrets.get("model") or "").strip() or preset["default_model"]
            if base_url and model_id:
                text = (
                    tpl.read_text(encoding="utf-8")
                    .replace("__MODEL_ID__", model_id)
                    .replace("__MODEL_BASE_URL__", base_url)
                    .replace("__API_KEY__", api_key)
                )
                (HERMES_HOME / "config.yaml").write_text(text, encoding="utf-8")
                log(
                    f"config.yaml written (model={model_id}, "
                    f"provider={provider or 'custom'})"
                )
            else:
                missing_cfg = [
                    name
                    for name, val in (("base_url", base_url), ("model", model_id))
                    if not val
                ]
                log(
                    f"model config incomplete ({', '.join(missing_cfg)} empty) "
                    f"- config.yaml skipped"
                )
    hc = secrets.get("home_channel") or secrets.get("home_user")
    if hc and (HERMES_HOME / "config.yaml").is_file():
        chat, _, thread = hc.partition(":")
        cfg = HERMES_HOME / "config.yaml"
        text = cfg.read_text(encoding="utf-8")
        text = text.replace('chat_id: ""', f'chat_id: "{chat}"')
        if thread:
            text = text.replace('thread_id: ""', f'thread_id: "{thread}"')
        cfg.write_text(text, encoding="utf-8")
        log(f"home channel configured: {mask(chat)}")
    seed_workspace_map(secrets, on_log=log)

    # 4) simple key files
    simple = {
        "ngrok": (home / ".config" / "ngrok" / "ngrok.yml",
                  lambda v: f'version: "2"\nauthtoken: {v}\n'),
        "vulners": (home / ".config" / "vulners" / "api.key", lambda v: v + "\n"),
        "nvd": (home / ".config" / "nvd" / "api.key", lambda v: v + "\n"),
        "wpscan": (home / ".wpscan" / "scan.json",
                   lambda v: '{"api_token":"%s"}\n' % v),
    }
    for fid, (path, fmt) in simple.items():
        if secrets.get(fid):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fmt(secrets[fid]), encoding="utf-8")
            os.chmod(path, 0o600)
            log(f"{fid} provisioned ({mask(secrets[fid])})")


    # 5) VPN profiles - copied from a local folder, preserving per-provider
    # subfolders (e.g. <dir>/proton/*.ovpn, <dir>/custom/*.ovpn). Auth is NOT
    # written to auth.txt: vpn_user/vpn_pass already landed in the key
    # registry (toolkit/keys/vpn_*.key) by the master loop above, and extra
    # providers add vpn_<provider>_user/pass keys later via Settings.
    vpn_dir = home / "vpn-profiles"
    src_dir = str(secrets.get("vpn_profiles_dir") or "").strip()
    if src_dir:
        pdir = Path(src_dir).expanduser()
        if pdir.is_dir():
            copied = 0
            for f in sorted(pdir.rglob("*.ovpn")):
                rel = f.relative_to(pdir)
                target = vpn_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                os.chmod(target, 0o600)
                copied += 1
            log(
                f"vpn profiles copied from {src_dir} "
                f"({copied} profiles; auth via key registry, not auth.txt)"
            )
        else:
            log(f"vpn_profiles_dir not found: {src_dir}")

    # 6) provider configs — built from the SAME master keys (no duplication)
    provider_map = {
        "subfinder": {
            "github": "github",
            "virustotal": "virustotal",
            "shodan": "shodan",
            "urlscan": "urlscan",
            "dnsdumpster": "dnsdumpster",
            "zoomeye": "zoomeyeapi",
            "fofa": "fofa",
        },
        "uncover": {
            "shodan": "shodan",
            "zoomeye": "zoomeye",
        },
    }
    for tool, mapping in provider_map.items():
        blocks = []
        for fid, provider in mapping.items():
            if secrets.get(fid):
                blocks.append(f'{provider}:\n  - "{secrets[fid]}"')
        if blocks:
            path = home / ".config" / tool / "provider-config.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            log(f"{tool} provider config provisioned ({len(blocks)} providers)")

    return True


# ── Live installer engine ─────────────────────────────────────────────────
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"          # CSI (colors, cursor, erase)
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"     # OSC (window titles)
    r"|\x1b[()][0-9A-Z]"                  # charset select
    r"|\x1b[@-Z\\-^_]"                    # single-char escapes
)


def clean_log_line(raw: str) -> str:
    """Strip ANSI escapes and collapse \\r progress updates to the last frame."""
    text = _ANSI_RE.sub("", raw)
    if "\r" in text:
        text = text.split("\r")[-1]
    return text.strip()


class LiveInstaller:
    """Runs the real installation steps.

    dry_run=True simulates (for automated UI tests).
    on_log receives plain-text lines; on_progress fires once per step.
    """

    def __init__(
        self,
        data: dict,
        dry_run: bool = False,
        sudo_password: str | None = None,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[], None] | None = None,
        log_file: str | Path | None = None,
    ) -> None:
        self.data = data
        self.dry_run = dry_run
        self.sudo_password = sudo_password
        self.failed: list[str] = []
        # Hetzner-style cloud images mount /tmp as a tiny tmpfs (often
        # 1-2 GB). Browser downloads (playwright ~800MB unpacked) and other
        # big extractions then fill it mid-run and freeze on write(2).
        # Point ALL temp work at the real disk once, up front; every
        # subprocess (pip, unzip, playwright, node) inherits this env.
        self._tmpdir = Path.home() / ".cache" / "houdini-tmp"
        try:
            self._tmpdir.mkdir(parents=True, exist_ok=True)
            for _var in ("TMPDIR", "TMP", "TEMP"):
                os.environ[_var] = str(self._tmpdir)
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(
                Path.home() / ".cache" / "ms-playwright"
            )
        except OSError:
            pass  # fall back to system tmp if ~/.cache is unavailable
        base_log = on_log or (lambda _line: None)
        self.log_file = Path(log_file).expanduser() if log_file else None
        if self.log_file is not None:

            def _log(line: str) -> None:
                base_log(line)
                if self.log_file is not None:
                    try:
                        with self.log_file.open("a", encoding="utf-8") as fh:
                            fh.write(line.rstrip("\n") + "\n")
                    except OSError:
                        pass

            self.on_log = _log
        else:
            self.on_log = base_log
        self.on_progress = on_progress or (lambda: None)

    async def run(self) -> None:
        if self.log_file is not None:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                self.log_file.write_text("", encoding="utf-8")
            except OSError:
                self.log_file = None
            if self.log_file is not None:
                self.on_log("=== Houdini install started ===")
        sec = self.data.get("secrets", {})
        self.on_log(
            "model config collected: "
            f"provider={sec.get('model_provider') or '<empty>'}, "
            f"model={sec.get('model') or '<empty>'}, "
            f"base_url={sec.get('model_base_url') or '<empty>'}, "
            f"api_key={'<set>' if sec.get('api_key') else '<empty>'}"
        )
        steps = [
            ("requirements", "Checking requirements"),
            ("hermes", "Installing Hermes core"),
            ("apt", "Installing apt toolchain"),
            ("pd", "Downloading nuclei / subfinder / httpx"),
            ("ngrok", "Installing ngrok"),
            ("drupal", "Installing droopescan / drupwn"),
            ("wpscan", "Installing wpscan"),
            ("templates", "Updating nuclei templates"),
            ("knowledge", "Merging knowledge pack"),
            ("config", "Writing secrets & configs"),
            ("sudoers", "Configuring sudo permissions"),
            ("browser", "Installing browser capture stack"),
            ("mobile", "Installing mobile toolchain"),
            ("memory", "Enabling local memory"),
            ("toolkit", "Generating tool inventory"),
            ("gateway", "Starting gateway"),
            ("webui", "Installing WebUI dashboard"),
        ]
        for key, label in steps:
            self.on_log(f"● {label} ...")
            if self.dry_run:
                await asyncio.sleep(0.05)
                ok = True
            else:
                ok = await self._step(key)
            if not ok:
                self.failed.append(label)
                self.on_log(f"✗ {label} failed")
            self.on_progress()
        self.on_log(
            f"=== install finished | failed: "
            f"{', '.join(self.failed) if self.failed else 'none'} | "
            f"log: {self.log_file} ==="
        )

    async def _sh(self, cmd: str, env: dict | None = None) -> bool:
        full_env = dict(os.environ)
        full_env["PATH"] = f"{Path.home() / '.local/bin'}:{full_env.get('PATH', '')}"
        if env:
            full_env.update(env)
        # Running as root (e.g. bare SSH server): sudo may not even be
        # installed. Strip the prefix - root needs no escalation.
        if os.geteuid() == 0:
            cmd = cmd.replace("sudo ", "")
        use_sudo = bool(self.sudo_password) and "sudo " in cmd
        shell_cmd = cmd.replace("sudo ", "sudo -S -p '' ") if use_sudo else cmd
        stdin = asyncio.subprocess.PIPE if use_sudo else None
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=full_env,
        )
        if use_sudo and proc.stdin is not None and self.sudo_password:
            proc.stdin.write((self.sudo_password + "\n").encode())
            await proc.stdin.drain()
            proc.stdin.close()
        assert proc.stdout is not None
        async for line in proc.stdout:
            text = clean_log_line(line.decode(errors="replace").rstrip())
            if text:
                self.on_log(text)
        return (await proc.wait()) == 0

    async def _sh_out(self, cmd: str) -> str:
        """Run a command and return its last output line (for version probes)."""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        out: list[str] = []
        async for line in proc.stdout:
            text = clean_log_line(line.decode(errors="replace").rstrip())
            if text:
                out.append(text)
        await proc.wait()
        return out[-1] if out else ""

    async def _step(self, key: str) -> bool:
        tools = self.data["tools"]
        if key == "requirements":
            # Base toolchain EVERY later step relies on: python3-pip is NOT
            # shipped by Ubuntu 24.04+ (PEP 668) and unzip is needed for the
            # jadx / nuclei GitHub releases - install them once, here.
            missing = [b for b in ("curl", "git") if shutil.which(b) is None]
            if not shutil.which("unzip") or not await self._sh("python3 -m pip --version >/dev/null 2>&1"):
                self.on_log("base toolchain: installing curl git python3-pip unzip...")
                return await self._sh(
                    "sudo apt-get update -qq && sudo apt-get install -y -qq "
                    "curl git python3-pip unzip"
                )
            if missing:
                self.on_log(f"missing base tools: {', '.join(missing)} — installing via apt")
                return await self._sh(
                    "sudo apt-get update -qq && sudo apt-get install -y -qq "
                    + " ".join(missing)
                )
            return True

        if key == "hermes":
            if tool_path("hermes"):
                self.on_log("Hermes already installed — skipping")
                return True
            # NOTE: `<(curl ...)` is bash-only; the TUI runs commands via
            # /bin/sh (dash) which rejects process substitution. The install
            # wizard reads /dev/tty directly, so it must be skipped explicitly
            # with --skip-setup (our installer writes config.yaml itself).
            #
            # install.sh hardcodes PYTHON_VERSION="3.11". Do not pin any
            # version: use whatever Python this system already has (Ubuntu
            # 24.04 -> 3.12, 25.04 -> 3.14, ...). uv python find <that>
            # resolves locally - no python-build-standalone tarball download.
            #
            # Flaky networks drop PyPI/GitHub connections mid-fetch; retry
            # the whole installer a few times before declaring failure.
            #
            # --skip-browser: Hermes' install.sh would pull Playwright via npm
            # (Node) whose extract froze on cloud images (Node 26 bug). Our
            # own "browser" step installs the SAME Playwright version through
            # pip/Python - stable zipfile extraction - so the browser engine
            # is always installed by Python, never Node.
            # timeout 1200: hard cap - a frozen child must never stall the
            # wizard; the retry loop below re-runs.
            _py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
            for attempt in (1, 2, 3):
                ok = await self._sh(
                    "curl -fsSL https://hermes-agent.nousresearch.com/install.sh "
                    f"| sed 's/^PYTHON_VERSION=\\\"3.11\\\"/PYTHON_VERSION=\\\"{_py_ver}\\\"/' "
                    "| timeout 1200 bash -s -- --non-interactive --skip-setup --skip-browser"
                )
                if ok:
                    return True
                if tool_path("hermes"):
                    self.on_log("Hermes install retry succeeded via leftover artifacts")
                    return True
                if attempt < 3:
                    self.on_log(f"attempt {attempt} failed — retrying in 10s...")
                    await asyncio.sleep(10)
            return False

        if key == "apt":
            selected = [APT_TOOLS[t] for t in APT_TOOLS if tools.get(t)]
            if not selected:
                self.on_log("no apt tools selected — skipping")
                return True
            return await self._sh(
                "sudo apt-get update -qq && sudo apt-get install -y -qq "
                + " ".join(["dnsutils", "netcat-openbsd", "jq", "unzip"] + selected)
            )

        if key == "pd":
            ok = True
            for name, ver, fname in PD_TOOLS:
                if not tools.get(name):
                    continue
                if tool_path(name):
                    self.on_log(f"{name} already installed — skipping")
                    continue
                url = f"https://github.com/projectdiscovery/{name}/releases/download/{ver}/{fname}"
                self.on_log(f"downloading {name} ...")
                ok = await self._sh(
                    f"cd /tmp && curl -fsSL -o {fname} '{url}' "
                    f"&& sudo unzip -o -q {fname} -d /usr/local/bin && sudo chmod +x /usr/local/bin/{name}"
                ) and ok
            return ok

        if key == "ngrok":
            if not tools.get("ngrok"):
                return True
            if tool_path("ngrok"):
                self.on_log("ngrok already installed — skipping")
                return True
            return await self._sh(
                "cd /tmp && curl -fsSL -o ngrok.tgz "
                "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz "
                "&& sudo tar xzf ngrok.tgz -C /usr/local/bin"
            )

        if key == "drupal":
            if not (tools.get("droopescan") or tools.get("drupwn")):
                return True
            # Judge by reality (tool exists on PATH), not by pip's exit code:
            # the frida/prompt-toolkit resolver conflict makes pip exit 1
            # even when everything installs fine.
            if tools.get("droopescan") and not tool_path("droopescan"):
                # Isolate droopescan (2021) in its own venv, exactly like
                # drupwn. Its legacy cement dependency calls
                # inspect.getargspec, which Python 3.11+ removed - patch it
                # inside the venv so the tool actually runs.
                venv = HERMES_HOME / "venvs" / "droopescan"
                py = venv / "bin" / "python"
                made = await self._sh(
                    f"python3 -m venv {shlex.quote(str(venv))} && "
                    f"{shlex.quote(str(py))} -m pip install -q droopescan"
                )
                if made:
                    await self._sh(
                        f"find {shlex.quote(str(venv / 'lib'))} -name '*.py' "
                        "-exec sed -i 's/inspect\\.getargspec/inspect.getfullargspec/g' {} + 2>/dev/null; true"
                    )
                bin_script = venv / "bin" / "droopescan"
                if bin_script.is_file():
                    launcher = f"#!/usr/bin/env bash\nexec {bin_script} \"$@\"\n"
                    await self._sh(
                        f"printf '%s' {shlex.quote(launcher)} | sudo tee /usr/local/bin/droopescan >/dev/null "
                        "&& sudo chmod +x /usr/local/bin/droopescan"
                    )
                if not tool_path("droopescan"):
                    self.on_log(
                        "! droopescan could not be made runnable (2021 "
                        "codebase) — drupwn + nuclei cover Drupal"
                    )
            if tools.get("drupwn") and not tool_path("drupwn"):
                # drupwn (last release 2019) requires prompt_toolkit<=2.0.7
                # while frida-tools needs 3.x - one environment can never
                # satisfy both. Give drupwn its own venv + wrapper so it
                # stops poisoning the system resolver verdict entirely.
                venv = HERMES_HOME / "venvs" / "drupwn"
                py = venv / "bin" / "python"
                for attempt in (1, 2, 3):
                    made = await self._sh(
                        f"python3 -m venv {shlex.quote(str(venv))} && "
                        f"{shlex.quote(str(py))} -m pip install -q 'setuptools<81' && "
                        f"{shlex.quote(str(py))} -m pip install -q "
                        "--no-build-isolation git+https://github.com/immunIT/drupwn"
                    )
                    if made:
                        break
                    if attempt < 3:
                        self.on_log(f"drupwn venv install failed — retrying in 8s...")
                        await asyncio.sleep(8)
                if py.is_file() and (venv / "lib").is_dir():
                    launcher = f"#!/usr/bin/env bash\nexec {py} -m drupwn \"$@\"\n"
                    await self._sh(
                        f"printf '%s' {shlex.quote(launcher)} | sudo tee /usr/local/bin/drupwn >/dev/null "
                        "&& sudo chmod +x /usr/local/bin/drupwn"
                    )
            # drupwn is the hard requirement; droopescan is best-effort only
            # (its 2021 code base is broken on modern Python interpreters).
            if tools.get("drupwn") and not tool_path("drupwn"):
                self.on_log("drupwn still missing after install")
                return False
            return True

        if key == "wpscan":
            if not tools.get("wpscan"):
                return True
            if tool_path("wpscan"):
                self.on_log("wpscan already installed — skipping")
                return True
            # wpscan is a ruby gem; native extensions need the ruby headers
            # (ruby-dev). Without them `gem install` fails to build.
            ok = await self._sh(
                "sudo apt-get install -y -qq ruby-dev && sudo gem install wpscan"
            )
            return ok or await self._sh("gem install wpscan")

        if key == "templates":
            if tools.get("nuclei") and tool_path("nuclei"):
                return await self._sh("nuclei -update-templates")
            return True

        if key == "browser":
            if not tools.get("browser-capture"):
                return True
            if tool_path("browser-capture"):
                self.on_log("browser-capture already installed — skipping")
                return True
            venv = Path.home() / "browser-venv"
            py = venv / "bin" / "python"
            # Match the Playwright version Hermes' browser tools expect so
            # pip downloads the SAME chromium revision into the shared cache
            # (~/.cache/ms-playwright) - one browser, used by both. Hermes
            # installs FHS-style under /usr/local/lib/hermes-agent; check
            # that first, then the legacy ~/.hermes path, then the npm
            # package.json as the final source of truth.
            pw_ver = ""
            _candidates = [
                Path("/usr/local/lib/hermes-agent/venv/bin/python"),
                HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python",
            ]
            hermes_py = next((p for p in _candidates if p.is_file()), None)
            if hermes_py is not None:
                raw = (
                    await self._sh_out(
                        f"{shlex.quote(str(hermes_py))} -c "
                        "'import importlib.metadata; "
                        "print(importlib.metadata.version(\"playwright\"))' "
                        "2>/dev/null || true"
                    )
                ).strip()
                # Only accept a real version string - _sh_out returns the
                # last output line which may be a PackageNotFoundError
                # traceback line when playwright isn't in the Hermes venv.
                if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", raw):
                    pw_ver = raw
            if not pw_ver:
                npm_pkg = Path(
                    "/usr/local/lib/hermes-agent/node_modules/playwright/package.json"
                )
                if npm_pkg.is_file():
                    try:
                        import json as _json
                        _ver = _json.loads(npm_pkg.read_text(encoding="utf-8")).get("version")
                        if _ver and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", str(_ver)):
                            pw_ver = str(_ver)
                            self.on_log(f"matching playwright {pw_ver} from Hermes npm package")
                    except Exception:
                        pass
            if not pw_ver:
                self.on_log("playwright not found in Hermes — installing latest")
            pw_spec = f"playwright=={pw_ver}" if pw_ver else "playwright"
            # Minimal cloud images: venv creation "succeeds" but yields no
            # pip (ensurepip missing) AND apt lists are empty until the first
            # `apt-get update`. Verify pip, then install pkgs and recreate.
            venv_ok = False
            for _attempt in range(2):
                if (
                    await self._sh(f"python3 -m venv {venv}")
                    and (venv / "bin" / "pip").is_file()
                ):
                    venv_ok = True
                    break
                self.on_log(
                    "venv has no pip — installing python3-venv (apt update first)..."
                )
                if not await self._sh(
                    "sudo apt-get update -qq && "
                    "sudo apt-get install -y -qq python3-venv python3-pip"
                ):
                    break
                await self._sh(f"rm -rf {venv}")
            ok = venv_ok and await self._sh(
                f"{py} -m pip install -q mitmproxy {pw_spec}"
            )
            if not ok and pw_ver:
                # npm ships patch releases PyPI never gets (e.g. npm 1.58.2
                # vs PyPI 1.58.0 -> 1.59.0). Same minor = same chromium
                # revision, so fall back to the nearest PyPI minor range.
                _mm = ".".join(pw_ver.split(".")[:2])
                _next = _mm.rsplit(".", 1)[0] + "." + str(int(_mm.split(".")[1]) + 1)
                self.on_log(
                    f"playwright=={pw_ver} not on PyPI — "
                    f"falling back to >={_mm},<{_next}"
                )
                ok = venv_ok and await self._sh(
                    f"{py} -m pip install -q mitmproxy 'playwright>={_mm},<{_next}'"
                )
            if ok:
                self.on_log(
                    "installing Chromium system deps (root) + browsers (agent user)..."
                )
                ok = await self._sh(
                    f"sudo {py} -m playwright install-deps chromium"
                )
            if ok:
                # Playwright rejects OS releases newer than it knows
                # (ubuntu26.04-x64) - override to the closest supported
                # platform so install-deps/chromium still resolve.
                ok = await self._sh(
                    f"{py} -m playwright install chromium",
                    env={
                        "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE": "ubuntu24.04-x64",
                    },
                )
            if ok:
                script = HERMES_HOME / "toolkit" / "tools" / "browser-capture.py"
                launcher = (
                    "#!/usr/bin/env bash\n"
                    f"exec {py} {script} \"$@\"\n"
                )
                ok = await self._sh(
                    f"printf '%s' {shlex.quote(launcher)} | sudo tee /usr/local/bin/browser-capture >/dev/null "
                    "&& sudo chmod +x /usr/local/bin/browser-capture"
                )
            return ok

        if key == "mobile":
            wanted = [t for t in ("apktool", "jadx", "frida") if tools.get(t)]
            if not wanted:
                return True
            # Each tool: try documented install paths, then JUDGE BY REALITY
            # (tool on PATH). Never let an expected failure (e.g. jadx is not
            # in Ubuntu repos anymore) or a resolver warning mark the step
            # failed when the tool actually landed.
            if "apktool" in wanted and not tool_path("apktool"):
                self.on_log("installing apktool ...")
                await self._sh("sudo apt-get install -y -qq apktool")
                if not tool_path("apktool"):
                    await self._sh(
                        "cd /tmp && curl -fsSL -o apktool.jar "
                        "https://github.com/iBotPeaches/Apktool/releases/latest/download/apktool.jar "
                        "&& sudo cp apktool.jar /usr/local/bin/ && printf '#!/usr/bin/env bash\\nexec java -jar /usr/local/bin/apktool.jar \"$@\"\\n' | sudo tee /usr/local/bin/apktool >/dev/null "
                        "&& sudo chmod +x /usr/local/bin/apktool"
                    )
            if "jadx" in wanted and not tool_path("jadx"):
                self.on_log("installing jadx ...")
                # jadx is NOT in Ubuntu repos (dropped after 22.04) - the apt
                # attempt logs "Unable to locate" but the GitHub release below
                # is the real install path. Install the JRE first.
                await self._sh(
                    "sudo apt-get install -y -qq openjdk-17-jre-headless"
                )
                if not tool_path("jadx"):
                    await self._sh(
                        "cd /tmp && curl -fsSL -o jadx.zip "
                        "https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip "
                        "&& sudo unzip -o -q jadx.zip -d /opt/jadx && sudo chmod +x /opt/jadx/bin/jadx "
                        "&& sudo ln -sf /opt/jadx/bin/jadx /usr/local/bin/jadx"
                    )
            if "frida" in wanted and not tool_path("frida"):
                self.on_log("installing frida-tools + objection ...")
                # --ignore-installed: Debian's blinker has no RECORD file, so
                # pip cannot uninstall it and fails without this flag. The
                # resolver may still exit non-zero over third-party conflicts
                # (drupwn's prompt-toolkit pin) - reality check below decides.
                await self._sh(
                    "sudo python3 -m pip install --break-system-packages "
                    "--ignore-installed -q frida-tools objection"
                )
                if tool_path("frida") and tool_path("objection"):
                    self.on_log("frida-tools + objection ready")
            missing = [t for t in wanted if not tool_path(t)]
            if missing:
                self.on_log(f"mobile tools still missing: {', '.join(missing)}")
                return False
            return True

        if key == "memory":
            enabled = bool(self.data.get("memory", True))
            cfg = HERMES_HOME / "config.yaml"
            if not cfg.is_file():
                self.on_log("config.yaml missing — memory step skipped")
                return False
            text = cfg.read_text(encoding="utf-8")
            if enabled:
                text = ensure_holographic_memory(text)
                cfg.write_text(text, encoding="utf-8")
                self.on_log(
                    "local memory enabled (Holographic / SQLite) — no server, "
                    "no API keys, no downloads"
                )
                return True
            # disabled: strip the provider key + hermes-memory-store plugin block
            cfg.write_text(strip_holographic_memory(text), encoding="utf-8")
            self.on_log("local memory provider disabled — removed from config.yaml")
            return True

        if key == "knowledge":
            if not PACK_DIR.is_dir():
                self.on_log(f"knowledge pack not found at {PACK_DIR}")
                return False
            HERMES_HOME.mkdir(parents=True, exist_ok=True)
            for name in ("SOUL.md", "config.template.yaml", "PERSONA.md.template"):
                src = PACK_DIR / name
                if src.is_file():
                    shutil.copy2(src, HERMES_HOME / name)
            src_skills = PACK_DIR / "skills"
            if src_skills.is_dir():
                mode = self.data.get("skills_mode", "minimal")
                if mode != "minimal":
                    self.on_log(
                        "skills_mode 'full' accepted — installing the bundled CyberStrike library"
                    )
                # Operational skills (lean) -> ~/.hermes/skills. Hermes
                # registers every SKILL.md there as a slash command, so the
                # 7k+ cyberstrike library MUST NOT live here (it blows up the
                # first-conversation context). It goes to ~/.hermes/knowledge.
                skills_dest = HERMES_HOME / "skills"
                skills_dest.mkdir(parents=True, exist_ok=True)
                for entry in src_skills.iterdir():
                    if entry.name == "cyberstrike":
                        continue
                    if entry.is_dir():
                        shutil.copytree(
                            entry, skills_dest / entry.name, dirs_exist_ok=True
                        )
                    else:
                        shutil.copy2(entry, skills_dest / entry.name)
                lib_src = src_skills / "cyberstrike"
                if lib_src.is_dir():
                    shutil.copytree(
                        lib_src,
                        HERMES_HOME / "knowledge" / "cyberstrike",
                        dirs_exist_ok=True,
                    )
                    self.on_log(
                        "cyberstrike library -> ~/.hermes/knowledge/cyberstrike "
                        "(not registered as commands; opened on demand)"
                    )
                self.on_log(
                    "skills: operational skills registered; CyberStrike library "
                    "on demand — no context cost"
                )
            src_toolkit = PACK_DIR / "toolkit"
            if src_toolkit.is_dir():
                shutil.copytree(src_toolkit, HERMES_HOME / "toolkit", dirs_exist_ok=True)
            # Windows checkouts can carry CRLF line endings, which breaks bash
            # scripts (e.g. toolkit-scan.sh). Normalize .sh files in the distro.
            await self._sh(
                f"find {shlex.quote(str(HERMES_HOME / 'toolkit'))} "
                f"{shlex.quote(str(HERMES_HOME / 'skills'))} "
                f"{shlex.quote(str(HERMES_HOME / 'knowledge'))} -name '*.sh' "
                "-exec sed -i 's/\\r$//' {} +"
            )
            idx = HERMES_HOME / "toolkit" / "tools" / "build-skills-index.py"
            if idx.is_file():
                await self._sh(
                    f"python3 {shlex.quote(str(idx))} --skills {shlex.quote(str(HERMES_HOME / 'skills'))}"
                )
            return True

        if key == "config":
            return self._write_configs()

        if key == "sudoers":
            mode = self.data.get("sudo_mode", "restricted")
            if mode == "none":
                self.on_log("sudo mode: none — skipping sudoers")
                return True
            user = getpass.getuser()
            if mode == "wide":
                line = f"{user} ALL=(ALL) NOPASSWD: SETENV: ALL"
            else:
                line = (
                    f"{user} ALL=(ALL) NOPASSWD: SETENV: /usr/sbin/openvpn, /usr/bin/systemctl, "
                    "/usr/bin/apt, /usr/bin/apt-get, /usr/bin/nmap, /usr/sbin/tcpdump, /usr/bin/docker"
                )
            dest = f"/etc/sudoers.d/hermes-{user}"
            tmp = "/tmp/hermes-sudoers"
            return await self._sh(
                f"printf '%s\\n' '{line}' > {tmp} "
                f"&& sudo install -m 440 -o root -g root {tmp} {dest} "
                f"&& rm -f {tmp}"
            )

        if key == "toolkit":
            scanner = HERMES_HOME / "toolkit" / "toolkit-scan.sh"
            if not scanner.is_file():
                self.on_log("toolkit scanner missing")
                return False
            os.chmod(scanner, 0o755)
            ok = await self._sh(f"bash {scanner}")
            if shutil.which("crontab"):
                await self._sh(
                    f'( crontab -l 2>/dev/null | grep -v "toolkit-scan" ; '
                    f'echo "17 * * * * bash {scanner} >/dev/null 2>&1" ) | crontab -'
                )
            return ok

        if key == "gateway":
            if not self.data["secrets"].get("bot"):
                self.on_log("no bot token — gateway skipped")
                return True
            if not tool_path("hermes"):
                self.on_log("hermes not installed — gateway skipped")
                return False
            env = {"XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
            # hermes treats a TTY stdin as interactive and blocks on prompts
            # (e.g. "start now?"). /dev/null forces its non-interactive path.
            ok = await self._sh("hermes gateway install < /dev/null", env=env)
            # ALWAYS restart, never just start: Hermes' install.sh launched
            # the gateway mid-install while ~/.hermes files (state.db among
            # them) were still being replaced - the early process holds fds
            # to DELETED inodes and every write then fails with
            # "attempt to write a readonly database". A fresh restart opens
            # clean handles on the final files.
            ok = await self._sh("hermes gateway restart < /dev/null", env=env) and ok
            return ok

        if key == "webui":
            if not self.data.get("webui", True):
                self.on_log("webui skipped (disabled)")
                return True
            home = Path.home()
            webui_dir = home / "hermes-webui"
            host = str(self.data.get("webui_host", "0.0.0.0"))
            port = str(self.data.get("webui_port", "8787"))
            if (webui_dir / "ctl.sh").is_file():
                self.on_log("hermes-webui already present — skipping clone")
            else:
                self.on_log("cloning hermes-webui (browser dashboard)...")
                ok = await self._sh(
                    "git clone --depth 1 https://github.com/nesquena/hermes-webui.git "
                    f"{shlex.quote(str(webui_dir))}"
                )
                if not ok:
                    self.on_log("hermes-webui clone failed")
                    return False
            env = {"HERMES_WEBUI_HOST": host, "HERMES_WEBUI_PORT": port}
            # Port isolation: a stale WebUI process from a previous install
            # may still hold the port. Kill anything listening on it first,
            # then fall back to the next free port if a foreign app owns it.
            await self._sh(
                f"fuser -k {port}/tcp 2>/dev/null; sleep 1; true"
            )
            for attempt in range(5):
                probe = await self._sh(
                    f"(ss -tln 2>/dev/null || netstat -tln 2>/dev/null) "
                    f"| grep -q ':{port} '"
                )
                if not probe:
                    break
                self.on_log(
                    f"port {port} busy — trying {int(port) + 1}"
                )
                port = str(int(port) + 1)
                env["HERMES_WEBUI_PORT"] = port
            # keep the summary in sync with the port that actually launched
            self.data["webui_port"] = port
            self.on_log(
                "starting WebUI daemon (first run builds a venv — may take a minute)..."
            )
            ok = await self._sh(
                f"cd {shlex.quote(str(webui_dir))} && ./ctl.sh start", env=env
            )
            if not ok:
                self.on_log("WebUI failed to start — see ~/.hermes/webui.log")
                return False
            url = f"http://{host}:{port}"
            for _attempt in range(12):
                if await self._sh(f"curl -fsS -m 2 '{url}/health' >/dev/null 2>&1"):
                    self.on_log(f"WebUI ready at {url}")
                    self.data["webui_url"] = url
                    return True
                await asyncio.sleep(1)
            self.on_log(
                f"WebUI daemon started, but health check timed out — try {url}"
            )
            self.data["webui_url"] = url
            return True

        return True

    # ── config / secrets writing (live) ────────────────────────────────────
    def _write_configs(self) -> bool:
        return provision_keys(self.data["secrets"], on_log=self.on_log)


# Install config loading (plain JSON or encrypted .hcfg)

def decrypt_hcfg(raw: bytes, password: str) -> bytes:
    """Decrypt a HERMESCFG1 (.hcfg) config blob with a password."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "cryptography is required to read .hcfg files "
            "(pip install cryptography)"
        ) from exc

    lines = raw.decode("utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "HERMESCFG1":
        raise ValueError("not a Hermes encrypted config (.hcfg) file")
    if len(lines) < 3:
        raise ValueError("encrypted config file is truncated")
    try:
        salt = base64.b64decode(lines[1])
    except Exception as exc:
        raise ValueError("corrupted .hcfg file (bad salt)") from exc
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    try:
        return Fernet(key).decrypt(lines[2].encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("wrong password or corrupted .hcfg file") from exc


def load_install_config(source: str, password: str = "") -> dict:
    """Load an install config from a local path or an http(s) URL.

    Accepts either a plain JSON file (install-config.json) or an encrypted
    HERMESCFG1 (.hcfg) file produced by config-tool/encrypt-config.py.
    """
    import json
    import urllib.request

    source = (source or "").strip()
    if not source:
        raise ValueError("config source is empty")

    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=30) as resp:
                raw = resp.read()
        except Exception as exc:
            raise ValueError(f"could not download config URL: {exc}") from exc
    else:
        path = Path(source).expanduser()
        if not path.is_file():
            raise ValueError(f"config file not found: {path}")
        raw = path.read_bytes()

    text = raw.decode("utf-8-sig", errors="replace")
    if text.lstrip().startswith("HERMESCFG1"):
        plain = decrypt_hcfg(raw, password)
        try:
            return json.loads(plain.decode("utf-8-sig"))
        except Exception as exc:
            raise ValueError(f"decrypted config is not valid JSON: {exc}") from exc

    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f"invalid JSON config: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data
