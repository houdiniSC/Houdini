---
name: browser-capture
description: "Capture authenticated browser traffic through a local proxy (Playwright + mitmproxy) and feed the results into the recon/testing workflow"
category: "recon"
version: "1.0"
author: "hermes-official"
tags:
  - browser
  - proxy
  - capture
  - traffic
  - recon
tech_stack:
  - web
cwe_ids: []
chains_with:
  - attack-idor-automation
  - attack-ssrf
  - attack-ssti
  - attack-xxe
  - attack-cors
  - attack-host-header
  - attack-open-redirect
  - attack-jwt
  - attack-prototype-pollution
  - attack-graphql
  - attack-race-condition
  - attack-request-smuggling
  - attack-websocket
  - attack-cache-poison
  - attack-rate-limit-bypass
  - attack-subdomain-takeover
prerequisites:
  - browser-capture.py present in toolkit/tools
---

# Browser Traffic Capture (HackBrowser-style)

## Objective

Drive a real browser through the target (optionally logged in with multiple
roles), intercept every HTTP request with a local proxy, and export the
unique endpoints as JSON so the testing workflow can probe them
methodically.

## Pipeline

```
Playwright (Chromium) --> mitmproxy (127.0.0.1:18080) --> flows.json --> probes
```

## Steps

### 1. One-time setup (first use only)

```bash
python3 -m pip install playwright mitmproxy
python3 -m playwright install chromium
```

(In the gateway this is already provisioned; verify with
`browser-capture.py --install`.)

### 2. Capture

Default crawl (load the URL and follow up to 10 same-scope links):

```bash
browser-capture.py --url https://target.com --scope target.com --out /tmp/target-flows.json
```

Authenticated capture with a custom driver (login flows, multiple roles):
write a small `driver.py` and run it per role:

```python
import os

async def drive(page, role):
    await page.goto("https://target.com/login")
    await page.fill("#username", os.environ["USER_ADMIN"])
    await page.fill("#password", os.environ["PASS_ADMIN"])
    await page.click("button[type=submit]")
    await page.wait_for_load_state("domcontentloaded")
    await page.goto("https://target.com/dashboard")
    # browse the areas you want tested
```

```bash
USER_ADMIN=... PASS_ADMIN=... BROWSER_CAPTURE_ROLE=admin \
  browser-capture.py --url https://target.com --scope target.com \
  --script driver.py --out /tmp/target-admin.json
```

Capture at least two roles (low-priv and admin) — the testers need both a
high-privilege baseline and low-privilege credentials.

### 3. Feed the testers

For each unique flow in the JSON:

- Run the relevant attack-* skill with the request (method, URL, headers,
  body) and the role context.
- Follow the 3-gate protocol: baseline with the original token/role, attack
  request, compare responses. Report only measurable, reproducible
  differences.

## Output format (flows.json)

```json
{
  "role": "admin",
  "count": 12,
  "flows": [
    {
      "method": "GET",
      "url": "https://target.com/api/users/1",
      "status": 200,
      "cookies": {},
      "sensitive_headers": {"authorization": "Bearer ..."},
      "content_type": "application/json",
      "request_body": null
    }
  ]
}
```

## Rules

- Never store captured credentials in reports — use masked tokens.
- Scope filter is mandatory; drop third-party calls (analytics, CDN).
- Do not test the same endpoint twice with the same vector (dedupe by
  method + path happens in the tool).
- If a role fails to log in, capture with `--mode curl` for the unauthenticated
  surface and retry the browser flow with corrected selectors.
