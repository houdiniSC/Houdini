---
name: toolkit-inventory
description: How to use the dynamic tools & keys catalog — read it first, refresh it, and add keys/tools without changing code.
---

# Toolkit Inventory

## Always read first
- `~/.hermes/toolkit/inventory.yaml` — generated catalog of tools + keys (masked)
- `~/.hermes/toolkit/keys/` — key files; read the actual file when the secret is needed

## Rules
- Never print full keys in chat, logs, or reports. Read into an env var, use it, discard.
- If a needed tool/key is missing, check the filesystem yourself before concluding:
  `command -v <tool>` ; `ls ~/.hermes/toolkit/keys/`
- Refresh the catalog after new installs: `bash ~/.hermes/toolkit/toolkit-scan.sh`

## Adding new capability (user side — no agent conversation needed)
- Tool: install to PATH → scanner picks it up
- Key: drop a file in `keys/` with 0600 → scanner picks it up
- Quota/limit info: read the tool card in `toolkit/tools/` before heavy use
