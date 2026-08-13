# Houdini Gateway

Production installer for the **Houdini** security gateway — an isolated
WSL2 workspace (Hermes engine) with a full security toolchain and
knowledge pack. Houdini is your offensive security assistant for testing
web applications, websites, and mobile APKs.

## Install (fastest: git clone)

Clone once (the package and the rootfs chunks download together), then run
the bootstrap from the clone — it reuses the bundled rootfs, no second
download:

```powershell
git clone https://github.com/houdiniSC/Houdini.git
cd Houdini
.\src\install-wsl.ps1
```

Creates an isolated WSL distro (`HoudiniGateway`) running the Houdini agent
(Hermes engine + full toolchain) and launches the terminal wizard. Provide
the rootfs locally to skip even the clone's rootfs download:

```powershell
$RootfsPath = 'C:\path\to\ubuntu-rootfs.tar.gz'; .\src\install-wsl.ps1
```

## One-liner (PowerShell, from GitHub)

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'; irm "$src/src/install-wsl.ps1" | iex
```

The one-liner downloads the repo zip once and reuses the rootfs chunks
inside it (no extra rootfs download). Or point it at a local rootfs:

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'; $RootfsPath = 'C:\path\to\ubuntu-rootfs.tar.gz'; irm "$src/src/install-wsl.ps1" | iex
```

## Native Ubuntu (no WSL)

Clone the repo and run the shell installer (whiptail UI) directly on an
Ubuntu machine:

```bash
git clone https://github.com/houdiniSC/Houdini.git
cd Houdini
bash src/install-ubuntu.sh
```

It reads optional settings from `src/secrets.env` (copy
`src/secrets.env.example`) and writes the install log to
`/tmp/houdini-bootstrap.log`.

## Remove the distro

Stop and delete the WSL distribution completely (filesystem, agent user,
services, and its Windows menu entry):

```powershell
wsl --unregister HoudiniGateway
```

The cached rootfs in `%TEMP%\hermes-rootfs.tar.gz` stays behind — delete it
manually for a fully clean slate.

## Config

Only two values are required at install: an AI model API key (any
OpenAI-compatible provider - DeepSeek, OpenAI, OpenCode or a custom
endpoint) and the Telegram bot token. Everything else is optional and
can be detected or added later at first conversation.

For a fast scripted install, copy `src/secrets.env.example` to
`src/secrets.env` next to `install-ubuntu.sh` and fill the values — same
field names as the wizard's encrypted `.hcfg` config.

## Security

Never commit `install-config.json`, `secrets.env`, `*.hcfg`, or the rootfs
to this repository. Encrypted configs are created locally with
`src/config-tool/encrypt-config.py` (cross-platform Python) and transferred
separately:

```bash
python3 src/config-tool/encrypt-config.py C:\path\install-config.json
```
