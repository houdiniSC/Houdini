---
name: poc-research
description: How to research, analyze, adapt, and execute published Proof-of-Concept exploits safely, with source-code review as the last resort.
---

# PoC Research

## Sources (in order)
1. Local helpers: cve2poc, vulners API (header `X-Api-Key` — see toolkit)
2. GitHub code search (authenticated; search by CVE id, product + version)
3. Exploit-DB, PacketStorm, NVD references
4. Vendor advisories + changelogs (version diffing)
5. Web search

## Analysis before execution
- Read the PoC completely; identify: root cause, trigger condition, required preconditions (auth? version? config?)
- Map the affected endpoint/parameter to the target's actual surface
- Understand what the PoC does at each step — never run it blind

## Adaptation
- Adjust paths, parameters, headers, cookies, CSRF tokens to the target
- If a published PoC fails, try: alternate payload encodings, protocol variants, version-specific offsets
- Think outside the box: chained gadgets, alternate entry points, race conditions

## Source code as last resort
- Only when published avenues are exhausted: read vendor patches/commits to derive the flaw
- Reconstruct the vulnerable logic in a local harness when possible

## Execution safety
- Non-destructive by default: no writes, deletions, or system-modifying payloads
- Proof of execution = minimal demonstration, then stop
- Log every step to `~/recon/<target>/` for the report
