#!/usr/bin/env python3
"""
installer-tui.py - Houdini Gateway Installer (Textual TUI)

Professional terminal wizard: dark neural theme, step sidebar, ContentSwitcher
steps, category switchers for tools/secrets, encrypted-config loading (local
path or URL), masked secrets, live install with streaming progress.

The installation engine lives in installer_core.py (shared).

Usage:
    python3 installer-tui.py             # interactive (sudo password may be asked once)
    python3 installer-tui.py --selftest  # headless UI walkthrough (dry-run)
"""

from __future__ import annotations

import asyncio
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.renderables.gradient import LinearGradient
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    Static,
    Tab,
    Tabs,
)

from installer_core import (
    HERMES_HOME,
    INSTALL_STEP_COUNT,
    MODEL_PROVIDERS,
    SECRET_FIELDS,
    SECRET_GROUPS,
    SUDO_MODES,
    TOOLS,
    LiveInstaller,
    load_install_config,
    mask,
    model_choices,
    tool_path,
)

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
# gruvbox palette
CYAN = "#8EC07C"      # aqua
BLUE = "#83A598"
VIOLET = "#D3869B"    # purple
EMERALD = "#B8BB26"   # green
AMBER = "#FABD2F"     # yellow
ORANGE = "#FE8019"
RED = "#FB4934"
SLATE = "#D5C4A1"     # fg2
SLATE_DIM = "#BDAE93" # fg3
SLATE_FAINT = "#928374"  # gray

TOOL_CAT_LABELS = {
    "pd": "ProjectDiscovery",
    "apt": "System / APT",
    "extra": "Web scanners",
    "uv": "uv tools",
    "ngrok": "Tunnels",
    "browser": "Browser capture",
    "mobile": "Mobile / APK",
}
TOOL_CATS = list(dict.fromkeys(cat for _name, _desc, cat in TOOLS))

STEP_DEFS = [
    ("welcome", "Welcome"),
    ("config", "Load config"),
    ("core", "Core setup"),
    ("decide", "Options"),
    ("tools", "Toolchain"),
    ("secrets", "Secrets"),
    ("sudo", "Permissions"),
    ("webui", "WebUI"),
    ("memory", "Memory"),
    ("review", "Review"),
    ("install", "Install"),
    ("summary", "Summary"),
]

STEP_HINTS = {
    "welcome": "Press Start Installation to begin.",
    "config": "Optional: paste a local path or an http(s) URL, then Load & Apply.",
    "core": "Required: pick an AI provider, choose the model and enter its API key. Bot token starts the gateway. Everything else can be added later.",
    "decide": "All tools install by default. Continue to customize, or Quick Install with defaults.",
    "tools": "Pick a tool category on the left; check the tools you want.",
    "secrets": "One key per service; empty fields are skipped and added later.",
    "sudo": "Permission scope written to /etc/sudoers.d - no password stored.",
    "webui": "Browser dashboard installed side-by-side; final URL shown in summary.",
    "memory": "Local SQLite memory (Holographic) - enabled by default, zero downloads.",
    "review": "Confirm everything before installation starts.",
    "install": "Live installation stream - this may take several minutes.",
    "summary": "Installation finished. Next steps below.",
}


# --------------------------------------------------------------------------
# Wizard screen (master-detail + ContentSwitcher steps)
# --------------------------------------------------------------------------
class WizardScreen(Screen):
    """Sidebar steps + content area. Every step is a ContentSwitcher pane."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="root"):
            with Vertical(id="sidebar"):
                yield Static("HOUDINI", id="logo")
                yield Static("BOOTSTRAP INSTALLER", id="subtitle")
                yield Static("", id="side_gradient")
                yield ProgressBar(total=len(STEP_DEFS), show_eta=False, id="side_progress")
                yield Static("", id="status_line")
            with Vertical(id="content"):
                yield Static("", id="content_title")
                yield Tabs(
                    *[Tab(label, id=key) for key, label in STEP_DEFS],
                    id="step_tabs",
                )
                with ContentSwitcher(id="steps"):
                    with Vertical(id="step-welcome", classes="step"):
                        yield Static("", id="welcome_gradient")
                        yield Static(
                            "      /\\\n"
                            "     /  \\\n"
                            "    / /\\ \\\n"
                            "   / /__\\ \\\n"
                            "  /________\\\n"
                            " /__________\\\n"
                            "/____________\\\n"
                            "\\____________/",
                            id="hat_logo",
                        )
                        yield Static(
                            "█ █ ███ █ █ ██  ███ █ █\n"
                            "███ █ █ █ █ █ █  █   ███\n"
                            "█ █ ███ █ █ ██  ███ █ █",
                            id="content_logo",
                        )
                        yield Static(
                            "The security wizard for testing web apps & sites",
                            id="content_sub",
                        )
                        yield Static(
                            "الساحر هوديني — مساعدك الأمني لفحص التطبيقات والمواقع",
                            id="welcome_arabic",
                        )
                        yield Static(
                            f"- [{EMERALD}]+[/] Live apt / binary installation\n"
                            f"- [{EMERALD}]+[/] Dynamic tool & key inventory\n"
                            f"- [{EMERALD}]+[/] Masked secrets entry\n"
                            f"- [{EMERALD}]+[/] Encrypted config load (path or URL)\n"
                            f"- [{EMERALD}]+[/] Gateway ready on first run",
                            id="welcome_features",
                        )
                        yield Button(
                            "Start Installation",
                            id="welcome_start",
                            variant="primary",
                        )
                        yield Static(
                            f"[{SLATE}]Your sudo password may be requested once during installation.[/]",
                            id="welcome_note",
                        )
                    with Vertical(id="step-config", classes="step"):
                        yield Static(
                            "Load a saved config (optional): local path or http(s) URL.\n"
                            "Plain JSON and password-encrypted .hcfg are both accepted.",
                            classes="hint",
                        )
                        yield Input(
                            placeholder="C:\\path\\install-config.hcfg  or  https://host/install-config.hcfg",
                            id="cfg_source",
                        )
                        yield Input(
                            placeholder="Decryption password (only for .hcfg)",
                            password=True,
                            id="cfg_password",
                        )
                        with Horizontal(id="cfg_row"):
                            yield Button("Load & Apply", id="cfg_load", variant="primary")
                            yield Button("Skip", id="cfg_skip", variant="default")
                        yield Static("", id="cfg_status")
                    with Vertical(id="step-core", classes="step"):
                        yield Static(
                            "Pick an AI provider, choose the model and enter its "
                            "API key.\nThe Telegram bot token is needed for the "
                            "gateway to start.\nEverything else (home channel, API "
                            "keys, tools) can be added or detected later.",
                            classes="hint",
                        )
                        yield RadioSet(
                            *[p["label"] for p in MODEL_PROVIDERS.values()],
                            id="model_providers",
                        )
                        yield Input(
                            placeholder="Base URL (auto-filled for presets; required for Custom)",
                            id="model_base_url",
                        )
                        yield Input(
                            placeholder="API key (sk-...)",
                            password=True,
                            id="api_key",
                        )
                        yield Select(
                            [],
                            prompt="Model list (live - click to pick)",
                            allow_blank=True,
                            disabled=True,
                            id="model_select",
                        )
                        yield Input(
                            placeholder="Model ID (pick from the list or type custom)",
                            id="model",
                        )
                        yield Input(
                            placeholder="Telegram bot token (@BotFather)",
                            password=True,
                            id="bot",
                        )
                        yield Static("", id="core_status")
                    with Vertical(id="step-decide", classes="step"):
                        yield Static(
                            "All tools install by default with the full toolkit.\n"
                            "Choose how to proceed:",
                            classes="hint",
                        )
                        with Horizontal(id="decide_row"):
                            yield Button(
                                "Continue & customize",
                                id="decide_custom",
                                variant="primary",
                            )
                            yield Button(
                                "Quick install (defaults)",
                                id="decide_quick",
                                variant="default",
                            )
                    with Vertical(id="step-tools", classes="step"):
                        yield Static("Tool categories - pick one to see its tools.", classes="hint")
                        with Horizontal(id="tools_split"):
                            yield ListView(id="tool_cats")
                            with ContentSwitcher(id="tool_panes"):
                                for cat in TOOL_CATS:
                                    with Vertical(id=f"tool_pane_{cat}", classes="pane"):
                                        for name, desc, _cat in TOOLS:
                                            if _cat == cat:
                                                yield Checkbox(
                                                    f"{name}  -  {desc}",
                                                    value=True,
                                                    id=f"tool_{name}",
                                                )
                    with Vertical(id="step-secrets", classes="step"):
                        yield Static("Provider groups - one key per service.", classes="hint")
                        with Horizontal(id="secrets_split"):
                            yield ListView(id="secret_groups")
                            with ContentSwitcher(id="secret_panes"):
                                for group, glabel in SECRET_GROUPS:
                                    with Vertical(id=f"secret_pane_{group}", classes="pane"):
                                        for g2, fid, label, secret, _targets in SECRET_FIELDS:
                                            if g2 == group and fid not in (
                                                "model_provider",
                                                "model",
                                                "model_base_url",
                                                "api_key",
                                                "bot",
                                            ):
                                                yield Input(placeholder=label, password=secret, id=fid)
                    with Vertical(id="step-sudo", classes="step"):
                        yield Static(
                            "Permissions go to /etc/sudoers.d with your username - no password is stored.",
                            classes="hint",
                        )
                        yield RadioSet(*[label for _key, label, _d in SUDO_MODES], id="sudo_modes")
                        yield Static("", id="sudo_detail")
                    with Vertical(id="step-webui", classes="step"):
                        yield Static(
                            "Hermes WebUI (dark browser dashboard) installs side-by-side "
                            "with the gateway and reads the same ~/.hermes config.",
                            classes="hint",
                        )
                        yield Checkbox(
                            "Install Hermes WebUI (browser dashboard)",
                            value=True,
                            id="webui_enable",
                        )
                        yield Input(
                            placeholder="Host (default 127.0.0.1)",
                            value="127.0.0.1",
                            id="webui_host",
                        )
                        yield Input(
                            placeholder="Port (default 8787)",
                            value="8787",
                            id="webui_port",
                        )
                        yield Static(
                            f"[{SLATE_DIM}]Final link http://127.0.0.1:8787 appears in the summary.[/]",
                            id="webui_note",
                        )
                    with Vertical(id="step-memory", classes="step"):
                        yield Static(
                            "Long-term memory runs fully local on SQLite "
                            "(Holographic provider): FTS5 search, trust scoring, "
                            "entity resolution.\nNo server, no API keys, no model "
                            "downloads - facts are stored on demand via fact_store\n"
                            "and mirrored from built-in memory writes.",
                            classes="hint",
                        )
                        yield Checkbox(
                            "Enable local memory (Holographic / SQLite)",
                            value=True,
                            id="memory_enable",
                        )
                        yield Static(
                            f"[{SLATE_DIM}]DB: ~/.hermes/memory_store.db - "
                            "auto-extract off, keeps MEMORY.md lean.[/]",
                            id="memory_note",
                        )
                    with Vertical(id="step-review", classes="step"):
                        yield DataTable(id="review_table", zebra_stripes=True)
                    with Vertical(id="step-install", classes="step"):
                        yield ProgressBar(total=INSTALL_STEP_COUNT, show_eta=False, id="prog")
                        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                    with Vertical(id="step-summary", classes="step"):
                        yield RichLog(id="summary_log", highlight=True, markup=True, wrap=True)
                yield Static("", id="content_hint")
                with Horizontal(id="content_nav"):
                    yield Button("Back", id="back", variant="default")
                    yield Button("Next", id="next", variant="primary")
        yield Footer()

    async def on_mount(self) -> None:
        self.current = "welcome"
        self.config_loaded = False
        self.install_done = False
        self._refresh_timer = None

        self.query_one("#tool_cats", ListView).extend(
            [ListItem(Static(TOOL_CAT_LABELS.get(c, c))) for c in TOOL_CATS]
        )
        self.query_one("#secret_groups", ListView).extend(
            [ListItem(Static(label)) for _key, label in SECRET_GROUPS]
        )
        self.query_one("#tool_panes", ContentSwitcher).current = f"tool_pane_{TOOL_CATS[0]}"
        self.query_one("#secret_panes", ContentSwitcher).current = f"secret_pane_{SECRET_GROUPS[0][0]}"
        self.query_one("#tool_cats", ListView).index = 0
        self.query_one("#secret_groups", ListView).index = 0

        try:
            self.query_one("#side_gradient", Static).update(
                LinearGradient(90, [(0.0, BLUE), (0.55, VIOLET), (1.0, CYAN)])
            )
        except Exception:
            pass

        mode_label = next(label for key, label, _d in SUDO_MODES if key == self.app.data["sudo_mode"])
        self._select_radio("sudo_modes", mode_label)
        self._select_radio("model_providers", MODEL_PROVIDERS["deepseek"]["label"])
        self._apply_model_preset("deepseek")

        await self._show("welcome")

    # ------------------------------------------------------------------ nav
    def _step_index(self, key: str) -> int:
        return next(i for i, (k, _l) in enumerate(STEP_DEFS) if k == key)

    async def _show(self, step: str) -> None:
        self.current = step
        idx = self._step_index(step)
        title = next(l for k, l in STEP_DEFS if k == step)
        self.query_one("#content_title", Static).update(
            f"[bold {CYAN}]STEP {idx + 1}/{len(STEP_DEFS)} - {title.upper()}[/]"
        )
        self.query_one("#steps", ContentSwitcher).current = f"step-{step}"
        self.query_one("#content_hint", Static).update(
            f"[{SLATE}]{STEP_HINTS.get(step, '')}[/]"
        )
        if step == "welcome":
            try:
                self.query_one("#welcome_gradient", Static).update(
                    LinearGradient(90, [(0.0, BLUE), (0.55, VIOLET), (1.0, CYAN)])
                )
            except Exception:
                pass
        self._update_sidebar()
        self._update_nav()
        if step == "review":
            self._fill_review()
        if step == "summary":
            self._fill_summary()

    def _update_sidebar(self) -> None:
        idx = self._step_index(self.current)
        self.query_one("#step_tabs", Tabs).active = self.current
        self.query_one("#side_progress", ProgressBar).progress = idx
        current_label = STEP_DEFS[idx][1].upper()
        self.query_one("#status_line", Static).update(
            f"[{SLATE}]STEP {idx + 1}/{len(STEP_DEFS)} | {current_label}[/]"
        )

    def _update_nav(self) -> None:
        back = self.query_one("#back", Button)
        nxt = self.query_one("#next", Button)
        step = self.current
        back.disabled = step in ("welcome", "install", "summary")
        if step == "welcome":
            nxt.label = "Start >"
            nxt.variant = "primary"
            nxt.disabled = False
        elif step == "summary":
            nxt.label = "Exit"
            nxt.variant = "success"
            nxt.disabled = False
        elif step == "install":
            nxt.disabled = False
            if self.install_done:
                nxt.label = "Summary >"
                nxt.variant = "success"
            else:
                nxt.label = "Start installation"
                nxt.variant = "primary"
        elif step == "decide":
            nxt.disabled = True
            nxt.label = "Next >"
            nxt.variant = "primary"
        else:
            nxt.label = "Next >"
            nxt.variant = "primary"
            nxt.disabled = False

    # ------------------------------------------------------------- buttons
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        idx = self._step_index(self.current)

        if bid == "back" and idx > 0 and self.current not in ("install", "summary"):
            self._collect_current()
            await self._show(STEP_DEFS[idx - 1][0])
            return
        if bid == "cfg_load":
            self.run_worker(self._load_config(), exclusive=True)
            return
        if bid == "cfg_skip":
            await self._show("core")
            return
        if bid == "decide_custom":
            self._collect_current()
            await self._show("tools")
            return
        if bid == "decide_quick":
            self._collect_current()
            self._quick_defaults()
            await self._show("review")
            return
        if bid == "welcome_start":
            await self._show("config")
            return
        if bid != "next":
            return

        if self.current == "welcome":
            await self._show("config")
        elif self.current == "config":
            src = self.query_one("#cfg_source", Input).value.strip()
            if src and not self.config_loaded:
                self.query_one("#cfg_status", Static).update(
                    f"[{AMBER}]A config source is set but not loaded - press Load & Apply (or clear the field).[/]"
                )
                return
            await self._show("core")
        elif self.current == "core":
            if self._selected_provider() == "custom":
                missing = []
                if not self.query_one("#model_base_url", Input).value.strip():
                    missing.append("Base URL")
                if not self.query_one("#api_key", Input).value.strip():
                    missing.append("API key")
                if not self.query_one("#model", Input).value.strip():
                    missing.append("Model ID")
                if missing:
                    self.query_one("#core_status", Static).update(
                        f"[{RED}]Custom provider: fill {', '.join(missing)} "
                        "before continuing.[/]"
                    )
                    return
            self.query_one("#core_status", Static).update("")
            self._collect_core()
            await self._show("decide")
        elif self.current == "tools":
            self._collect_tools()
            await self._show("secrets")
        elif self.current == "secrets":
            self._collect_secrets()
            await self._show("sudo")
        elif self.current == "sudo":
            await self._show("webui")
        elif self.current == "webui":
            self._collect_webui()
            await self._show("memory")
        elif self.current == "memory":
            self._collect_memory()
            await self._show("review")
        elif self.current == "review":
            await self._show("install")
        elif self.current == "install":
            if self.install_done:
                await self._show("summary")
            else:
                self.query_one("#next", Button).disabled = True
                self.run_worker(self._run_install(), exclusive=True)
        elif self.current == "summary":
            self.app.exit()

    # ------------------------------------------------------- config load
    async def _load_config(self) -> None:
        src = self.query_one("#cfg_source", Input).value.strip()
        pw = self.query_one("#cfg_password", Input).value
        status = self.query_one("#cfg_status", Static)
        btn = self.query_one("#cfg_load", Button)
        if not src:
            status.update(f"[{AMBER}]Enter a path or URL first.[/]")
            return
        btn.disabled = True
        status.update(f"[{SLATE}]Loading config ...[/]")
        try:
            cfg = await asyncio.to_thread(load_install_config, src, pw)
        except Exception as exc:
            status.update(f"[{RED}]x {exc}[/]")
            btn.disabled = False
            self.config_loaded = False
            return
        self._apply_config(cfg)
        n_tools = sum(1 for n, _d, _c in TOOLS if self.app.data["tools"].get(n))
        status.update(
            f"[{EMERALD}]v Loaded - {n_tools} tools, {self.app.data['secrets_count']} secrets, "
            f"sudo={self.app.data['sudo_mode']}, persona=first-contact[/]"
        )
        btn.disabled = False

    def _apply_config(self, cfg: dict) -> None:
        tools_cfg = cfg.get("tools") or {}
        for name, _desc, _cat in TOOLS:
            if name in tools_cfg:
                self.query_one(f"#tool_{name}", Checkbox).value = bool(tools_cfg[name])

        secrets_cfg = cfg.get("secrets") or {}
        count = 0
        core_inputs = {"model", "model_base_url", "api_key", "bot"}
        for _g, fid, _label, _secret, _targets in SECRET_FIELDS:
            val = str(secrets_cfg.get(fid, "") or "").strip()
            if val:
                if fid == "model_provider":
                    provider = val.lower()
                    if provider in MODEL_PROVIDERS:
                        self._select_radio(
                            "model_providers",
                            MODEL_PROVIDERS[provider]["label"],
                        )
                        self._apply_model_preset(provider)
                elif fid in ("model", "model_base_url"):
                    self.query_one(f"#{fid}", Input).value = val
                elif fid in core_inputs:
                    self.query_one(f"#{fid}", Input).value = val
                    count += 1
                else:
                    self.query_one(f"#{fid}", Input).value = val
                    count += 1
        self.app.data["secrets_count"] = count

        mode = cfg.get("sudo_mode")
        if any(mode == k for k, _l, _d in SUDO_MODES):
            self.app.data["sudo_mode"] = mode
            self._select_radio(
                "sudo_modes",
                next(label for k, label, _d in SUDO_MODES if k == mode),
            )

        if "webui" in cfg:
            self.app.data["webui"] = bool(cfg["webui"])
            self.query_one("#webui_enable", Checkbox).value = bool(cfg["webui"])
        if cfg.get("webui_host"):
            self.app.data["webui_host"] = str(cfg["webui_host"])
            self.query_one("#webui_host", Input).value = str(cfg["webui_host"])
        if cfg.get("webui_port"):
            self.app.data["webui_port"] = str(cfg["webui_port"])
            self.query_one("#webui_port", Input).value = str(cfg["webui_port"])

        if "memory" in cfg:
            self.app.data["memory"] = bool(cfg["memory"])
            self.query_one("#memory_enable", Checkbox).value = bool(cfg["memory"])

        self.config_loaded = True

    def _select_radio(self, rid: str, label: str) -> None:
        try:
            rs = self.query_one(f"#{rid}", RadioSet)
        except Exception:
            return
        for rb in rs.query(RadioButton):
            try:
                if rb.label is not None and rb.label.plain == label:
                    rb.value = True
                    break
            except Exception:
                continue

    def _apply_model_preset(self, provider: str, refresh: bool = True) -> None:
        preset = MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS["custom"])
        model_input = self.query_one("#model", Input)
        base_input = self.query_one("#model_base_url", Input)
        select = self.query_one("#model_select", Select)
        defaults = {p["default_model"] for p in MODEL_PROVIDERS.values()}
        current = model_input.value.strip()
        if not current or current in defaults:
            model_input.value = preset["default_model"]
        model_input.placeholder = "Model ID (pick from the list or type custom)"
        select.set_options(
            [(m, m) for m in preset.get("preset_models", [])]
            + [("Custom... (type below)", "__custom__")]
        )
        select.disabled = False
        if provider == "custom":
            base_input.placeholder = "Base URL (required for custom endpoints)"
        else:
            base_input.placeholder = "Base URL (auto-filled)"
            base_input.value = preset["base_url"]
        if (
            refresh
            and not self.app.dry_run
            and self.query_one("#api_key", Input).value.strip()
        ):
            self.run_worker(self._refresh_model_list(provider))

    def _selected_provider(self) -> str:
        rs = self.query_one("#model_providers", RadioSet)
        for rb in rs.query(RadioButton):
            if rb.value and rb.label is not None:
                lbl = rb.label.plain
                return next(
                    (k for k, p in MODEL_PROVIDERS.items() if p["label"] == lbl),
                    "custom",
                )
        return "deepseek"

    async def _refresh_model_list(self, provider: str) -> None:
        """Live model catalog from the provider endpoint (curated fallback)."""
        if self.app.dry_run:
            return
        preset = MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS["custom"])
        base_url = (
            self.query_one("#model_base_url", Input).value.strip()
            or preset["base_url"]
        )
        api_key = self.query_one("#api_key", Input).value.strip()
        if not base_url or not api_key:
            return
        models = await asyncio.to_thread(model_choices, provider, base_url, api_key)
        if not models:
            return  # keep curated presets
        if self._selected_provider() != provider:
            return  # stale result - provider changed while fetching
        select = self.query_one("#model_select", Select)
        select.set_options(
            [(m, m) for m in models] + [("Custom... (type below)", "__custom__")]
        )

    # ------------------------------------------------------- data collect
    def _collect_tools(self) -> None:
        for name, _desc, _cat in TOOLS:
            self.app.data["tools"][name] = self.query_one(f"#tool_{name}", Checkbox).value

    def _count_secrets(self) -> int:
        return sum(
            1
            for k, v in self.app.data.get("secrets", {}).items()
            if k not in ("model_provider", "model", "model_base_url")
            and str(v or "").strip()
        )

    def _collect_core(self) -> None:
        secrets = self.app.data["secrets"]
        provider = self._selected_provider()
        select = self.query_one("#model_select", Select)
        if select.value not in (Select.BLANK, Select.NULL, "__custom__"):
            model_input = self.query_one("#model", Input)
            if not model_input.value.strip():
                model_input.value = str(select.value)
        self._apply_model_preset(provider, refresh=False)
        secrets["model_provider"] = provider
        secrets["model"] = self.query_one("#model", Input).value.strip()
        secrets["model_base_url"] = self.query_one(
            "#model_base_url", Input
        ).value.strip()
        secrets["api_key"] = self.query_one("#api_key", Input).value.strip()
        secrets["bot"] = self.query_one("#bot", Input).value.strip()
        self.app.data["secrets_count"] = self._count_secrets()

    def _collect_secrets(self) -> None:
        for _group, fid, _label, _secret, _targets in SECRET_FIELDS:
            if fid in ("model_provider", "model", "model_base_url", "api_key", "bot"):
                continue
            self.app.data["secrets"][fid] = self.query_one(f"#{fid}", Input).value.strip()
        self.app.data["secrets_count"] = self._count_secrets()

    def _quick_defaults(self) -> None:
        for name, _desc, _cat in TOOLS:
            self.app.data["tools"][name] = True

    def _collect_webui(self) -> None:
        self.app.data["webui"] = self.query_one("#webui_enable", Checkbox).value
        host = self.query_one("#webui_host", Input).value.strip() or "127.0.0.1"
        port = self.query_one("#webui_port", Input).value.strip() or "8787"
        self.app.data["webui_host"] = host
        self.app.data["webui_port"] = port

    def _collect_memory(self) -> None:
        self.app.data["memory"] = self.query_one("#memory_enable", Checkbox).value

    def _collect_current(self) -> None:
        """Persist the current step's inputs before navigating away (tabs/back)."""
        if self.current == "core":
            self._collect_core()
        elif self.current == "tools":
            self._collect_tools()
        elif self.current == "secrets":
            self._collect_secrets()
        elif self.current == "webui":
            self._collect_webui()
        elif self.current == "memory":
            self._collect_memory()

    # ------------------------------------------------------------ events
    @staticmethod
    def _list_item_label(item) -> str:
        try:
            static = item.query_one(Static)
            renderable = getattr(static, "renderable", "")
            return getattr(renderable, "plain", str(renderable))
        except Exception:
            return ""

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        prompt = self._list_item_label(event.item) if event.item is not None else ""
        if prompt in TOOL_CAT_LABELS.values():
            cat = next(c for c, label in TOOL_CAT_LABELS.items() if label == prompt)
            self.query_one("#tool_panes", ContentSwitcher).current = f"tool_pane_{cat}"
        elif prompt in [label for _k, label in SECRET_GROUPS]:
            group = next(k for k, label in SECRET_GROUPS if label == prompt)
            self.query_one("#secret_panes", ContentSwitcher).current = f"secret_pane_{group}"

    async def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab = getattr(event, "tab", None)
        tid = getattr(tab, "id", None)
        if not tid or tid not in [k for k, _l in STEP_DEFS]:
            return
        if self.current == "install" and not self.install_done:
            return  # do not leave the live-install step mid-run
        if tid == "summary" and not self.install_done:
            return
        self._collect_current()
        await self._show(tid)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        rs = getattr(event, "radio_set", None)
        rid = getattr(rs, "id", None) if rs is not None else None
        pressed = getattr(event, "pressed", None)
        value = (
            getattr(pressed.label, "plain", str(pressed.label))
            if pressed is not None
            else getattr(event, "value", "")
        )
        if rid == "sudo_modes":
            for key, label, detail in SUDO_MODES:
                if key == value or label == value:
                    self.app.data["sudo_mode"] = key
                    self.query_one("#sudo_detail", Static).update(
                        f"[b]Effect:[/] {detail}"
                    )
                    break
        elif rid == "model_providers":
            provider = next(
                (k for k, p in MODEL_PROVIDERS.items() if p["label"] == value),
                "custom",
            )
            self._apply_model_preset(provider)

    def on_select_changed(self, event: Select.Changed) -> None:
        sel = getattr(event, "select", None)
        if sel is None or getattr(sel, "id", None) != "model_select":
            return
        value = event.value
        if value in (Select.BLANK, Select.NULL):
            return
        model_input = self.query_one("#model", Input)
        if value == "__custom__":
            model_input.value = ""
            model_input.focus()
            return
        model_input.value = str(value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("api_key", "model_base_url"):
            if self._refresh_timer is not None:
                self._refresh_timer.stop()
            self._refresh_timer = None
            if self.app.dry_run or not event.value.strip():
                return
            self._refresh_timer = self.set_timer(
                0.8,
                lambda: self.run_worker(
                    self._refresh_model_list(self._selected_provider())
                ),
            )

    # ------------------------------------------------------------ review
    def _fill_review(self) -> None:
        data = self.app.data
        selected = [name for name, _d, _c in TOOLS if data["tools"].get(name)]
        mode_label = next(
            (label for key, label, _d in SUDO_MODES if key == data.get("sudo_mode")),
            "restricted",
        )
        table = self.query_one("#review_table", DataTable)
        table.clear()
        table.add_columns("Item", "Value")
        table.add_row("Tools", f"{len(selected)} - {', '.join(selected) if selected else 'none'}")
        table.add_row("Secrets provided", str(data.get("secrets_count", 0)))
        provider = data.get("secrets", {}).get("model_provider", "deepseek")
        model = data.get("secrets", {}).get("model", "")
        table.add_row(
            "AI model",
            f"{MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS['custom'])['label']} / "
            f"{model or 'not set'}",
        )
        api_key = data.get("secrets", {}).get("api_key", "")
        bot = data.get("secrets", {}).get("bot", "")
        table.add_row("API key", mask(api_key) if api_key else "not set")
        table.add_row("Bot token", mask(bot) if bot else "not set")
        table.add_row("Sudo mode", mode_label)
        table.add_row("Personality", "set at first conversation (agent name + style)")
        webui = data.get("webui", True)
        webui_host = data.get("webui_host", "127.0.0.1")
        webui_port = data.get("webui_port", "8787")
        table.add_row(
            "WebUI",
            f"{'enabled' if webui else 'disabled'}"
            + (f" - http://{webui_host}:{webui_port}" if webui else ""),
        )
        table.add_row(
            "Local memory",
            "enabled (Holographic / SQLite)"
            if data.get("memory", True)
            else "disabled",
        )
        table.add_row("Config loaded", "yes" if self.config_loaded else "no")

    # ------------------------------------------------------------ install
    @staticmethod
    def _colorize(line: str) -> str:
        if line.startswith("o"):
            return f"[bold {CYAN}]{line}[/]"
        if line.startswith("x"):
            return f"[bold {RED}]{line}[/]"
        if line.startswith("v"):
            return f"[{EMERALD}]{line}[/]"
        return line

    async def _run_install(self) -> None:
        log = self.query_one("#log", RichLog)
        prog = self.query_one("#prog", ProgressBar)
        installer = LiveInstaller(
            self.app.data,
            dry_run=bool(self.app.dry_run),
            on_log=lambda line: log.write(self._colorize(line)),
            on_progress=lambda: prog.advance(1),
            log_file=HERMES_HOME / "install.log",
        )
        await installer.run()
        self.app.data["failed"] = installer.failed
        log.write(f"\n[bold {EMERALD}]v Installation finished.[/]")
        self.install_done = True
        nxt = self.query_one("#next", Button)
        nxt.label = "Summary >"
        nxt.variant = "success"
        nxt.disabled = False

    def _fill_summary(self) -> None:
        log = self.query_one("#summary_log", RichLog)
        data = self.app.data
        log.write(f"[bold {CYAN}]INSTALLATION SUMMARY[/]")
        log.write("")
        log.write(f"[{SLATE}]Installed tools:[/]")
        for name, _desc, _cat in TOOLS:
            if data["tools"].get(name) and tool_path(name):
                log.write(f"  [{EMERALD}]v[/] {name}")
        mode_label = next(
            (label for key, label, _d in SUDO_MODES if key == data.get("sudo_mode")),
            "restricted",
        )
        log.write("")
        log.write(f"[{SLATE}]Sudo mode:[/] {mode_label}")
        log.write(f"[{SLATE}]Secrets provided:[/] {data.get('secrets_count', 0)}")
        provider = data.get("secrets", {}).get("model_provider", "deepseek")
        model = data.get("secrets", {}).get("model", "")
        log.write(
            f"[{SLATE}]AI model:[/] "
            f"{MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS['custom'])['label']} / "
            f"{model or 'not set'}"
        )
        api_key = data.get("secrets", {}).get("api_key", "")
        bot = data.get("secrets", {}).get("bot", "")
        log.write(
            f"[{SLATE}]API key:[/] "
            f"[{EMERALD}]{mask(api_key)}[/]" if api_key else f"[{RED}]API key: not set[/]"
        )
        log.write(
            f"[{SLATE}]Bot token:[/] "
            f"[{EMERALD}]{mask(bot)}[/]" if bot else f"[{RED}]Bot token: not set[/]"
        )
        log.write(f"[{SLATE}]Personality:[/] asked at first conversation (name + style)")
        log.write(
            f"[{SLATE}]Local memory:[/] "
            f"{'enabled (Holographic / SQLite fact store)' if data.get('memory', True) else 'disabled'}"
        )
        if data.get("webui", True):
            url = data.get("webui_url") or (
                f"http://{data.get('webui_host', '127.0.0.1')}:"
                f"{data.get('webui_port', '8787')}"
            )
            log.write("")
            log.write(f"[bold {EMERALD}]v WebUI dashboard:[/] {url}")
            log.write(
                f"[{SLATE_DIM}]WSL2: open the link directly from Windows; for remote access "
                "use an SSH tunnel (ssh -L 8787:127.0.0.1:8787 user@host).[/]"
            )
        if data.get("failed"):
            log.write(f"[{RED}]Failed steps:[/] {', '.join(data['failed'])}")
        log.write("")
        log.write(f"[{SLATE}]Houdini home:[/] {HERMES_HOME}")
        log.write(f"[{SLATE}]Install log:[/] {HERMES_HOME / 'install.log'}")
        log.write(
            f"[{SLATE_DIM}]Add more keys/tools anytime: drop a file in toolkit/keys/ or run toolkit-scan.sh.[/]"
        )


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class HoudiniInstaller(App):
    """Houdini Gateway Installer - Textual UI, live installation."""

    TITLE = "Houdini Gateway Installer"
    SUB_TITLE = "terminal wizard"
    BINDINGS = [Binding("q", "quit", "Quit")]
    # Built-in Textual themes (gruvbox, nord, dracula, catppuccin-mocha,
    # tokyo-night, monokai, solarized-dark, rose-pine, ...) - switch by
    # changing this one line.
    THEME = "gruvbox"

    CSS = """
    Screen { background: $background; }
    #root { width: 100%; height: 100%; }

    #sidebar {
        width: 32;
        height: 100%;
        background: $surface;
        border-right: solid $primary;
        padding: 1 1;
    }
    #logo { text-style: bold; color: $accent; }
    #subtitle { color: $text-muted; margin-bottom: 2; }
    #side_gradient { height: 2; margin-bottom: 1; }
    #side_progress { margin-bottom: 1; }
    #status_line { color: $text-muted; margin-top: 1; }

    #content { width: 1fr; height: 100%; padding: 1 2; }
    #content_title { text-style: bold; margin-bottom: 1; }

    #step_tabs { margin-bottom: 1; }
    #steps {
        height: 1fr;
        border: round $primary;
        background: $panel;
        padding: 1;
    }
    .step { height: 100%; padding: 1 2; overflow-y: auto; }
    .hint { color: $text-muted; margin-bottom: 1; }

    #content_hint { color: $text-muted; margin-top: 1; text-align: center; }
    #content_nav { align: center middle; height: auto; margin-top: 1; }
    #decide_row { align: center middle; height: auto; margin-top: 1; }
    Button { margin: 0 1; }
    Button:hover { background: $primary; color: $background; }

    #step-welcome { align: center middle; }
    #hat_logo { color: $accent; text-style: bold; margin-bottom: 1; }
    #content_logo { text-style: bold; color: $accent; text-align: center; }
    #content_sub { text-align: center; color: $text-muted; }
    #welcome_arabic { text-align: center; color: $text-muted; margin-bottom: 1; }
    #welcome_gradient { height: 2; margin-bottom: 1; }
    #welcome_features { margin: 1 0; color: $text-muted; }
    #welcome_start { margin-top: 1; }
    #welcome_note { margin-top: 1; color: $text-muted; }

    #cfg_source, #cfg_password { margin-bottom: 1; }
    #cfg_row { height: auto; align: left middle; margin-bottom: 1; }
    #cfg_status { margin-top: 1; }

    #tools_split, #secrets_split { width: 100%; height: 100%; }
    #tool_cats, #secret_groups { width: 28; height: 100%; }
    #tool_panes, #secret_panes {
        width: 1fr;
        height: 100%;
        border-left: solid $primary;
        padding: 0 2;
    }
    .pane { height: 100%; padding: 0 1; }

    Checkbox, Input, RadioButton { margin-bottom: 1; }
    #sudo_detail { margin-top: 1; }
    #review_table { height: 100%; }
    #prog { margin: 0 0 1 0; }
    #log, #summary_log { height: 1fr; border: solid $primary; }
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__()
        self.dry_run = dry_run
        self.data: dict = {
            "tools": {},
            "secrets": {},
            "secrets_count": 0,
            "sudo_mode": "restricted",
            "webui": True,
            "webui_host": "127.0.0.1",
            "webui_port": "8787",
            "memory": True,
            "failed": [],
        }

    def on_mount(self) -> None:
        self.push_screen(WizardScreen())


# --------------------------------------------------------------------------
# Self-test (headless, dry-run)
# --------------------------------------------------------------------------
async def selftest() -> None:
    app = HoudiniInstaller(dry_run=True)
    async with app.run_test(size=(140, 46)) as pilot:
        try:
            async def press(bid: str) -> None:
                app.screen.query_one(f"#{bid}", Button).press()
                await pilot.pause()

            await pilot.pause()
            assert app.screen is not None
            assert app.screen.query_one("#welcome_start", Button) is not None
            assert app.screen.query_one("#step_tabs", Tabs) is not None
            await press("welcome_start")  # welcome -> config
            await press("next")  # config (skip) -> core
            app.screen.query_one("#api_key", Input).value = "sk-demo-value"
            app.screen.query_one("#bot", Input).value = "123:demo-token"
            rs = app.screen.query_one("#model_providers", RadioSet)
            for rb in rs.query(RadioButton):
                if rb.label is not None and rb.label.plain == "OpenCode":
                    rb.value = True
                    break
            await pilot.pause()
            sel = app.screen.query_one("#model_select", Select)
            assert not sel.disabled
            assert len(sel._options) >= 4  # blank + curated presets + custom
            sel.value = "deepseek-v4-flash-free"
            await pilot.pause()
            await press("next")  # core -> decide
            assert app.screen.query_one("#decide_custom", Button) is not None
            assert app.screen.query_one("#decide_quick", Button) is not None
            assert app.data["secrets"]["model_provider"] == "opencode"
            assert app.data["secrets"]["model"] == "deepseek-v4-flash-free"
            assert app.data["secrets"]["model_base_url"] == "https://opencode.ai/zen/v1"
            app.screen.query_one("#decide_custom", Button).press()
            await pilot.pause()
            cats = app.screen.query_one("#tool_cats", ListView)
            assert len(cats.children) >= 1
            assert app.screen.query_one("#tool_nuclei", Checkbox).value is True
            assert app.screen.query_one("#tool_nmap", Checkbox).value is True
            await press("next")  # tools -> secrets
            await press("next")  # secrets -> sudo
            await press("next")  # sudo -> webui
            app.screen.query_one("#webui_enable", Checkbox)
            await press("next")  # webui -> memory
            app.screen.query_one("#memory_enable", Checkbox)
            assert app.data["memory"] is True
            await press("next")  # memory -> review
            assert app.screen.query_one("#review_table", DataTable) is not None
            assert mask(app.data["secrets"]["api_key"]) == "sk-d...alue"
            await press("next")  # review -> install
            await press("next")  # start install (dry-run)
            for _ in range(60):
                nxt = app.screen.query_one("#next", Button)
                if not nxt.disabled and "Summary" in nxt.label.plain:
                    break
                await pilot.pause(0.1)
            await press("next")  # -> summary
            assert app.screen.query_one("#summary_log", RichLog) is not None
            assert app.data["secrets_count"] == 2
            assert app.data["sudo_mode"] == "restricted"
            assert app.data["tools"]["nuclei"] is True
        except Exception:
            app.exit()
            raise

    # quick-install path: core -> decide(quick) -> review (defaults, no install)
    app2 = HoudiniInstaller(dry_run=True)
    async with app2.run_test(size=(140, 46)) as pilot2:
        async def press2(bid: str) -> None:
            app2.screen.query_one(f"#{bid}", Button).press()
            await pilot2.pause()

        await pilot2.pause()
        await press2("next")  # welcome -> config
        await press2("next")  # config (skip) -> core
        app2.screen.query_one("#api_key", Input).value = "sk-demo"
        await press2("next")  # core -> decide
        app2.screen.query_one("#decide_quick", Button).press()
        await pilot2.pause()
        assert app2.screen.query_one("#review_table", DataTable) is not None
        assert all(app2.data["tools"][n] for n, _d, _c in TOOLS)
        assert app2.data["secrets"]["api_key"] == "sk-demo"
        assert app2.data["secrets"]["model_provider"] == "deepseek"
        assert app2.data["secrets_count"] == 1

    # custom-provider path: base URL + key + model must all reach secrets
    app3 = HoudiniInstaller(dry_run=True)
    async with app3.run_test(size=(140, 46)) as pilot3:
        async def press3(bid: str) -> None:
            app3.screen.query_one(f"#{bid}", Button).press()
            await pilot3.pause()

        await pilot3.pause()
        await press3("next")  # welcome -> config
        await press3("next")  # config (skip) -> core
        rs3 = app3.screen.query_one("#model_providers", RadioSet)
        for rb in rs3.query(RadioButton):
            if rb.label is not None and rb.label.plain.startswith("Custom"):
                rb.value = True
                break
        await pilot3.pause()
        app3.screen.query_one("#model_base_url", Input).value = "https://my-gw.example/v1"
        app3.screen.query_one("#api_key", Input).value = "sk-custom-demo"
        app3.screen.query_one("#model", Input).value = "my-custom-model"
        await press3("next")  # core -> decide
        assert app3.data["secrets"]["model_provider"] == "custom"
        assert app3.data["secrets"]["model"] == "my-custom-model"
        assert app3.data["secrets"]["model_base_url"] == "https://my-gw.example/v1"
        assert app3.data["secrets"]["api_key"] == "sk-custom-demo"

    # tab navigation must collect the current step's inputs before leaving
    app4 = HoudiniInstaller(dry_run=True)
    async with app4.run_test(size=(140, 46)) as pilot4:
        async def press4(bid: str) -> None:
            app4.screen.query_one(f"#{bid}", Button).press()
            await pilot4.pause()

        await pilot4.pause()
        await press4("next")  # welcome -> config
        await press4("next")  # config (skip) -> core
        rs4 = app4.screen.query_one("#model_providers", RadioSet)
        for rb in rs4.query(RadioButton):
            if rb.label is not None and rb.label.plain.startswith("Custom"):
                rb.value = True
                break
        await pilot4.pause()
        app4.screen.query_one("#model_base_url", Input).value = "https://tab-gw.example/v1"
        app4.screen.query_one("#api_key", Input).value = "sk-tab-demo"
        app4.screen.query_one("#model", Input).value = "tab-model"
        app4.screen.query_one("#step_tabs", Tabs).active = "decide"  # tab jump, not Next
        await pilot4.pause()
        assert app4.data["secrets"]["model_provider"] == "custom"
        assert app4.data["secrets"]["model"] == "tab-model"
        assert app4.data["secrets"]["model_base_url"] == "https://tab-gw.example/v1"
        assert app4.data["secrets"]["api_key"] == "sk-tab-demo"

    # custom validation: Next must be blocked while required fields are empty
    app5 = HoudiniInstaller(dry_run=True)
    async with app5.run_test(size=(140, 46)) as pilot5:
        async def press5(bid: str) -> None:
            app5.screen.query_one(f"#{bid}", Button).press()
            await pilot5.pause()

        await pilot5.pause()
        await press5("next")  # welcome -> config
        await press5("next")  # config (skip) -> core
        rs5 = app5.screen.query_one("#model_providers", RadioSet)
        for rb in rs5.query(RadioButton):
            if rb.label is not None and rb.label.plain.startswith("Custom"):
                rb.value = True
                break
        await pilot5.pause()
        app5.screen.query_one("#model_base_url", Input).value = "https://v.example/v1"
        app5.screen.query_one("#api_key", Input).value = "sk-v"
        await press5("next")  # model missing -> must NOT advance
        assert app5.screen.current == "core"
        status5 = app5.screen.query_one("#core_status", Static)
        assert "Model ID" in str(status5.content)
        app5.screen.query_one("#model", Input).value = "v-model"
        await press5("next")  # now complete -> advances
        assert app5.screen.current == "decide"
        assert app5.data["secrets"]["model"] == "v-model"
    print("selftest OK")


if __name__ == "__main__":
    def main() -> None:
        HoudiniInstaller().run()

    if "--selftest" in sys.argv:
        asyncio.run(selftest())
    else:
        main()
