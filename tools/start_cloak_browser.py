#!/usr/bin/env python3
"""Start a dedicated CloakBrowser instance for job scraping.

This keeps browser-harness/pipeline automation out of the user's main Chrome
profile. It starts CloakBrowser with a stable user-data-dir and Chrome DevTools
Protocol endpoint, then prints the BU_CDP_URL value to use with the pipeline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


DEFAULT_PORT = 9333
DEFAULT_PROFILE = Path.home() / ".jobhunting-cloak-profile"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start CloakBrowser with a dedicated job-hunting profile."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE,
        help=f"Dedicated browser profile directory (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without opening a visible browser window.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for the DevTools endpoint to become reachable.",
    )
    return parser.parse_args()


def _ensure_cloak_binary_and_args() -> tuple[str, list[str]]:
    try:
        from cloakbrowser.config import get_default_stealth_args
        from cloakbrowser.download import ensure_binary
    except ModuleNotFoundError:
        print(
            "CloakBrowser is not installed. Install it with:\n"
            "  python3 -m pip install cloakbrowser",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return ensure_binary(), get_default_stealth_args()


def _wait_for_cdp(port: int, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                data = json.loads(response.read())
            if data.get("webSocketDebuggerUrl"):
                return
        except Exception as exc:  # noqa: BLE001 - report final startup error
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"CloakBrowser CDP endpoint did not start at {url}: {last_error}")


def main() -> int:
    args = _parse_args()
    chrome, stealth_args = _ensure_cloak_binary_and_args()
    args.profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome,
        *stealth_args,
        f"--remote-debugging-port={args.port}",
        f"--user-data-dir={args.profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if args.headless:
        cmd.append("--headless=new")

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not args.no_wait:
        _wait_for_cdp(args.port)

    cdp_url = f"http://127.0.0.1:{args.port}"
    print("CloakBrowser started for job-hunting automation.")
    print(f"Profile: {args.profile_dir}")
    print(f"CDP URL: {cdp_url}")
    print()
    print("Use it for one command:")
    print(f"  JOBHUNTING_BROWSER=cloak python3 tools/pipeline.py --scrape-only /tmp/jobhunting-listings.json")
    print()
    print("Or export:")
    print(f"  export JOBHUNTING_BROWSER=cloak")
    print(f"  export JOBHUNTING_CLOAK_CDP_URL={cdp_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
