---
name: recon-playbook
description: Standard web recon methodology — scoping, passive enumeration, tech detection, targeted scanning, validation, reporting. Target-agnostic.
---

# Recon Playbook

## 0. Scope & authorization
- Only proceed when the user explicitly declared the target authorized.
- Record the declared scope in `~/recon/<target>/SCOPE.md` before scanning.
- Target folder layout (see SOUL.md "Work layout"): `evidence/`, `poc/`,
  `reports/`, `logs/` under `~/recon/<target>/` — create them on intake.

## 1. Passive phase (no contact with the target)
- WHOIS / certificate transparency (crt.sh)
- Subdomain enumeration: subfinder (see `toolkit/tools/subfinder.md`)
- Historical data: Wayback CDX, urlscan, DNSDumpster
- Technology fingerprinting from search results / third-party sources

## 2. Active mapping (light touch)
- DNS resolution: `dig` / `host` for all discovered names
- HTTP probing: httpx (status, title, tech, TLS)
- Cloudflare/origin detection: compare IPs against Cloudflare ranges; MX history may reveal the origin

## 3. Targeted scanning
- Choose the right tool card per detected stack (WordPress → wpscan; Drupal → droopescan/drupwn; generic → nuclei)
- Port scan only declared target IPs (`nmap -sV`)
- Directory/content discovery: gobuster/ffuf with wordlists, respecting rate limits

## 4. Validation (never report theoretical)
- Every finding needs proof: exact request/response evidence
- Confirm vulnerability paths non-destructively (see `skills/poc-research`)

## 5. Reporting
- Write the report file per `skills/report-template`
- Save raw outputs under `~/recon/<target>/`
- Deliver per `skills/telegram-delivery`

## Discipline
- Traffic moderate, batched, with delays; API quotas respected (see toolkit inventory)
- If a step needs a missing tool/key, check the toolkit yourself — do not assume
