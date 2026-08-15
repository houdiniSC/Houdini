---
name: attack-wordpress
description: "WordPress recon — version & plugin fingerprinting from the site index itself (no wpscan API needed), known-vuln matching, XML-RPC/config checks"
category: "web-application"
version: "1.0"
author: "houdini-gateway"
tags:
  - wordpress
  - cms
  - wpscan
  - fingerprinting
  - plugins
  - web
tech_stack:
  - wordpress
  - php
  - web
cwe_ids:
  - CWE-200
  - CWE-284
chains_with:
  - attack-subdomain-takeover
prerequisites: []
severity_boost: {}
---

# WordPress Recon & Vulnerability Mapping

## Objective

Fingerprint a WordPress site's **version** and **plugins/themes** (with their
versions) and map them to known vulnerabilities. **wpscan's API is optional —
the whole flow works from the site index itself**, so nothing stops when the
wpscan API quota (25 req/day free) is exhausted.

## Golden rules

1. **Index-first.** WordPress exposes its version and plugin list in the HTML
   of the site itself. Scrape it BEFORE burning any wpscan API quota.
2. **Budget wpscan API.** Free token = 25 requests/day. Use it only when the
   passive pass found something worth enumerating (users, backup files).
3. **Every finding needs a version number.** "Plugin X installed" is weak;
   "Plugin X v1.4.2 (CVE-2022-xxxx)" is actionable. Keep digging until you
   have the version.
4. **Verify before reporting.** A vulnerable version is not a vulnerable
   site. Confirm the exploit path exists (route reachable, feature enabled)
   and mark each finding as confirmed / unconfirmed.

## Step 1 — Passive fingerprinting (no API, no wpscan)

Run these against the target and capture EVERY version string:

```bash
# generator meta tag (wp version)
curl -sk "https://TARGET/" | grep -oiE '<meta name="generator"[^>]*>' 

# readme.html — leaks version + install confirmation
curl -sk -o /dev/null -w "%{http_code}\n" "https://TARGET/readme.html"

# wp-json root — plugin & theme list (names, sometimes versions)
curl -sk "https://TARGET/wp-json/" | jq .

# wp-json users — author/user enumeration
curl -sk "https://TARGET/wp-json/wp/v2/users?per_page=100" | jq '.[].slug'

# theme + plugin paths from the HTML source (css/js links leak slugs)
curl -sk "https://TARGET/" | grep -oE "wp-content/(plugins|themes)/[a-z0-9-]+" | sort -u
```

Also try (each is a cheap curl, each can leak a version):

```bash
# classic readme.txt of plugins (version + changelog header)
curl -sk "https://TARGET/wp-content/plugins/PLUGIN_SLUG/readme.txt" | head -20

# main plugin file header (Stable tag:)
curl -sk "https://TARGET/wp-content/plugins/PLUGIN_SLUG/PLUGIN_SLUG.php" | grep -iE "version|stable"

# wp-links-opml.php, license.txt, xmlrpc.php reachability
for p in wp-links-opml.php license.txt xmlrpc.php wp-cron.php; do
  echo -n "$p: "; curl -sk -o /dev/null -w "%{http_code}\n" "https://TARGET/$p"
done

# classic sensitive leftovers (READMEs, backups, debug, install)
for p in wp-config.php.bak wp-config.php~ wp-config.php.save wp-config.php.swp \
         .wp-config.php.swp wp-content/debug.log readme.html backup.zip \
         wp-content/uploads/woocommerce_uploads/; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://TARGET/$p"); echo "$p -> $code"
done
```

Build two lists from everything above:

- **CORE_VERSION** — from generator meta / readme / wp-json (`wp-json` root
  does NOT give the version; use the HTML source or `wp-json` routes that
  embed it, e.g. versioned assets like `?ver=6.4.3` query strings on css/js).
- **PLUGINS** — `slug + version` pairs (`?ver=` query strings on plugin
  css/js are the most reliable version leak on modern themes).

## Step 2 — wpscan (ONLY after the passive pass, and only if API budget remains)

```bash
# passive (no API): theme/plugin slugs + versions from HTML
wpscan --url https://TARGET --no-banner --random-user-agent -e u,vt,tt --plugins-detection passive

# with API: vulnerability matching for what we already found
wpscan --url https://TARGET --no-banner --random-user-agent --api-token $(cat ~/.wpscan/scan.json | jq -r .api_token) -e vp,vt,u

# if the API quota is exhausted (25/day): STILL run the passive enum and
# the direct checks below — never skip the assessment because of the API.
```

If the token is exhausted or missing: skip `-e vp` (vulnerable plugins) and
match versions manually against known vulns (Step 3).

## Step 3 — Manual version → CVE mapping (works with zero API)

For each `slug@version` found:

1. Web-search / memory lookup: `<slug> <version> vulnerability CVE`
   (e.g. `elementor 3.5.2 CVE`, `woocommerce 8.2 vulnerability`).
2. Record the CVE, severity, type (SQLi/XSS/RCE/arbitrary file read...),
   affected range (`<= 3.5.2`), and fixed version.
3. Check the exploit path:
   - File-read/RCE via known endpoint? `curl -sk "https://TARGET/wp-content/plugins/<slug>/<vuln-route>"`
   - Auth-required? Mark as `unconfirmed — requires auth`.
   - Theme/plugin deactivated? Check the HTML for its assets; if absent, mark
     `not loaded — likely inactive`.

Only report a finding as **confirmed** when the vulnerable route/behavior was
actually observed. Otherwise it is `unconfirmed (version match only)`.

## Step 4 — WordPress-core vulns

Core versions have their own CVE timeline. For CORE_VERSION found:

- `<= 4.7.3` → REST API content injection (CVE-2017-1001000)
- `4.8.2` / `4.9.x` era → check wpscan database for the exact minor
- `5.5.x` → XML-RPC amplification era; check xmlrpc.php reachable
- Recent minors → latest patches fixed listed CVEs; flag only if the site is
  noticeably behind (2+ minors back from latest stable).

## Step 5 — XML-RPC & user checks (independent of versions)

```bash
# xmlrpc reachable?
curl -sk -o /dev/null -w "%{http_code}\n" "https://TARGET/xmlrpc.php"

# system.listMethods probe (cheap, no auth)
curl -sk -X POST "https://TARGET/xmlrpc.php" -d '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>'

# wp.getUsersBlogs brute signal (username oracle)
curl -sk -X POST "https://TARGET/xmlrpc.php" -d '<?xml version="1.0"?><methodCall><methodName>wp.getUsersBlogs</methodName><params><param><value>admin</value></param><param><value>wrongpass</value></param></params></methodCall>'
```

`wp.getUsersBlogs` returning a login error for a guessed name = valid username
(no rate limiting on many hosts → brute signal, report as finding).

## Report

Follow `skills/report-template`. Sections: version summary (core + plugins
table with CVE mapping), confirmed findings, unconfirmed leads, exploitation
paths, recommendations. Every finding carries its evidence command.

## Pitfalls

- `?ver=` strings are sometimes removed by cache plugins — fall back to
  plugin `readme.txt` headers.
- HTTPS-only sites: `curl -sk` for self-signed, but prefer following redirects
  (`-L`) and adding a browser UA to avoid WAF blocks.
- Cloudflare/WAF in front (see `attack-cloudflare`): fingerprint from cached
  pages; the real origin may differ — resolve the real IP first.
- Do NOT run brute-force or authenticated exploitation without the
  operator's explicit «ابدأ الفحص» authorization for that target.
