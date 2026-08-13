# browser-capture

- Category: authenticated traffic capture (proxy + browser)
- Usage: `browser-capture.py --url https://target --scope example.com --out flows.json`
- Modes: `--mode browser` (Playwright+Chromium) / `--mode curl` (lightweight) / `--script driver.py` (custom login flows)
- One-time setup: `browser-capture.py --install`
- Notes: proxy on 127.0.0.1:18080 (override with --proxy-port), TLS errors ignored, output filtered to scope and deduped by method+path. Feeds the attack-* skills in the recon/testing workflow.
