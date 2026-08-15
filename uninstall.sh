#!/usr/bin/env bash
# =============================================================================
# Houdini Gateway — uninstall.sh
# Remove the ENTIRE Houdini install so the machine is clean for a reinstall.
#
# Usage:
#   bash uninstall.sh              # interactive (asks before deleting)
#   bash uninstall.sh --yes        # no prompts
#   bash uninstall.sh --keep-data  # keep ~/recon and ~/vpn-profiles
#   bash uninstall.sh --purge-apt  # also remove apt tools installed by us
#
# What it removes (everything the installer created):
#   ~/.hermes, ~/.houdini-tui-venv, ~/browser-venv, ~/hermes-webui,
#   ~/nuclei-templates, /usr/local/lib/hermes-agent, /opt/jadx,
#   tool binaries in /usr/local/bin, tool configs/caches, system pip
#   packages, the systemd user service, the toolkit crontab, sudoers drop-in.
# =============================================================================
set -u

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
YES=0
KEEP_DATA=0
PURGE_APT=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --keep-data) KEEP_DATA=1 ;;
    --purge-apt) PURGE_APT=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)"; exit 2 ;;
  esac
done

if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi

say()  { printf '\033[1;36m[uninstall]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[uninstall]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[uninstall]\033[0m %s\n' "$*"; }

confirm() {
  if [ "$YES" = 1 ]; then return 0; fi
  printf '%s [y/N] ' "$1"
  read -r ans
  case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

if [ "$YES" != 1 ]; then
  say "This removes the Houdini Gateway install from this machine."
  say "Targets: $HERMES_HOME, tool venvs, /usr/local binaries, services, crontab, sudoers."
  confirm "Continue?" || { say "aborted - nothing touched."; exit 0; }
fi

REMOVED=0
KEPT=0

rmf() {  # remove path (file/dir) if it exists; log + count
  if [ -e "$1" ] || [ -L "$1" ]; then
    if rm -rf "$1" 2>/dev/null; then
      ok "removed  $1"; REMOVED=$((REMOVED+1))
    else
      warn "could not remove $1 (permissions?)"; KEPT=$((KEPT+1))
    fi
  fi
}

# ── 1. stop services ────────────────────────────────────────────────────────
say "Stopping services..."
systemctl --user stop hermes-gateway 2>/dev/null
systemctl --user disable hermes-gateway 2>/dev/null
if [ -x "$HOME/hermes-webui/ctl.sh" ]; then
  "$HOME/hermes-webui/ctl.sh" stop >/dev/null 2>&1
fi
pkill -f "hermes_cli.main" 2>/dev/null
fuser -k 8787/tcp 2>/dev/null
sleep 1

# ── 2. user-level files ─────────────────────────────────────────────────────
say "Removing user-level files..."
rmf "$HERMES_HOME"
rmf "$HOME/.houdini-tui-venv"
rmf "$HOME/browser-venv"
rmf "$HOME/hermes-webui"
rmf "$HOME/nuclei-templates"
rmf "$HOME/.cache/ms-playwright"
rmf "$HOME/.config/subfinder"
rmf "$HOME/.config/uncover"
rmf "$HOME/.config/vulners"
rmf "$HOME/.config/nvd"
rmf "$HOME/.wpscan"
rmf "$HOME/.config/ngrok"
rmf "$HOME/.local/state/hermes"   # uv/state leftovers if any
rmf "$HOME/.config/systemd/user/hermes-gateway.service"
if [ -f "$HOME/.config/systemd/user/hermes-webui.service" ]; then
  rmf "$HOME/.config/systemd/user/hermes-webui.service"
fi
systemctl --user daemon-reload 2>/dev/null

if [ "$KEEP_DATA" = 1 ]; then
  warn "keeping work data: ~/recon and ~/vpn-profiles"
else
  rmf "$HOME/recon"
  rmf "$HOME/vpn-profiles"
fi

# ── 3. system-level files ───────────────────────────────────────────────────
say "Removing system-level files..."
for b in hermes hermes-acp hermes-agent droopescan drupwn jadx frida \
         objection apktool nuclei subfinder httpx ngrok browser-capture; do
  rmf "/usr/local/bin/$b"
done
rmf "/usr/local/lib/hermes-agent"
rmf "/opt/jadx"
for f in /etc/sudoers.d/hermes-*; do
  [ -e "$f" ] && { $SUDO rm -f "$f" 2>/dev/null && ok "removed  $f" || warn "could not remove $f (try sudo)"; }
done

# ── 4. system pip packages (installed with --break-system-packages) ─────────
if python3 -m pip --version >/dev/null 2>&1; then
  say "Uninstalling system pip packages..."
  python3 -m pip uninstall -y -q droopescan drupwn frida-tools objection 2>/dev/null \
    && ok "pip packages removed" || warn "pip uninstall had failures (harmless if packages absent)"
fi

# ── 5. crontab ──────────────────────────────────────────────────────────────
if command -v crontab >/dev/null 2>&1; then
  if crontab -l 2>/dev/null | grep -q "toolkit-scan"; then
    crontab -l 2>/dev/null | grep -v "toolkit-scan" | crontab - 2>/dev/null
    ok "toolkit cron removed"
  fi
fi

# ── 6. optional apt purge ───────────────────────────────────────────────────
if [ "$PURGE_APT" = 1 ]; then
  say "Purging apt tools installed by the installer..."
  $SUDO apt-get purge -y -qq \
    nmap nikto sqlmap gobuster ffuf whatweb apktool \
    openjdk-17-jre-headless ruby-dev python3-pip 2>/dev/null \
    && ok "apt packages purged" || warn "some apt packages could not be purged"
  $SUDO apt-get autoremove -y -qq >/dev/null 2>&1
fi

# ── done ────────────────────────────────────────────────────────────────────
echo
ok "Done. Removed $REMOVED items, $KEPT kept (see warnings above)."
say "The machine is clean. To reinstall:"
say "  git clone https://github.com/houdiniSC/Houdini.git && cd Houdini && bash install-ubuntu.sh"
if [ "$KEEP_DATA" = 0 ]; then
  warn "~/recon and ~/vpn-profiles were deleted too (use --keep-data next time to preserve them)."
fi
if [ "$PURGE_APT" = 0 ]; then
  say "apt tools (nmap, sqlmap, ...) were left installed - add --purge-apt to remove them."
fi
