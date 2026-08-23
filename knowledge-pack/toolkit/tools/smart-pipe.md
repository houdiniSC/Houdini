# smart_pipe

- Category: output filtering / token economy
- Usage: `<tool ...> | smart_pipe --target <slug> --tool <name> [--max-tokens 1200]`
- What it does: keeps the FULL raw output on disk (`~/recon/<slug>/<name>_raw.txt`)
  and prints only high-signal lines (sorted by security relevance) to stdout.
- Signal scoring: critical findings (CVE/RCE/SQLi/IDOR/SSRF...) highest, then
  secrets (.env/tokens/keys), HTTP statuses with API paths, dynamic params,
  UUIDs, and high-entropy strings. Static assets (images/css/fonts) dropped.
- JSON-aware: nuclei/subfinder/httpx `-json` lines are digested to one compact
  line each (host + severity + template id) instead of raw blobs.
- Token budget: `--max-tokens` caps what enters the agent context (default
  1200 ≈ 900 words). Everything else stays on disk for the report.
- ALWAYS pipe verbose tools through it (nuclei, ffuf, katana, dirsearch,
  subfinder+httpx). Never pipe already-short outputs (dig, curl single checks).
- Never read `*_raw.txt` back into context — grep/summarize it instead.
