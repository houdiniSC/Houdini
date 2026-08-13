---
name: vpn-egress
description: "Egress via OpenVPN profiles (~/vpn-profiles) — ProtonVPN & generic .ovpn, auth-user-pass, connect/verify/rotate/stop, dynamic profile discovery. Never writes memory."
category: "network"
version: "1.0"
author: "hermes-official"
tags:
  - network
  - vpn
  - egress
  - openvpn
  - protonvpn
tech_stack: []
cwe_ids: []
chains_with:
  - recon-playbook
prerequisites: []
---

# VPN Egress — OpenVPN Profiles (ProtonVPN & generic)

## Where the assets live (discover, do not memorize)

- Profiles: `~/vpn-profiles/*.ovpn` (one file per exit server)
- Credentials: `~/vpn-profiles/auth.txt` — line 1 = username, line 2 = password
- Manifest: `~/.hermes/toolkit/assets/manifest.json` — registered names + hashes + backups
- Catalog: `~/.hermes/toolkit/inventory.yaml` → `vpn_profiles.count` and
  `keys.vpn.status` (masked). Refresh with
  `bash ~/.hermes/toolkit/toolkit-scan.sh` if it looks stale.

These files are the source of truth. Never copy them into memory, SOUL.md, or a
skill. If a new profile is added on disk, it is picked up automatically — list
the folder, don't assume.

## Self-heal before use

1. Compare `~/vpn-profiles/*.ovpn` with the manifest's `profiles` section.
2. Missing profile → restore from `~/.hermes/toolkit/backups/`, re-run
   `bash ~/.hermes/toolkit/toolkit-scan.sh`, note the restoration.
3. Backup also missing → report to ⚙️ الإعدادات (profile gone, re-send it);
   use a different profile in the meantime if one exists.

## Workflow

1. **List available profiles** (dynamic — new files appear without any config):
   ```bash
   ls -1 ~/vpn-profiles/*.ovpn
   ```
2. **Connect** (openvpn needs root; auth comes from the auth file, never inline):
   ```bash
   sudo openvpn --config ~/vpn-profiles/<profile>.ovpn \
     --auth-user-pass ~/vpn-profiles/auth.txt \
     --daemon --writepid /tmp/openvpn-hermes.pid --log /tmp/openvpn-hermes.log
   ```
3. **Wait and verify** — do not proceed until egress is confirmed:
   ```bash
   for i in $(seq 1 10); do
     curl -fsS -m 3 https://api.ipify.org && break
     sleep 1
   done
   curl -fsS -m 5 https://ifconfig.me   # second confirmation
   ```
   If the user asked for a specific exit country, confirm the IP geolocation
   matches before running the task.
4. **Check for DNS leaks** (quick, one command):
   ```bash
   resolvectl query example.com 2>/dev/null || nslookup example.com
   ```
5. **Rotate** when a target blocks the current exit IP:
   stop → pick another profile from step 1 → connect → re-verify the new IP.
6. **Stop** when done:
   ```bash
   sudo kill "$(cat /tmp/openvpn-hermes.pid)" 2>/dev/null || sudo pkill -f 'openvpn --config'
   ```

## ProtonVPN notes

- The OpenVPN login is **not** the account password — use the dedicated
  OpenVPN username/password from the ProtonVPN account panel, in
  `~/vpn-profiles/auth.txt` (line 1 / line 2, chmod 600).
- Some `.ovpn` files embed `tls-crypt`/`tls-auth` keys inline — keep the file
  intact and 0600; never print its contents.
- Different profiles = different exit servers/countries. Prefer the closest
  or least-loaded one for latency; rotate on blocks.

## Guards

- Never print `auth.txt`, passwords, or any key material — read into the
  command, keep output redacted.
- Use the VPN only when the task requires it (target geo/ISP behavior,
  callback egress); keep traffic moderate.
- Do not write these asset locations into memory — they are discoverable
  through the toolkit catalog and this skill.
