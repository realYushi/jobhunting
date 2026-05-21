#!/usr/bin/env python3
"""Start a Lightpanda CDP server for lightweight job scraping.

Lightpanda is useful on small VPS instances for public pages that do not need a
full Chrome profile. It is not a drop-in replacement for authenticated LinkedIn
flows, but browser-harness can talk to it over CDP for simple extraction tasks.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


DEFAULT_PORT = 9222
DEFAULT_CACHE = Path.home() / ".jobhunting-lightpanda-cache"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start Lightpanda with a CDP endpoint for job scraping."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--binary",
        type=Path,
        help="Path to the Lightpanda binary (default: PATH or .pi/bin/lightpanda).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"HTTP cache directory (default: {DEFAULT_CACHE}).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not pass --http-cache-dir to Lightpanda.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run Lightpanda in the foreground instead of daemonizing it.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for the DevTools endpoint to become reachable.",
    )
    parser.add_argument(
        "--log-level",
        default="warn",
        choices=("debug", "info", "warn", "error", "fatal"),
    )
    return parser.parse_args()


def _find_lightpanda_binary(explicit: Path | None) -> str:
    if explicit:
        if explicit.exists():
            return str(explicit)
        raise SystemExit(f"Lightpanda binary not found: {explicit}")

    bundled = Path(__file__).resolve().parents[1] / ".pi" / "bin" / "lightpanda"
    if bundled.exists():
        return str(bundled)

    found = shutil.which("lightpanda")
    if found:
        return found

    print(
        "Lightpanda is not installed. Download a release from:\n"
        "  https://github.com/lightpanda-io/browser/releases\n"
        "Then either put it on PATH or pass --binary /path/to/lightpanda.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _wait_for_cdp(host: str, port: int, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    url = f"http://{host}:{port}/json/version"
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
    raise RuntimeError(f"Lightpanda CDP endpoint did not start at {url}: {last_error}")


def main() -> int:
    args = _parse_args()
    binary = _find_lightpanda_binary(args.binary)

    cmd = [
        binary,
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--log-level",
        args.log_level,
    ]
    if not args.no_cache:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--http-cache-dir", str(args.cache_dir)])

    if args.foreground:
        return subprocess.run(cmd).returncode

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not args.no_wait:
        _wait_for_cdp(args.host, args.port)

    cdp_url = f"http://{args.host}:{args.port}"
    print("Lightpanda started for lightweight job-hunting scraping.")
    if not args.no_cache:
        print(f"Cache: {args.cache_dir}")
    print(f"CDP URL: {cdp_url}")
    print()
    print("Use it for one command:")
    print(
        "  JOBHUNTING_BROWSER=lightpanda "
        "python3 tools/pipeline.py --source seek "
        "--scrape-only /tmp/jobhunting-listings.json"
    )
    print()
    print("Or export:")
    print("  export JOBHUNTING_BROWSER=lightpanda")
    print(f"  export JOBHUNTING_LIGHTPANDA_CDP_URL={cdp_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
