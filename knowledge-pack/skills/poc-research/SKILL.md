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

## Phase 0 — Gather everything (parallel, cheap)

1. Local helpers: `cve2poc`, vulners API (header `X-Api-Key` — see toolkit)
2. GitHub code search (search by CVE id, product + version, error string)
3. Exploit-DB, PacketStorm, NVD references, GitHub security advisories
4. Vendor advisories + changelogs + security bulletins
5. Web search: `<product> <version> exploit poc CVE`

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
