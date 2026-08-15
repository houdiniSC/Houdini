---
name: poc-research
description: "PoC research & engineering — try published PoCs, cross-compare & chain them into a working exploit, then derive the flaw from the vendor's own fix diff as the final source of truth"
---

# PoC Research & Engineering

## Objective

Turn a CVE / vulnerable product into a **working, confirmed PoC** against an
authorized target. The pipeline is graduated: published PoCs first (cheapest),
cross-PoC comparison & chaining next, and the **vendor fix diff** last — the
diff is the most reliable oracle because the patch itself shows the exact
vulnerable logic, even when no PoC exists.

## Phase 0 — Gather everything (ACTIVE WEB SEARCH FIRST, then local tools)

Local helpers (cve2poc, vulners API) go stale and hit quota walls —
treat them as a fallback, never as the primary source. Your **live web
search keys** find fresh PoCs, writeups, and patches the day they land.
Keys live in `~/.hermes/toolkit/keys/<service>.key` (masked in
`inventory.yaml` — read the file when you use it).

```bash
K=~/.hermes/toolkit/keys   # key dir; read what exists first: ls $K
Q='CVE-2024-xxxx OR "<product>" "<version>" exploit PoC'   # build the query

# 1) SerpAPI — Google results (pages, GitHub, blogs, advisories)
SERP=$(cat $K/serpapi.key 2>/dev/null)
[ -n "$SERP" ] && curl -s "https://serpapi.com/search.json?engine=google&q=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")&num=20&api_key=$SERP" \
  | jq -r '.organic_results[]? | "\(.link)  |  \(.title)"'

# 2) Brave Search API — independent index, good for fresh PoCs
BRAVE=$(cat $K/brave.key 2>/dev/null)
[ -n "$BRAVE" ] && curl -s "https://api.search.brave.com/res/v1/web/search?q=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")&count=20" \
  -H "Accept: application/json" -H "X-Subscription-Token: $BRAVE" \
  | jq -r '.web.results[]? | "\(.url)  |  \(.title)"'

# 3) GitHub API — repositories, code, issues, commits (token: 5000 req/h
#    instead of 60; also unlocks code search)
GHT=$(cat $K/github.key 2>/dev/null)
AUTH=(); [ -n "$GHT" ] && AUTH=(-H "Authorization: Bearer $GHT")
curl -s "https://api.github.com/search/repositories?q=${Q// /+}&per_page=20" "${AUTH[@]}" | jq -r '.items[]? | .html_url'
curl -s "https://api.github.com/search/issues?q=${Q// /+}&per_page=20" "${AUTH[@]}" | jq -r '.items[]? | .html_url'
[ -n "$GHT" ] && curl -s "https://api.github.com/search/code?q=${Q// /+}&per_page=20" "${AUTH[@]}" | jq -r '.items[]? | .html_url'
# commits/PRs touching the CVE (best early signal — often links the fix diff)
curl -s "https://api.github.com/search/commits?q=${Q// /+}&per_page=20" "${AUTH[@]}" | jq -r '.items[]? | .html_url'

# 4) NVD + Exploit-DB + PacketStorm directly (no quota, public JSON)
curl -s "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2024-xxxx" | jq -r '.vulnerabilities[0].cve | {description: .descriptions[0].value, refs: [.references[].url]}'
curl -s "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv" | grep -i "<cve-or-keyword>"

# 5) ONLY THEN the local helpers: cve2poc, vulners (header X-Api-Key — see
#    toolkit) — they cover history; the web search above covers the present.
```

Search query recipes (run several in parallel — different angles):

- `"<CVE>" exploit` / `"<CVE>" poc github`
- `"<product>" "<version>" vulnerability`
- `"<product>" security advisory patch`
- `site:github.com "<CVE>"`
- `"<CVE>" diff patch commit`

Save every PoC variant found: `~/recon/<target>/pocs/<name>-<sha1>.py|.sh|.md`.
Collect MANY variants of the same CVE — different authors cover different
corners; this matters in Phase 2.

## Phase 1 — Try published PoCs as-is (fastest path)

- Read each PoC completely FIRST: root cause, trigger condition,
  preconditions (auth? version? config? race?), and what every step does.
- Map the affected endpoint/parameter to the target's actual surface.
- Run it. Log input, output, and exit state to `~/recon/<target>/pocs/`.
- If it works: confirm the impact minimally, capture evidence, stop. Done.
- If it fails: record WHY precisely (error message, HTTP code, wrong offset,
  missing route, blocked primitive...). The failure mode is data for Phase 2.

Adaptation before giving up on a PoC:
- alternate payload encodings, protocol variants, version-specific offsets
- adjust paths/params/headers/cookies/CSRF tokens to the target

## Phase 2 — Cross-PoC comparison (the failed PoCs talk to each other)

Different PoCs for the same CVE often solve each other's problems:

1. **Diff the PoCs against each other**: what does variant B do that variant
   A doesn't? (different trigger, encoding, bypass, prerequisite)
2. **Harvest the workarounds**: one PoC may carry the exact bypass
   (e.g. encoding, header, timing, race) that another one lacks.
3. **Map the overlap**: build a table — PoC × (trigger point, payload style,
   bypass used, failure mode on target). The gaps in the table are the
   missing pieces.

Rule: **a failing PoC is never discarded** — extract every non-default
trick from it before moving on.

## Phase 3 — Chain the PoCs into one complete exploit

- Combine Phase 2 findings: trigger from PoC A + bypass from PoC B +
  encoding from PoC C = working chain.
- Order matters: write the chain as numbered stages (setup → trigger →
  confirmation), test each stage in isolation before joining.
- Chained gadgets beyond the CVE itself: an "unrelated" primitive found in
  the target (open redirect, IDOR, weak session) can be the missing link —
  use it.
- Keep the chain minimal: every extra step is a new failure surface.

If the chain still fails — do NOT keep guessing blindly. Go to Phase 4.

## Phase 4 — Vendor fix diff (the oracle; works even with ZERO PoCs)

The patch that fixed the CVE literally shows the vulnerable code. Derive the
exploit from it:

```bash
# 1) Get the source — exact vulnerable version (release tarball or git tag)
git clone --depth 200 <vendor repo> /tmp/src-<product>
cd /tmp/src-<product>

# 2) Find the fix commit
git log --oneline --all --grep="CVE-2024-xxxx"          # by CVE id
git log --oneline --all --grep="security" --grep="XSS"  # by keyword
git log -S "sanitize" --oneline                          # by added code

# 3) Diff vulnerable vs fixed (commit or tag)
git show <fix_commit> --stat                            # which files changed
git show <fix_commit> -- <file>                          # the exact change
# or between release tags:
git diff v1.2.3 v1.2.4 -- <relevant paths>
```

What the diff tells you (ask these questions in order):

1. **Which file/function changed?** → that is the vulnerable surface.
2. **What was added?** (input check, length limit, escape, signature verify,
   permission check) → that is the exact missing defense = the bug class.
3. **What was removed/changed?** (dangerous sink, weak default) → the
   vulnerable parameter or call.
4. **The commit message & linked issue** → exploit preconditions, severity,
   and sometimes a reproducer.

Then reconstruct the attack backwards from the fixed code: craft an input
that the OLD code would have accepted but the NEW code blocks. That input IS
your PoC skeleton. Finish it with the techniques from Phases 1-3.

For interpreted projects (PHP/Python/JS) the diff is directly readable; for
compiled ones (C/Rust/Go) the diff still names the function and the added
check — replicate it in a local harness when possible.

## Execution safety (all phases)

- Non-destructive by default: no writes, deletions, or system-modifying
  payloads against the target.
- Proof of execution = minimal demonstration, then stop. No deepening.
- Every step logged to `~/recon/<target>/` for the report: which PoC was
  tried, why it failed, what was chained, and the diff commit that unlocked
  the exploit.
- PoCs from public repos may contain backdoors — read them fully before
  running anything with privileges; sandbox unknown code.
