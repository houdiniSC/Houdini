#!/usr/bin/env python3
"""
browser-capture.py — capture authenticated browser traffic for the testing workflow.

Architecture: Playwright (Chromium) -> mitmproxy (intercept) -> flows.json
The captured flows feed the recon/testing workflow.

Usage:
  browser-capture.py --url https://target.com --scope example.com --out flows.json
  browser-capture.py --url https://target.com --scope example.com --script driver.py --role admin
  browser-capture.py --url https://target.com --scope example.com --mode curl   # no browser needed
  browser-capture.py --install                                                 # one-time deps

Driver script contract (--script):
  async def drive(page, role):
      await page.goto("https://target.com/login")
      await page.fill("#user", os.environ.get("USER_ADMIN"))
      ...
  The helper launches Chromium with the proxy already configured and
  ignore_https_errors=True. BROWSER_CAPTURE_ROLE is exported for the driver.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

PROXY_PORT = 18080


def _port_open(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _mitmdump_cmd(flow_file: Path, port: int) -> list[str]:
    venv_bin = Path(sys.executable).parent / "mitmdump"
    for candidate in (venv_bin, shutil.which("mitmdump")):
        if candidate and os.access(candidate, os.X_OK):
            return [
                str(candidate),
                "-q",
                "-w",
                str(flow_file),
                "--listen-port",
                str(port),
                "--set",
                "flow_detail=0",
            ]
    return [
        sys.executable,
        "-c",
        "from mitmproxy.tools.main import mitmdump; mitmdump()",
        "-q",
        "-w",
        str(flow_file),
        "--listen-port",
        str(port),
        "--set",
        "flow_detail=0",
    ]


def start_proxy(flow_file: Path, port: int = PROXY_PORT) -> subprocess.Popen:
    proc = subprocess.Popen(
        _mitmdump_cmd(flow_file, port),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(20):
        if proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"mitmdump failed to start: {err[:500]}")
        if _port_open("127.0.0.1", port):
            return proc
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("mitmdump did not start listening")


def parse_flows(flow_path: Path, scope: str | None) -> dict:
    from mitmproxy import http, io  # type: ignore

    flows: list[dict] = []
    with flow_path.open("rb") as fp:
        for f in io.FlowReader(fp).stream():
            if not isinstance(f, http.HTTPFlow):
                continue
            req = f.request
            host = req.pretty_host
            if scope and not (host == scope or host.endswith("." + scope)):
                continue
            entry = {
                "method": req.method,
                "url": req.pretty_url,
                "host": host,
                "status": f.response.status_code if f.response else None,
                "cookies": dict(req.cookies),
                "response_cookies": dict(f.response.cookies) if f.response else {},
                "content_type": req.headers.get("content-type", ""),
                "response_content_type": (
                    f.response.headers.get("content-type", "") if f.response else ""
                ),
                "sensitive_headers": {
                    k: v
                    for k, v in req.headers.items()
                    if k.lower()
                    in ("authorization", "cookie", "x-api-key", "x-csrf-token")
                },
                "request_body": None,
            }
            if req.content and len(req.content) <= 65536:
                try:
                    entry["request_body"] = req.get_text()
                except Exception:
                    entry["request_body"] = None
            flows.append(entry)

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for e in flows:
        key = (e["method"], e["url"].split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return {
        "flows": unique,
        "count": len(unique),
        "captured_total": len(flows),
        "role": os.environ.get("BROWSER_CAPTURE_ROLE", "default"),
    }


async def drive_browser(
    url: str,
    scope: str,
    script: str | None,
    proxy_url: str,
    headless: bool,
) -> None:
    from playwright.async_api import async_playwright  # type: ignore

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            proxy={"server": proxy_url},
            ignore_https_errors=True,
        )
        page = await ctx.new_page()
        role = os.environ.get("BROWSER_CAPTURE_ROLE", "default")
        if script:
            spec = importlib.util.spec_from_file_location("browser_capture_driver", script)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            await mod.drive(page, role)
        else:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            links: set[str] = set()
            for a in await page.query_selector_all("a[href]"):
                href = await a.get_attribute("href")
                if href and href.startswith(("http", "/")):
                    links.add(href)
            for href in list(links)[:10]:
                try:
                    await page.goto(
                        urljoin(url, href),
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                except Exception:
                    pass
        await ctx.close()
        await browser.close()


def curl_capture(url: str, proxy_url: str) -> None:
    import ssl
    import urllib.request

    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    https_handler = urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
    opener = urllib.request.build_opener(proxy_handler, https_handler)
    req = urllib.request.Request(url, headers={"User-Agent": "browser-capture/1.0"})
    with opener.open(req, timeout=30) as resp:
        resp.read(65536)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture browser traffic for the testing workflow")
    parser.add_argument("--url", default=None, help="target base URL")
    parser.add_argument("--scope", default=None, help="filter hosts (default: host of --url)")
    parser.add_argument("--out", default="browser-capture.json", help="output JSON path")
    parser.add_argument("--script", default=None, help="Playwright driver .py (async def drive(page, role))")
    parser.add_argument("--role", default=None, help="role label exported as BROWSER_CAPTURE_ROLE")
    parser.add_argument("--mode", choices=["browser", "curl"], default="browser")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--proxy-port", type=int, default=PROXY_PORT)
    parser.add_argument("--install", action="store_true", help="install playwright + mitmproxy + chromium")
    args = parser.parse_args()

    if args.install:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "playwright", "mitmproxy"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
        print("installed: playwright + mitmproxy + chromium")
        return

    if not args.url:
        parser.error("--url is required (or use --install)")
    scope = args.scope or Path(args.url).name.split("/")[0]
    if args.role:
        os.environ["BROWSER_CAPTURE_ROLE"] = args.role

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser-capture-") as tmp:
        flow_file = Path(tmp) / "capture.flow"
        proxy_url = f"http://127.0.0.1:{args.proxy_port}"
        proc = start_proxy(flow_file, args.proxy_port)
        try:
            if args.mode == "curl":
                curl_capture(args.url, proxy_url)
            else:
                asyncio.run(
                    drive_browser(
                        args.url,
                        scope,
                        args.script,
                        proxy_url,
                        args.headless,
                    )
                )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        result = parse_flows(flow_file, scope)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"captured {result['count']} unique flows -> {out} (role={result['role']})")


if __name__ == "__main__":
    main()
