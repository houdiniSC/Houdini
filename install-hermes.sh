#!/usr/bin/env bash
# install-hermes.sh — Hermes Bootstrap Installer (whiptail UI)
# Target: WSL2 Ubuntu (run as the normal user).
# Secrets: read from secrets.env if present, else ask via UI (empty = skip).
# Sudo: agent permissions are configured via sudoers.d — no stored password.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_DIR="$SCRIPT_DIR/knowledge-pack"
SECRETS_FILE="$SCRIPT_DIR/secrets.env"
HERMES_HOME="$HOME/.hermes"
LOG="/tmp/hermes-bootstrap.log"
: > "$LOG"

# ── UI helpers ────────────────────────────────────────────────────────────
HAVE_UI=0
command -v whiptail >/dev/null 2>&1 && HAVE_UI=1

ui_box() { # ui_box <title> <height> <width> <text>
  if [ "$HAVE_UI" = 1 ]; then
    whiptail --backtitle "Hermes Bootstrap Installer" --title "$1" --msgbox "$4" "$2" "$3"
  else
    printf '\n== %s ==\n%s\n' "$1" "$4"
  fi
}

ui_info() { # ui_info <title> <text>
  if [ "$HAVE_UI" = 1 ]; then
    whiptail --backtitle "Hermes Bootstrap Installer" --title "$1" --infobox "$2" 6 62
  else
    printf '[%s] %s\n' "$1" "$2"
  fi
}

ui_ask() { # ui_ask <title> <prompt> -> prints value (empty = skip)
  local title=$1 prompt=$2 val=""
  if [ "$HAVE_UI" = 1 ]; then
    val=$(whiptail --backtitle "Hermes Bootstrap Installer" --title "$title" \
      --inputbox "$prompt

(اتركه فارغًا ثم Enter للتخطي)" 10 70 3>&1 1>&2 2>&3 || true)
  else
    printf '%s (Enter = skip): ' "$prompt"; IFS= read -r val || val=""
  fi
  printf '%s' "$val"
}

ui_yesno() { # ui_yesno <title> <text> -> 0 yes / 1 no (default: yes)
  if [ "$HAVE_UI" = 1 ]; then
    whiptail --backtitle "Hermes Bootstrap Installer" --title "$1" --yesno "$2" 10 64
  else
    printf '%s (Y/n): ' "$2"; read -r a
    case "$a" in ""|y|Y) return 0;; *) return 1;; esac
  fi
}

ui_radio() { # ui_radio <title> <prompt> <items...> -> prints selection
  local title=$1 prompt=$2; shift 2
  local items=("$@")
  local args=() i=0 choice
  for item in "${items[@]}"; do i=$((i+1)); args+=("$i" "$item" OFF); done
  if [ "$HAVE_UI" = 1 ]; then
    choice=$(whiptail --backtitle "Hermes Bootstrap Installer" --title "$title" \
      --radiolist "$prompt" 14 50 8 "${args[@]}" 3>&1 1>&2 2>&3 || true)
  else
    printf '%s\n' "$prompt"
    local n=1
    for item in "$@"; do printf '  %s) %s\n' "$n" "$item"; n=$((n+1)); done
    read -r choice || choice=1
  fi
  if [ -n "$choice" ] && [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "${#items[@]}" ]; then
    printf '%s' "${items[$((choice-1))]}"
  else
    printf '%s' "${items[0]}"
  fi
}

get_env() { grep -E "^$1=" "$SECRETS_FILE" 2>/dev/null | head -1 | cut -d= -f2-; }

# ── Welcome ───────────────────────────────────────────────────────────────
ui_box "Welcome" 14 68 "
         ╔══════════════════════════════════════════════╗
         ║   HERMES BOOTSTRAP INSTALLER                 ║
         ╚══════════════════════════════════════════════╝

سيتم تثبيت:
  • Hermes Agent (أحدث إصدار)
  • أدوات الفحص الكاملة (nuclei, subfinder, nmap, sqlmap ...)
  • حزمة المعرفة: البرومبت + نظام الأدوات والمفاتيح + المهارات الأساسية
  • إدخال الأسرار (أو تخطيها وإضافتها لاحقًا)

اضغط OK للمتابعة."

ui_info "Check" "التحقق من المتطلبات..."
export PATH="$HOME/.local/bin:$PATH"
for b in curl git; do
  command -v "$b" >/dev/null 2>&1 || { echo "✗ missing: $b"; exit 1; }
done

# ── 1) Hermes core ─────────────────────────────────────────────────────────
if command -v hermes >/dev/null 2>&1; then
  ui_info "Hermes" "✓ Hermes موجود: $(hermes --version 2>/dev/null | head -1)"
else
  ui_info "Hermes" "جاري تثبيت Hermes Agent..."
  bash <(curl -fsSL https://hermes-agent.nousresearch.com/install.sh) --non-interactive >> "$LOG" 2>&1 \
    || { ui_box "Error" 8 60 "✗ فشل تثبيت Hermes — شاهد $LOG"; exit 1; }
fi

# ── 2) Security toolchain ──────────────────────────────────────────────────
ui_info "Tools" "تثبيت أدوات apt (nmap, nikto, sqlmap ...)"
sudo apt-get update -qq >> "$LOG" 2>&1
sudo apt-get install -y -qq nmap nikto sqlmap gobuster ffuf whatweb dnsutils \
  netcat-openbsd jq unzip openvpn >> "$LOG" 2>&1

for p in "nuclei v3.11.0 nuclei_3.11.0_linux_amd64.zip" \
         "subfinder v2.15.0 subfinder_2.15.0_linux_amd64.zip" \
         "httpx v1.10.0 httpx_1.10.0_linux_amd64.zip"; do
  set -- $p
  name=$1; ver=$2; file=$3
  [ -x "/usr/local/bin/$name" ] && continue
  ui_info "Tools" "تثبيت $name..."
  cd /tmp && curl -fsSL -o "$file" "https://github.com/projectdiscovery/$name/releases/download/$ver/$file" \
    && unzip -o -q "$file" -d /usr/local/bin && chmod +x "/usr/local/bin/$name"
done

command -v ngrok >/dev/null 2>&1 || {
  ui_info "Tools" "تثبيت ngrok..."
  cd /tmp && curl -fsSL -o ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
    && tar xzf ngrok.tgz -C /usr/local/bin; }

export PATH="$HERMES_HOME/bin:$PATH"
command -v droopescan >/dev/null 2>&1 || {
  ui_info "Tools" "تثبيت droopescan + drupwn (pip)..."
  sudo python3 -m pip install --break-system-packages droopescan >> "$LOG" 2>&1
  sudo python3 -m pip install --break-system-packages 'setuptools<81' >> "$LOG" 2>&1
  sudo python3 -m pip install --break-system-packages --no-build-isolation git+https://github.com/immunIT/drupwn >> "$LOG" 2>&1
}

ui_info "Tools" "تحديث قوالب nuclei..."
command -v nuclei >/dev/null 2>&1 && nuclei -update-templates >> "$LOG" 2>&1

# ── 3) Merge knowledge pack (hand-written, no traces) ──────────────────────
if [ -d "$PACK_DIR" ]; then
  ui_info "Knowledge" "دمج حزمة المعرفة..."
  mkdir -p "$HERMES_HOME"
  [ -f "$PACK_DIR/SOUL.md" ] && cp "$PACK_DIR/SOUL.md" "$HERMES_HOME/SOUL.md"
  [ -f "$PACK_DIR/config.template.yaml" ] && cp "$PACK_DIR/config.template.yaml" "$HERMES_HOME/config.template.yaml"
  [ -f "$PACK_DIR/PERSONA.md.template" ] && cp "$PACK_DIR/PERSONA.md.template" "$HERMES_HOME/PERSONA.md.template"
  if [ -d "$PACK_DIR/skills" ]; then
    mkdir -p "$HERMES_HOME/skills"
    cp -r "$PACK_DIR/skills/." "$HERMES_HOME/skills/"
    ui_info "Knowledge" "skills: minimal — custom operational skills only"
  fi
  if [ -d "$PACK_DIR/toolkit" ]; then
    mkdir -p "$HERMES_HOME/toolkit"
    cp -r "$PACK_DIR/toolkit/." "$HERMES_HOME/toolkit/"
    chmod +x "$HERMES_HOME/toolkit/toolkit-scan.sh" 2>/dev/null || true
  fi
  if [ -f "$HERMES_HOME/toolkit/tools/build-skills-index.py" ]; then
    python3 "$HERMES_HOME/toolkit/tools/build-skills-index.py" --skills "$HERMES_HOME/skills" >> "$LOG" 2>&1 || true
  fi
fi

# browser-capture: Playwright + mitmproxy + Chromium (optional, large)
if ask_tool "Browser Capture" "تثبيت browser-capture (Playwright + Chromium + mitmproxy, ~200MB)؟"; then
  ui_info "Tools" "تثبيت browser-capture (playwright + mitmproxy)..."
  python3 -m venv "$HOME/browser-venv"
  "$HOME/browser-venv/bin/pip" install -q playwright mitmproxy >> "$LOG" 2>&1
  sudo "$HOME/browser-venv/bin/playwright" install --with-deps chromium >> "$LOG" 2>&1
  printf '#!/usr/bin/env bash\nexec %s %s "$@"\n' \
    "$HOME/browser-venv/bin/python" "$HERMES_HOME/toolkit/tools/browser-capture.py" \
    | sudo tee /usr/local/bin/browser-capture >/dev/null
  sudo chmod +x /usr/local/bin/browser-capture
  ui_info "Tools" "browser-capture جاهز"
fi

# mobile toolchain: apktool + jadx + frida (APK testing)
if ask_tool "Mobile Tools" "تثبيت أدوات APK (apktool + jadx + frida/objection)؟"; then
  ui_info "Tools" "تثبيت أدوات الموبايل..."
  sudo apt-get install -y -qq apktool openjdk-17-jre-headless jadx >> "$LOG" 2>&1
  command -v apktool >/dev/null 2>&1 || {
    curl -fsSL -o /tmp/apktool.jar https://github.com/iBotPeaches/Apktool/releases/latest/download/apktool.jar
    sudo cp /tmp/apktool.jar /usr/local/bin/
    printf '#!/usr/bin/env bash\nexec java -jar /usr/local/bin/apktool.jar "$@"\n' | sudo tee /usr/local/bin/apktool >/dev/null
    sudo chmod +x /usr/local/bin/apktool
  }
  command -v jadx >/dev/null 2>&1 || {
    curl -fsSL -o /tmp/jadx.zip https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip
    sudo unzip -o -q /tmp/jadx.zip -d /opt/jadx
    sudo chmod +x /opt/jadx/bin/jadx
    sudo ln -sf /opt/jadx/bin/jadx /usr/local/bin/jadx
  }
  sudo python3 -m pip install --break-system-packages -q frida-tools objection >> "$LOG" 2>&1
  ui_info "Tools" "أدوات الموبايل جاهزة"
fi

# ── 4) Secrets (UI with skip) ──────────────────────────────────────────────
ui_box "Secrets" 10 66 "
الآن سنسأل عن الإعدادات والأسرار.
أي حقل تتركه فارغًا ثم Enter = تخطي (يُضاف لاحقًا).

لو حضرت ملف secrets.env بجانب السكربت، الأسرار ستُقرأ تلقائيًا."

ask_sec() { # ask_sec <var> <title> <prompt> <envname>
  local __v=$1 __title=$2 __prompt=$3 __env=$4 __val
  __val=$(get_env "$__env")
  if [ -z "$__val" ] && [ "$CUSTOMIZE" = 1 ]; then
    __val=$(ui_ask "$__title" "$__prompt")
  fi
  eval "$__v=\$__val"
}

ask_tool() { # ask_tool <title> <text> -> 0 install / 1 skip (default: yes)
  [ "$CUSTOMIZE" = 1 ] && ui_yesno "$1" "$2" || return 0
}

ask_sec bot "Telegram Bot" "توكن البوت من @BotFather" bot
CUSTOMIZE=0
if ui_yesno "Customize" "متابعة تهيئة المفاتيح والأدوات الاختيارية؟ (لا = تثبيت سريع بالإعدادات الافتراضية)"; then
  CUSTOMIZE=1
fi

# AI provider (OpenAI-compatible) - interactive: pick a provider, enter the
# API key and (optionally) choose the model. Endpoints are presets, so the
# user never has to type a base URL unless they pick Custom.
MODEL_PROVIDER="$(get_env model_provider)"
if [ -z "$MODEL_PROVIDER" ] && [ "$CUSTOMIZE" = 1 ]; then
  MODEL_PROVIDER=$(ui_radio "AI Provider" "اختر مزود الذكاء الاصطناعي (OpenAI-compatible):" \
    "DeepSeek" "OpenAI" "OpenCode" "Custom")
fi
case "$MODEL_PROVIDER" in
  OpenAI)  MODEL_PROVIDER=openai ;;
  OpenCode) MODEL_PROVIDER=opencode ;;
  Custom)  MODEL_PROVIDER=custom ;;
  openai|opencode|custom) ;;
  *)       MODEL_PROVIDER=deepseek ;;
esac
case "$MODEL_PROVIDER" in
  openai)   DEFAULT_MODEL="gpt-5.4";           DEFAULT_BASE_URL="https://api.openai.com/v1" ;;
  opencode) DEFAULT_MODEL="deepseek-v4-flash"; DEFAULT_BASE_URL="https://opencode.ai/zen/v1" ;;
  custom)   DEFAULT_MODEL="";                  DEFAULT_BASE_URL="" ;;
  *)        MODEL_PROVIDER="deepseek";         DEFAULT_MODEL="deepseek-v4-flash"; DEFAULT_BASE_URL="https://api.deepseek.com/v1" ;;
esac
ask_sec model_base_url "AI Base URL" "رابط API (فارغ = تلقائي للمزود; مطلوب فقط عند Custom)" model_base_url
[ -n "$model_base_url" ] || model_base_url="$DEFAULT_BASE_URL"
ask_sec api_key "AI API Key" "مفتاح API للمزود (sk-...)" api_key

# Dynamic model list: live catalog from the provider's OpenAI-compatible
# /models endpoint (uses the key above); curated presets as fallback.
case "$MODEL_PROVIDER" in
  openai)   PRESET_MODELS=(gpt-5.4 gpt-5.4-mini gpt-5.4-nano) ;;
  opencode) PRESET_MODELS=(deepseek-v4-flash deepseek-v4-flash-free) ;;
  custom)   PRESET_MODELS=() ;;
  *)        PRESET_MODELS=(deepseek-v4-flash deepseek-v4-pro) ;;
esac
MODEL_CHOICES=()
if [ -n "$api_key" ] && [ -n "$model_base_url" ] \
    && command -v curl >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  while IFS= read -r m; do [ -n "$m" ] && MODEL_CHOICES+=("$m"); done < <(
    curl -fsS -m 15 -H "Authorization: Bearer $api_key" "$model_base_url/models" 2>/dev/null \
      | jq -r '.data[].id' 2>/dev/null | sort -u
  )
fi
[ "${#MODEL_CHOICES[@]}" -gt 0 ] || MODEL_CHOICES=("${PRESET_MODELS[@]}")
if [ "${#MODEL_CHOICES[@]}" -gt 40 ]; then
  MODEL_CHOICES=("${MODEL_CHOICES[@]:0:40}")
fi
model="$(get_env model)"
if [ -z "$model" ] && [ "$CUSTOMIZE" = 1 ] && [ "${#MODEL_CHOICES[@]}" -gt 1 ]; then
  model=$(ui_radio "AI Model" "اختر الموديل (قائمة $MODEL_PROVIDER):" "${MODEL_CHOICES[@]}")
fi
[ -n "$model" ] || model="${DEFAULT_MODEL:-}"
ask_sec users "Telegram Users" "معرفات المستخدمين المسموحين (فواصل)" users
ask_sec github "Recon - GitHub" "GitHub PAT (subfinder + gh/git)" github
ask_sec virustotal "Recon - VirusTotal" "مفتاح VirusTotal" virustotal
ask_sec shodan "Recon - Shodan" "مفتاح Shodan (subfinder + uncover)" shodan
ask_sec urlscan "Recon - URLScan" "مفتاح URLScan" urlscan
ask_sec dnsdumpster "Recon - DNSDumpster" "مفتاح DNSDumpster" dnsdumpster
ask_sec zoomeye "Recon - ZoomEye" "مفتاح ZoomEye (host:key) (subfinder + uncover)" zoomeye
ask_sec fofa "Recon - Fofa" "مفتاح Fofa (email:key)" fofa
ask_sec vulners "Vulners" "مفتاح Vulners" vulners
ask_sec wpscan "WPScan" "توكن WPScan" wpscan
ask_sec ngrok "ngrok" "ngrok authtoken" ngrok
ask_sec vpn_user "VPN" "اسم مستخدم VPN (المزود الافتراضي)" vpn_user
ask_sec vpn_pass "VPN" "كلمة مرور VPN (المزود الافتراضي)" vpn_pass
ask_sec vpn_profiles_dir "VPN" "مجلد بروفيلات OpenVPN (.ovpn) - يدعم مجلدات فرعية لكل مزود" vpn_profiles_dir
ask_sec brave "Search" "Brave Search API key" brave
ask_sec serpapi "Search" "SerpAPI key" serpapi
ask_sec nvd "NVD" "NVD API key" nvd
ask_sec home_channel "Telegram" "Home channel (اختياري — اتركه فارغًا للتعرف التلقائي عند أول استخدام)" home_channel
ask_sec home_user "Telegram" "معرف محادثتك الخاصة (اختياري — اتركه فارغًا للتعرف التلقائي)" home_user

# ── 5) Agent sudo permissions (no stored password) ─────────────────────────
if [ "$CUSTOMIZE" = 1 ]; then
  SUDO_MODE=$(ui_radio "Sudo" "صلاحيات الوكيل على النظام:" \
    "مقنّن (موصى به)" "واسع (كل شيء)" "بدون")
else
  SUDO_MODE="مقنّن (موصى به)"
fi
case "$SUDO_MODE" in
  *واسع*)
    SUDOERS_LINE="$USER ALL=(ALL) NOPASSWD: ALL"
    ;;
  *مقنّن*)
    SUDOERS_LINE="$USER ALL=(ALL) NOPASSWD: /usr/sbin/openvpn, /usr/bin/systemctl, /usr/bin/apt, /usr/bin/apt-get, /usr/bin/nmap, /usr/sbin/tcpdump, /usr/bin/docker"
    ;;
  *)
    SUDOERS_LINE=""
    ;;
esac
if [ -n "$SUDOERS_LINE" ]; then
  ui_info "Sudo" "كتابة صلاحيات الوكيل في /etc/sudoers.d (سيتطلب كلمة مرورك مرة واحدة)..."
  printf '%s\n' "$SUDOERS_LINE" | sudo tee "/etc/sudoers.d/hermes-$USER" >/dev/null 2>>"$LOG" \
    && sudo chmod 440 "/etc/sudoers.d/hermes-$USER" >> "$LOG" 2>&1 \
    && echo "sudoers written: /etc/sudoers.d/hermes-$USER" >> "$LOG" \
    || ui_box "Sudo" 8 60 "✗ لم نتمكن من كتابة صلاحيات sudo — يمكنك إضافتها يدويًا لاحقًا."
fi

# ── 6) Write configs & keys ────────────────────────────────────────────────
ui_info "Config" "كتابة الإعدادات..."
mkdir -p "$HERMES_HOME"

if [ -n "$api_key" ] && [ -n "$model" ] && [ -n "$model_base_url" ]; then
  python3 - "$HERMES_HOME/config.template.yaml" "$HERMES_HOME/config.yaml" \
      "$model" "$model_base_url" "$api_key" <<'PY' >> "$LOG" 2>&1
import sys
tpl, out, model, base_url, key = sys.argv[1:6]
text = open(tpl, encoding="utf-8").read()
text = (text.replace("__MODEL_ID__", model)
            .replace("__MODEL_BASE_URL__", base_url)
            .replace("__API_KEY__", key))
open(out, "w", encoding="utf-8").write(text)
PY
  printf '\nOPENAI_API_KEY=%s\n' "$api_key" >> "$HERMES_HOME/.env"
fi

if [ -n "$bot" ]; then
  printf 'TELEGRAM_BOT_TOKEN=%s\n' "$bot" >> "$HERMES_HOME/.env"
  [ -n "$users" ] && printf 'TELEGRAM_ALLOWED_USERS=%s\n' "$users" >> "$HERMES_HOME/.env"
fi
[ -n "$brave" ]    && printf 'BRAVE_SEARCH_API_KEY=%s\n' "$brave" >> "$HERMES_HOME/.env"
[ -n "$serpapi" ]  && printf 'SERPAPI_API_KEY=%s\n' "$serpapi" >> "$HERMES_HOME/.env"
[ -n "$github" ]   && printf 'GITHUB_TOKEN=%s\n' "$github" >> "$HERMES_HOME/.env"

HOMECHAT="${home_channel:-$home_user}"
if [ -n "$HOMECHAT" ]; then
  printf 'TELEGRAM_HOME_CHANNEL=%s\n' "$HOMECHAT" >> "$HERMES_HOME/.env"
  if [ -f "$HERMES_HOME/config.yaml" ]; then
    CHAT="${HOMECHAT%%:*}"
    THREAD="${HOMECHAT#*:}"
    [ "$THREAD" = "$HOMECHAT" ] && THREAD=""
    sed -i "s/^      chat_id: \"\".*/      chat_id: \"$CHAT\"/" "$HERMES_HOME/config.yaml"
    [ -n "$THREAD" ] && sed -i "s/^      thread_id: \"\".*/      thread_id: \"$THREAD\"/" "$HERMES_HOME/config.yaml"
  fi
fi

# Pre-seed workspace_topics.json with the pinned chat_ids (group -> home_channel,
# private -> home_user). Topic ids are NOT known yet — first-run-setup creates
# them dynamically on first interaction (topics_pending: true).
if [ -n "$home_channel" ] || [ -n "$home_user" ]; then
  mkdir -p "$HERMES_HOME"
  export HERMES_MAP_PATH="$HERMES_HOME/workspace_topics.json"
  export HERMES_HC="${home_channel:-}"
  export HERMES_HU="${home_user:-}"
  python3 - <<'PY' || true
import json, os
path = os.environ["HERMES_MAP_PATH"]
hc = os.environ.get("HERMES_HC", "").strip()
hu = os.environ.get("HERMES_HU", "").strip()
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    data = {}
if not isinstance(data, dict):
    data = {}
seeded = []
def entry(chat, slot):
    return {"chat_id": int(chat) if chat.lstrip("-").isdigit() else chat,
            "flat": slot == "home_user", "topics": {},
            "topics_pending": True, "preconfigured": True}
def seed(slot, raw):
    chat = raw.split(":", 1)[0].strip()
    if not chat:
        return
    if isinstance(data.get(slot), dict) and data[slot].get("chat_id") is not None:
        return
    data[slot] = entry(chat, slot)
    seeded.append(slot)
if hc:
    chat = hc.split(":", 1)[0].strip()
    seed("home_channel" if chat.startswith("-") else "home_user", chat)
if hu:
    seed("home_user", hu)
if seeded:
    json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    os.chmod(path, 0o600)
    print("workspace map pre-seeded: " + ", ".join(seeded))
PY
  unset HERMES_MAP_PATH HERMES_HC HERMES_HU
fi

chmod 600 "$HERMES_HOME/.env" 2>/dev/null || true

ui_info "Memory" "تفعيل الذاكرة المحلية (Holographic / SQLite) — بدون خادم أو تحميلات خارجية"

mkdir -p "$HOME/.config/subfinder"
{
  [ -n "$github" ]      && printf 'github:\n  - "%s"\n' "$github"
  [ -n "$virustotal" ]  && printf 'virustotal:\n  - "%s"\n' "$virustotal"
  [ -n "$shodan" ]      && printf 'shodan:\n  - "%s"\n' "$shodan"
  [ -n "$urlscan" ]     && printf 'urlscan:\n  - "%s"\n' "$urlscan"
  [ -n "$dnsdumpster" ] && printf 'dnsdumpster:\n  - "%s"\n' "$dnsdumpster"
  [ -n "$zoomeye" ]     && printf 'zoomeyeapi:\n  - "%s"\n' "$zoomeye"
  [ -n "$fofa" ]        && printf 'fofa:\n  - "%s"\n' "$fofa"
} > "$HOME/.config/subfinder/provider-config.yaml"
chmod 600 "$HOME/.config/subfinder/provider-config.yaml" 2>/dev/null || true

[ -n "$vulners" ] && { mkdir -p "$HOME/.config/vulners"; printf '%s\n' "$vulners" > "$HOME/.config/vulners/api.key"; chmod 600 "$HOME/.config/vulners/api.key"; }
[ -n "$nvd" ] && { mkdir -p "$HOME/.config/nvd"; printf '%s\n' "$nvd" > "$HOME/.config/nvd/api.key"; chmod 600 "$HOME/.config/nvd/api.key"; }
[ -n "$wpscan" ] && { mkdir -p "$HOME/.wpscan"; printf '{"api_token":"%s"}\n' "$wpscan" > "$HOME/.wpscan/scan.json"; chmod 600 "$HOME/.wpscan/scan.json"; }
[ -n "$ngrok" ] && { mkdir -p "$HOME/.config/ngrok"; printf 'version: "2"\nauthtoken: %s\n' "$ngrok" > "$HOME/.config/ngrok/ngrok.yml"; chmod 600 "$HOME/.config/ngrok/ngrok.yml"; }
if [ -n "$shodan" ] || [ -n "$zoomeye" ]; then
  mkdir -p "$HOME/.config/uncover"
  {
    [ -n "$shodan" ]  && printf 'shodan:\n  - "%s"\n' "$shodan"
    [ -n "$zoomeye" ] && printf 'zoomeye:\n  - "%s"\n' "$zoomeye"
  } > "$HOME/.config/uncover/provider-config.yaml"
  chmod 600 "$HOME/.config/uncover/provider-config.yaml"
fi


# VPN: auth goes to the key registry (inventory), NOT auth.txt. Profiles keep
# per-provider subfolders so multiple providers can coexist.
[ -n "$vpn_user" ] && { mkdir -p "$HERMES_HOME/toolkit/keys"; printf '%s\n' "$vpn_user" > "$HERMES_HOME/toolkit/keys/vpn_user.key"; chmod 600 "$HERMES_HOME/toolkit/keys/vpn_user.key"; }
[ -n "$vpn_pass" ] && { mkdir -p "$HERMES_HOME/toolkit/keys"; printf '%s\n' "$vpn_pass" > "$HERMES_HOME/toolkit/keys/vpn_pass.key"; chmod 600 "$HERMES_HOME/toolkit/keys/vpn_pass.key"; }
if [ -n "$vpn_profiles_dir" ] && [ -d "$vpn_profiles_dir" ]; then
  mkdir -p "$HOME/vpn-profiles"
  (cd "$vpn_profiles_dir" && find . -name '*.ovpn' -print0 | while IFS= read -r -d '' f; do
     mkdir -p "$HOME/vpn-profiles/$(dirname "$f")"
     cp "$f" "$HOME/vpn-profiles/$f"
     chmod 600 "$HOME/vpn-profiles/$f"
   done)
  ui_info "VPN" "?? ??? ???????? OpenVPN (auth ?? ??? ????????)"
fi

# ── 7) Toolkit first scan + hourly refresh ─────────────────────────────────
if [ -x "$HERMES_HOME/toolkit/toolkit-scan.sh" ]; then
  ui_info "Toolkit" "توليد كتالوج الأدوات والمفاتيح الأول..."
  bash "$HERMES_HOME/toolkit/toolkit-scan.sh" >> "$LOG" 2>&1
  if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v 'toolkit-scan' ; \
      echo "17 * * * * bash $HERMES_HOME/toolkit/toolkit-scan.sh >/dev/null 2>&1" ) | crontab -
  fi
fi

# ── 8) Start gateway ───────────────────────────────────────────────────────
if [ -n "$bot" ]; then
  ui_info "Gateway" "تشغيل بوابة Hermes..."
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  hermes gateway install >> "$LOG" 2>&1
  hermes gateway start >> "$LOG" 2>&1
fi

# ── 8b) Hermes WebUI (side-by-side browser dashboard) ──────────────────────
WEBUI_URL=""
if ask_tool "WebUI" "تثبيت Hermes WebUI (لوحة تحكم المتصفح) جنبًا إلى جنب مع البوابة؟"; then
  ui_info "WebUI" "تثبيت لوحة تحكم المتصفح..."
  if [ ! -d "$HOME/hermes-webui/.git" ]; then
    git clone --depth 1 https://github.com/nesquena/hermes-webui.git "$HOME/hermes-webui" >> "$LOG" 2>&1
  fi
  if [ -x "$HOME/hermes-webui/ctl.sh" ]; then
    export HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-127.0.0.1}"
    export HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8787}"
    (cd "$HOME/hermes-webui" && ./ctl.sh start) >> "$LOG" 2>&1
    WEBUI_URL="http://$HERMES_WEBUI_HOST:$HERMES_WEBUI_PORT"
    ui_info "WebUI" "جاهز: $WEBUI_URL"
  else
    ui_box "WebUI" 8 60 "✗ تعذر العثور على ctl.sh — شاهد $LOG"
  fi
fi

# ── 10) Summary ────────────────────────────────────────────────────────────
MISSING=""
[ -z "$api_key" ] && MISSING="$MISSING
• AI API key (بدونه لن يعمل الوكيل)"
[ -z "$bot" ]  && MISSING="$MISSING
• Telegram bot token (بدونه لن تعمل البوابة)"
[ -z "$ngrok" ]     && MISSING="$MISSING
• ngrok authtoken"

ui_box "Done" 14 68 "
اكتمل التثبيت ✅

الوكيل جاهز. عند أول رسالة في قروب تيليجرام سيجهّز نفسه تلقائيًا
(البوابة تعمل، وأي مفتاح/أداة جديدة تُكتشف ذاتيًا — الاسم والشخصية يُسألان في أول محادثة).

${WEBUI_URL:+لوحة تحكم المتصفح (WebUI): $WEBUI_URL
}
الذاكرة المحلية (SQLite) مفعّلة افتراضيًا — حقائق fact_store في ~/.hermes/memory_store.db
سجل التثبيت: $LOG
الإعدادات: $HERMES_HOME
${MISSING:+أشياء تركتها فارغًا وتضيفها لاحقًا:$MISSING}"
