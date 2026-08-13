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
import shlex
import shutil
from pathlib import Path
from typing import Callable

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PACK_DIR = SCRIPT_DIR / "knowledge-pack"
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
    ("core", "deepseek", "DeepSeek API key", True, "env"),
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

SUDO_MODES = [
    ("restricted", "Restricted (recommended)", "openvpn, systemctl, apt, nmap, tcpdump, docker"),
    ("wide", "Wide (everything)", "NOPASSWD: ALL"),
    ("none", "None", "leave sudo as-is"),
]


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
        "deepseek": "DEEPSEEK_API_KEY",
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

    # 3) config.yaml (model key + home channel)
    if secrets.get("deepseek"):
        tpl = HERMES_HOME / "config.template.yaml"
        if tpl.is_file():
            text = tpl.read_text(encoding="utf-8").replace(
                "__DEEPSEEK_API_KEY__", secrets["deepseek"]
            )
            (HERMES_HOME / "config.yaml").write_text(text, encoding="utf-8")
            log("config.yaml written (model key injected)")
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
    ) -> None:
        self.data = data
        self.dry_run = dry_run
        self.sudo_password = sudo_password
        self.failed: list[str] = []
        self.on_log = on_log or (lambda _line: None)
        self.on_progress = on_progress or (lambda: None)

    async def run(self) -> None:
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

    async def _sh(self, cmd: str, env: dict | None = None) -> bool:
        full_env = dict(os.environ)
        full_env["PATH"] = f"{Path.home() / '.local/bin'}:{full_env.get('PATH', '')}"
        if env:
            full_env.update(env)
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
            text = line.decode(errors="replace").rstrip()
            if text:
                self.on_log(text)
        return (await proc.wait()) == 0

    async def _step(self, key: str) -> bool:
        tools = self.data["tools"]
        if key == "requirements":
            missing = [b for b in ("curl", "git") if shutil.which(b) is None]
            if missing:
                self.on_log(f"missing base tools: {', '.join(missing)} — installing via apt")
                return await self._sh("sudo apt-get update -qq && sudo apt-get install -y -qq curl git")
            return True

        if key == "hermes":
            if tool_path("hermes"):
                self.on_log("Hermes already installed — skipping")
                return True
            return await self._sh(
                "bash <(curl -fsSL https://hermes-agent.nousresearch.com/install.sh) --non-interactive"
            )

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
            ok = True
            if tools.get("droopescan") and not tool_path("droopescan"):
                # natural default: pip installs console scripts into the
                # system Python bin (/usr/local/bin on Ubuntu)
                ok = await self._sh(
                    "sudo python3 -m pip install --break-system-packages -q droopescan"
                ) and ok
            if tools.get("drupwn") and not tool_path("drupwn"):
                ok = await self._sh(
                    "sudo python3 -m pip install --break-system-packages -q 'setuptools<81'"
                ) and ok
                ok = await self._sh(
                    "sudo python3 -m pip install --break-system-packages -q "
                    "--no-build-isolation git+https://github.com/immunIT/drupwn"
                ) and ok
            return ok

        if key == "wpscan":
            if not tools.get("wpscan"):
                return True
            if tool_path("wpscan"):
                self.on_log("wpscan already installed — skipping")
                return True
            # standard location: system gem install puts wpscan in /usr/local/bin
            return await self._sh("sudo gem install wpscan") or await self._sh("gem install wpscan")

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
            ok = await self._sh(
                f"python3 -m venv {venv} && {py} -m pip install -q playwright mitmproxy"
            )
            if ok:
                self.on_log("installing Chromium + system deps (large download)...")
                ok = await self._sh(
                    f"sudo {py} -m playwright install --with-deps chromium"
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
            ok = True
            if "apktool" in wanted and not tool_path("apktool"):
                self.on_log("installing apktool ...")
                ok = await self._sh("sudo apt-get install -y -qq apktool") and ok
                if not tool_path("apktool"):
                    ok = await self._sh(
                        "cd /tmp && curl -fsSL -o apktool.jar "
                        "https://github.com/iBotPeaches/Apktool/releases/latest/download/apktool.jar "
                        "&& sudo cp apktool.jar /usr/local/bin/ && printf '#!/usr/bin/env bash\\nexec java -jar /usr/local/bin/apktool.jar \"$@\"\\n' | sudo tee /usr/local/bin/apktool >/dev/null "
                        "&& sudo chmod +x /usr/local/bin/apktool"
                    ) and ok
            if "jadx" in wanted and not tool_path("jadx"):
                self.on_log("installing jadx ...")
                ok = await self._sh(
                    "sudo apt-get install -y -qq openjdk-17-jre-headless jadx"
                ) and ok
                if not tool_path("jadx"):
                    ok = await self._sh(
                        "cd /tmp && curl -fsSL -o jadx.zip "
                        "https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip "
                        "&& sudo unzip -o -q jadx.zip -d /opt/jadx && sudo chmod +x /opt/jadx/bin/jadx "
                        "&& sudo ln -sf /opt/jadx/bin/jadx /usr/local/bin/jadx"
                    ) and ok
            if "frida" in wanted and not tool_path("frida"):
                self.on_log("installing frida-tools + objection ...")
                ok = await self._sh(
                    "sudo python3 -m pip install --break-system-packages -q frida-tools objection"
                ) and ok
            return ok

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
                shutil.copytree(
                    src_skills,
                    HERMES_HOME / "skills",
                    dirs_exist_ok=True,
                )
                self.on_log(
                    "skills: custom + CyberStrike library (index-only, loaded on demand — no token cost)"
                )
            src_toolkit = PACK_DIR / "toolkit"
            if src_toolkit.is_dir():
                shutil.copytree(src_toolkit, HERMES_HOME / "toolkit", dirs_exist_ok=True)
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
                line = f"{user} ALL=(ALL) NOPASSWD: ALL"
            else:
                line = (
                    f"{user} ALL=(ALL) NOPASSWD: /usr/sbin/openvpn, /usr/bin/systemctl, "
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
            ok = await self._sh("hermes gateway install", env=env)
            ok = await self._sh("hermes gateway start", env=env) and ok
            return ok

        if key == "webui":
            if not self.data.get("webui", True):
                self.on_log("webui skipped (disabled)")
                return True
            home = Path.home()
            webui_dir = home / "hermes-webui"
            host = str(self.data.get("webui_host", "127.0.0.1"))
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
