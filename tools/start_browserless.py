#!/usr/bin/env python3
"""Start a local Browserless Chromium container for job scraping.

This is the VPS-friendly browser backend: one full Chromium instance exposed via
CDP, isolated from the user's local Chrome profile. The pipeline can then route
all browser-harness scraping through Browserless with JOBHUNTING_BROWSER.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000
DEFAULT_IMAGE = "ghcr.io/browserless/chromium:latest"
DEFAULT_CONTAINER = "jobhunting-browserless"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a Browserless Chromium Docker container for scraping."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--name", default=DEFAULT_CONTAINER)
    parser.add_argument(
        "--token",
        default=os.environ.get("JOBHUNTING_BROWSERLESS_TOKEN") or secrets.token_urlsafe(24),
        help="Browserless token. Defaults to JOBHUNTING_BROWSERLESS_TOKEN or a generated token.",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=1,
        help="Browserless concurrency cap. Keep this low on cheap VPS instances.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120_000,
        help="Browserless session timeout in milliseconds.",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull the Browserless image before starting.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Remove an existing container with the same name before starting.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for /json/version to become reachable.",
    )
    return parser.parse_args()


def _require_docker() -> None:
    try:
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("Docker is not installed or not on PATH.", file=sys.stderr)
        raise SystemExit(2)
    except subprocess.CalledProcessError as exc:
        print(
            "Docker is installed but the daemon is not reachable:\n"
            f"  {exc.stderr.strip() or exc.stdout.strip()}",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _container_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return any(line.strip() == name for line in result.stdout.splitlines())


def _container_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return any(line.strip() == name for line in result.stdout.splitlines())


def _json_version_url(host: str, port: int, token: str) -> str:
    query = urllib.parse.urlencode({"token": token}) if token else ""
    return urllib.parse.urlunsplit(("http", f"{host}:{port}", "/json/version", query, ""))


def _wait_for_cdp(host: str, port: int, token: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    url = _json_version_url(host, port, token)
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                data = json.loads(response.read())
            if data.get("webSocketDebuggerUrl") or data.get("Browser"):
                return
        except Exception as exc:  # noqa: BLE001 - report final startup error
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Browserless CDP endpoint did not start at {url}: {last_error}")


def main() -> int:
    args = _parse_args()
    _require_docker()

    if args.pull:
        subprocess.run(["docker", "pull", args.image], check=True)

    if _container_exists(args.name):
        if args.replace:
            subprocess.run(["docker", "rm", "-f", args.name], check=True)
        elif not _container_running(args.name):
            subprocess.run(["docker", "start", args.name], check=True)
        else:
            print(f"Container {args.name!r} is already running.")
    else:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                args.name,
                "-p",
                f"{args.host}:{args.port}:3000",
                "-e",
                f"TOKEN={args.token}",
                "-e",
                f"CONCURRENT={args.concurrent}",
                "-e",
                f"TIMEOUT={args.timeout_ms}",
                "--shm-size=1gb",
                args.image,
            ],
            check=True,
        )

    if not args.no_wait:
        _wait_for_cdp(args.host, args.port, args.token)

    http_url = f"http://{args.host}:{args.port}"
    ws_url = f"ws://{args.host}:{args.port}?{urllib.parse.urlencode({'token': args.token})}"
    print("Browserless started for job-hunting automation.")
    print(f"Container: {args.name}")
    print(f"HTTP URL: {http_url}")
    print(f"CDP WS: {ws_url}")
    print()
    print("Use it for one command:")
    print(
        "  JOBHUNTING_BROWSER=browserless "
        f"JOBHUNTING_BROWSERLESS_CDP_WS='{ws_url}' "
        "python3 tools/pipeline.py --scrape-only /tmp/jobhunting-listings.json"
    )
    print()
    print("Or export:")
    print("  export JOBHUNTING_BROWSER=browserless")
    print(f"  export JOBHUNTING_BROWSERLESS_CDP_WS='{ws_url}'")
    print(f"  export JOBHUNTING_BROWSERLESS_TOKEN='{args.token}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
