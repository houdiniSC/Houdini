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
.\bootstrap-wsl.ps1
```

Creates an isolated WSL distro (`HoudiniGateway`) running the Houdini agent
(Hermes engine + full toolchain) and launches the terminal wizard. Provide
the rootfs locally to skip even the clone's rootfs download:

```powershell
$RootfsPath = 'C:\path\to\ubuntu-rootfs.tar.gz'; .\bootstrap-wsl.ps1
```

## One-liner (PowerShell, from GitHub)

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'; irm "$src/bootstrap-wsl.ps1" | iex
```

The one-liner downloads the repo zip once and reuses the rootfs chunks
inside it (no extra rootfs download). Or point it at a local rootfs:

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'; $RootfsPath = 'C:\path\to\ubuntu-rootfs.tar.gz'; irm "$src/bootstrap-wsl.ps1" | iex
```

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

For a fast scripted install, copy `secrets.env.example` to `secrets.env`
next to `install-hermes.sh` and fill the values — same field names as the
wizard's encrypted `.hcfg` config.

## Security

Never commit `install-config.json`, `secrets.env`, `*.hcfg`, or the rootfs
to this repository. Encrypted configs are created locally with
`config-tool/encrypt-config.ps1` (pure PowerShell - no WSL needed) and
transferred separately:

```powershell
.\config-tool\encrypt-config.ps1 C:\path\install-config.json
```
