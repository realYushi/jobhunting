#!/usr/bin/env python3
"""Smoke-test the hosted/self-hosted Browserless backend.

Reads `.env` if present, then routes a tiny browser-harness script through
`JOBHUNTING_BROWSER=browserless`. No local Chrome is needed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

# Allow `python3 tools/check_browserless.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from lib.harness_utils import _harness_env, run_harness  # noqa: E402


def _redact_url(url: str | None) -> str:
    if not url:
        return "<unset>"
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "***" if key.lower() in {"token", "api_key", "apikey"} else value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(redacted))
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Browserless CDP routing.")
    parser.add_argument(
        "--url",
        default="https://example.com",
        help="URL to open for the smoke test (default: https://example.com).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="browser-harness timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    os.environ.setdefault("JOBHUNTING_BROWSER", "browserless")

    env = _harness_env()
    print("Browserless routing:")
    print(f"  BU_NAME: {env.get('BU_NAME', '<unset>')}")
    print(f"  BU_CDP_WS: {_redact_url(env.get('BU_CDP_WS'))}")
    print(f"  BU_CDP_URL: {_redact_url(env.get('BU_CDP_URL'))}")

    script = f"""
from browser_harness import *
import json
goto_url({args.url!r})
wait_for_load()
print(json.dumps({{
  "url": js("location.href"),
  "title": js("document.title"),
  "text": js("document.body?.innerText?.slice(0, 120) || ''"),
}}))
"""
    stdout, stderr, retcode = run_harness(script, timeout=args.timeout)
    if retcode != 0:
        print("\n❌ Browserless smoke test failed", file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        return retcode

    for line in stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        print("\n✅ Browserless smoke test passed")
        print(f"  Title: {data.get('title')}")
        print(f"  URL: {data.get('url')}")
        return 0

    print("\n❌ Browserless returned no JSON result", file=sys.stderr)
    if stdout:
        print(stdout, file=sys.stderr)
    if stderr:
        print(stderr, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
