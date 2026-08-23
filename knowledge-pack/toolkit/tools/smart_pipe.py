#!/usr/bin/env python3
"""
smart_pipe.py — Smart Output Filter & Token Saver (Houdini edition)

Captures full raw security tool outputs to disk and streams only
prioritized, high-signal results to stdout. Prevents context-window
bloat and token exhaustion in the agent.

Inspired by Cybermes smart_pipe (PolyForm-licensed upstream) — rewritten
for the Houdini gateway:
  - token budget instead of fixed line count
  - JSON-aware scoring (nuclei/subfinder/httpx -json outputs)
  - saves raw under ~/recon/<target>/ like every other Houdini artifact
  - Houdini toolchain markers (subfinder, httpx, nuclei, ffuf, wpscan)

Usage:
  subfinder -d example.com | smart_pipe --target example.com --tool subfinder
  nuclei -u https://x -json | smart_pipe --target x --tool nuclei --max-tokens 1200
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-9?]*[ -/]*[@-~])")
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)

STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".css", ".mp4", ".mp3", ".webm", ".avi", ".mov", ".map",
)

CRITICAL_MARKERS = (
    "[critical]", "[high]", "cve-", "rce", "sql injection", "sqli",
    "idor", "ssrf", "xxe", "auth bypass", "lfi", "path traversal",
    "reflected xss", "stored xss", "open redirect", "template injection",
)
SECRET_MARKERS = (
    ".env", ".git", "swagger", "openapi", "graphql", "id_rsa",
    "password", "secret_key", "bearer ", "token=", "jwt", "api_key",
    "authorization:", "x-api-key",
)
HIGH_STATUS = ("[200]", "[201]", "[204]", "200 ok", "201 created")
AUTH_STATUS = ("[401]", "[403]", "401 unauthorized", "403 forbidden")
ERROR_STATUS = ("[500]", "[502]", "[503]", "500 internal server error")


def clean_line(line: str) -> str:
    return ANSI_ESCAPE.sub("", line).strip()


def entropy(text: str) -> float:
    if len(text) < 16:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def score_signal(line: str) -> int:
    lower = line.lower()
    if any(lower.endswith(ext) or f"{ext}?" in lower for ext in STATIC_EXTENSIONS):
        return 0
    score = 10
    if any(m in lower for m in CRITICAL_MARKERS):
        score += 80
    if any(m in lower for m in SECRET_MARKERS):
        score += 60
    if any(s in lower for s in HIGH_STATUS):
        score += 25
        if "/api/" in lower or "/v1/" in lower or "/v2/" in lower or "/graphql" in lower:
            score += 25
    elif any(s in lower for s in AUTH_STATUS):
        score += 20
        if "/admin" in lower or "/api/" in lower or "/internal" in lower:
            score += 25
    elif any(s in lower for s in ERROR_STATUS):
        score += 15
    if "?" in line and "=" in line:
        score += 20
    if UUID_RE.search(line):
        score += 20
    if any(k in lower for k in ("key", "secret", "tok", "pass", "token")):
        if entropy(line) > 3.8:
            score += 30
    return score


def score_json(obj: object) -> tuple[int, str]:
    """Flatten a JSON finding (nuclei/subfinder/httpx -json style) to a
    signal score + a compact one-line digest."""
    text = json.dumps(obj, ensure_ascii=False)
    lower = text.lower()
    s = 10
    if "nuclei" in lower and any(m in lower for m in ("info", "low", "medium", "high", "critical")):
        if "critical" in lower:
            s += 100
        elif "high" in lower:
            s += 85
        elif "medium" in lower:
            s += 70
        elif "low" in lower:
            s += 50
        else:
            s += 35
    if isinstance(obj, dict):
        host = obj.get("host") or obj.get("input") or obj.get("url") or ""
        status = obj.get("status_code") or obj.get("status") or ""
        tech = obj.get("tech") or obj.get("technologies") or ""
        title = obj.get("title") or ""
        cve = obj.get("cve_id") or ""
        template = obj.get("template_id") or obj.get("template-id") or ""
        digest = " ".join(str(x) for x in (host, status, tech, title, cve, template) if x)
        if cve:
            s += 60
        if any(m in lower for m in SECRET_MARKERS):
            s += 40
    else:
        digest = str(obj)[:200]
    if entropy(text) > 3.9 and any(k in lower for k in ("key", "secret", "token")):
        s += 30
    return s, digest


def est_tokens(text: str) -> int:
    return max(1, len(text.split()) * 5 // 4 + 1)


def process_stream(input_lines, target: str, tool: str, max_tokens: int) -> None:
    recon = Path.home() / "recon" / target
    recon.mkdir(parents=True, exist_ok=True)
    raw_path = recon / f"{tool}_raw.txt"

    raw_lines: list[str] = []
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for line in input_lines:
        c = clean_line(line)
        if not c:
            continue
        raw_lines.append(c)
        if c in seen:
            continue
        seen.add(c)
        s, digest = None, None
        stripped = c.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                obj = json.loads(stripped)
                s, digest = score_json(obj)
            except Exception:
                s, digest = score_signal(c), c
        else:
            s, digest = score_signal(c), c
        if s > 0:
            scored.append((s, digest))

    scored.sort(key=lambda x: x[0], reverse=True)

    budget = max_tokens
    shown: list[str] = []
    for _, d in scored:
        t = est_tokens(d)
        if budget - t < 0 and shown:
            break
        shown.append(d)
        budget -= t
    if not shown and seen:
        shown = list(seen)[:20]

    with open(raw_path, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(raw_lines) + "\n")
    try:
        os.chmod(raw_path, 0o666)
    except Exception:
        pass

    print(f"[smart_pipe] {len(shown)} high-signal lines from {len(raw_lines)} "
          f"raw lines (token budget {max_tokens}).")
    print(f"[smart_pipe] full raw: ~/recon/{target}/{tool}_raw.txt")
    print()
    for d in shown:
        print(d)
    if len(scored) > len(shown):
        print(f"\n[smart_pipe] (+{len(scored) - len(shown)} more in raw log)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smart Output Filter & Token Saver")
    ap.add_argument("--target", "-t", required=True, help="target slug (recon/<target>/)")
    ap.add_argument("--tool", "-n", required=True, help="tool name for the raw log")
    ap.add_argument("--max-tokens", "-m", type=int, default=1200,
                    help="token budget for the agent-visible output (default 1200)")
    args = ap.parse_args()
    if sys.stdin.isatty():
        ap.print_help()
        sys.exit(2)
    process_stream(sys.stdin, args.target, args.tool, args.max_tokens)


if __name__ == "__main__":
    main()
