# Hermes Bootstrap

Production installer for an isolated Hermes gateway (WSL2 Ubuntu) with a
full security toolchain and knowledge pack.

## One-liner (PowerShell)

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'
irm "$src/bootstrap-wsl.ps1" | iex
```

Creates an isolated WSL distro (`HermesGateway`), installs Hermes + tools,
and launches the terminal wizard. Provide the rootfs locally to skip the
download:

```powershell
$src = 'https://raw.githubusercontent.com/houdiniSC/Houdini/main'
$RootfsPath = 'C:\path\to\ubuntu-rootfs.tar.gz'
irm "$src/bootstrap-wsl.ps1" | iex
```

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
