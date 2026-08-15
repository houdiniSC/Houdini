---
name: attack-cloudflare
description: "Origin-IP discovery behind Cloudflare — subdomain enumeration (own tools), certificate transparency, passive DNS, historical records, direct-IP probing"
category: "web-application"
version: "1.0"
author: "houdini-gateway"
tags:
  - cloudflare
  - origin-ip
  - subdomains
  - passive-dns
  - certificate-transparency
  - web
tech_stack:
  - cloudflare
  - dns
  - web
cwe_ids:
  - CWE-200
chains_with:
  - attack-subdomain-takeover
  - attack-wordpress
prerequisites: []
severity_boost: {}
---

# Cloudflare Origin-IP Discovery

## Objective

Find the **real origin IP** of a site behind Cloudflare. Cloudflare only
protects what DNS points at it — the origin stays reachable directly via its
real IP unless locked down (and it usually is not). This skill hunts that IP
so direct probing/scans hit the real server.

## Golden rules

1. **Verify every candidate.** Cloudflare IP ranges are public
   (`https://www.cloudflare.com/ips-v4` and `-v6`) — a candidate inside those
   ranges is Cloudflare itself, NOT the origin. Always filter them out.
2. **Confirm before scanning.** Once you have a candidate IP, confirm it is
   the origin: `curl -sk --resolve TARGET:443:IP https://TARGET/` must return
   the site (check a known string from the homepage). Wrong IP → different
   site / TLS error.
3. **Prefer passive sources first** (crt.sh, DNS history). They cost nothing
   and often resolve it in seconds. Only fall back to bruteforce/spraying
   when passive sources dry up.
4. **Record evidence** for every candidate: source (crt.sh / subfinder /
   securitytrails...), the IP, and the confirmation result.

## Step 1 — Enumerate subdomains (our own tools first)

```bash
# subfinder (passive sources bundled)
subfinder -d TARGET -silent | tee subs.txt

# every subdomain that is NOT behind Cloudflare can leak the origin
# (misconfigured A records, dev/staging hosts, mail/ftp/vpn prefixes)
```

Filter and resolve:

```bash
cat subs.txt | httpx -silent -status-code -title -ip -cname -o subs-resolved.txt
```

Look specifically for:

- hosts NOT on Cloudflare ranges (bare `A` record to a real IP)
- `dev`, `staging`, `stage`, `test`, `old`, `origin`, `direct`, `mail`,
  `ftp`, `vpn`, `cpanel`, `webmail`, `whm` prefixes
- `CNAME` chains pointing to non-Cloudflare providers (they may proxy to
  the real origin)

## Step 2 — Certificate transparency (passive, zero auth)

```bash
# crt.sh — every cert ever issued for the domain (subdomain discovery too)
curl -sk "https://crt.sh/?q=%25.TARGET&output=json" | jq -r '.[].name_value' | sort -u > crt-names.txt

# the SAN list often includes origin-only names (origin.example.com, *.internal)
cat crt-names.txt | while read h; do dig +short "$h" A; done | sort -u | grep -vE '^(104\.|172\.6[4-9]\.|173\.245\.|188\.114\.|190\.93\.)' | tee candidates.txt
```

Cloudflare edge ranges to exclude (v4):
`104.16.0.0/13 104.24.0.0/14 172.64.0.0/13 131.0.72.0/22 141.101.64.0/18 162.158.0.0/15 173.245.48.0/20 188.114.96.0/20 190.93.240.0/20 197.234.240.0/22 198.41.128.0/17`

## Step 3 — External passive sources (DNS history & internet-wide DBs)

Use whichever are reachable (no paid API assumed — free tiers only):

```bash
# SecurityTrails free DNS history (requires free API key if configured)
curl -sk "https://api.securitytrails.com/v1/history/TARGET/dns/a" -H "APIKEY: $ST_KEY" | jq -r '.records[].values[].ip' | sort -u

# ViewDNS.info (no key)
curl -sk "https://viewdns.info/iphistory/?domain=TARGET" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u

# SecurityTrails historical via the free "DNS Trails" web endpoint is blocked;
# fall back to dnsdumpster-style scraping only if reachable.
```

Other free lookups to try when the above fail: `censys.io` (search API free
tier), `shodan.io` (`ssl.cert.subject.cn:TARGET`), `fofa.info`, `hunter.how`.
Search each for `TARGET` in SSL certs and banners — origins serving the same
cert/banner appear with their real IP.

## Step 4 — Direct-IP probing (confirm candidates)

```bash
# fetch the site THROUGH the candidate IP, sending the right Host header
for ip in $(cat candidates.txt | sort -u); do
  echo "== $ip =="
  curl -sk --resolve TARGET:443:$ip "https://TARGET/" -o /tmp/origin-check-$ip.html -w "code:%{http_code} size:%{size_download}\n"
done
```

A candidate is CONFIRMED when `/tmp/origin-check-<ip>.html` contains a known
string from the real homepage (title tag, unique css path) AND the TLS cert
matches the domain (or is a wildcard/self-signed the origin uses).

Bonus probes on confirmed-origin candidates:

- `http://IP` (plain HTTP on the origin — many origins answer on :80 directly)
- `https://IP` with `-k` (self-signed origin cert)
- common origin ports: `nmap -Pn -p 80,443,8080,8443,22 $ip` (only with the
  operator's scan authorization for that target)

## Step 5 — Fallbacks when nothing leaked

- **SPF records**: `dig TXT TARGET +short` — `include:` hosts and raw IPs in
  SPF are often the mail origin = same infra as the web origin.
- **MX records**: `dig MX TARGET +short` — mail server IP can share hosting.
- **Old DNS**: check `dns.google` / `dnschecker.org` history pages via curl.
- **Subdomain bruteforce**: `gobuster dns -d TARGET -w <wordlist> -t 50`
  where `<wordlist>` is
  `/usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt` if
  SecLists is installed, otherwise fetch it once:
  `curl -fsSL -o /tmp/subs5k.txt https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/DNS/subdomains-top1million-5000.txt`
  and use `/tmp/subs5k.txt`.

## Report

Follow `skills/report-template`. Sections: subdomain map (behind-CF vs
direct), candidates table (IP, source, CF-range? confirmed?), confirmed
origin IP(s) with evidence command, exposed services on origin, remediation
(origin firewall allowlist-only to Cloudflare ranges, block direct HTTP).

## Pitfalls

- `--resolve` on curl needs the SAME port as the URL scheme; mixing breaks TLS
  SNI — keep `--resolve TARGET:443:IP` for https.
- Some origins bind vhosts: direct IP without Host header returns a default
  page — always send the Host header.
- WAFs block scanner UAs; use `-A "Mozilla/5.0 ..."` on confirmations.
- Cloudflare now proxies some `direct`/`origin` prefixes too — every candidate
  still goes through the range filter and the confirmation curl.
- Never scan the discovered origin directly without the operator's
  authorization for that target — discovery is passive; active probing is a
  scan step.
