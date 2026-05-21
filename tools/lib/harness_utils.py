"""Browser-harness utilities for job scraping."""

from __future__ import annotations

import json
import os
import string
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "harness-scripts"
_ENV_LOADED = False
DEFAULT_CLOAK_CDP_URL = "http://127.0.0.1:9333"
DEFAULT_LIGHTPANDA_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSERLESS_CDP_URL = "http://127.0.0.1:3000"


def _load_optional_env() -> None:
    """Load project .env if present, without making scraping depend on it."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from lib.config import ConfigError, load_env

        try:
            load_env()
        except ConfigError:
            pass
    except Exception:
        # Browser routing should still work when this module is used outside the
        # full project package layout.
        pass


def _append_query_param(url: str, key: str, value: str) -> str:
    """Return url with key=value added unless key already exists."""
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if any(existing_key == key for existing_key, _ in query):
        return url
    query.append((key, value))
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(query))
    )


def _http_to_ws_url(url: str) -> str:
    """Convert an http(s) Browserless endpoint to its ws(s) equivalent."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == "http":
        return urllib.parse.urlunsplit(parsed._replace(scheme="ws"))
    if parsed.scheme == "https":
        return urllib.parse.urlunsplit(parsed._replace(scheme="wss"))
    return url


def _harness_env() -> dict[str, str]:
    """Return environment for browser-harness subprocesses.

    Set JOBHUNTING_BROWSER=cloak to route browser-harness to a dedicated
    CloakBrowser instance instead of the user's main Chrome. Start it with:
        python3 tools/start_cloak_browser.py
    Override the endpoint with JOBHUNTING_CLOAK_CDP_URL when needed.

    Set JOBHUNTING_BROWSER=lightpanda to target a Lightpanda CDP server. This
    is intended for cheap VPS/public-page scraping experiments, not LinkedIn
    logged-in flows. Start it with:
        python3 tools/start_lightpanda.py
    Override the endpoint with JOBHUNTING_LIGHTPANDA_CDP_URL when needed.

    Set JOBHUNTING_BROWSER=browserless to target Browserless for all browser
    automation. Prefer JOBHUNTING_BROWSERLESS_CDP_WS for hosted Browserless
    endpoints, or JOBHUNTING_BROWSERLESS_CDP_URL for self-hosted endpoints that
    expose /json/version. JOBHUNTING_BROWSERLESS_TOKEN is appended when set.
    """
    _load_optional_env()
    env = os.environ.copy()
    browser = env.get("JOBHUNTING_BROWSER", "").strip().lower()
    if browser == "cloak":
        # Use a separate browser-harness daemon name so an existing default
        # daemon connected to the user's main Chrome is never reused.
        env.setdefault("BU_NAME", "jobhunting-cloak")
        env.setdefault(
            "BU_CDP_URL",
            env.get("JOBHUNTING_CLOAK_CDP_URL", DEFAULT_CLOAK_CDP_URL),
        )
    elif browser == "lightpanda":
        # Keep Lightpanda isolated from both the default Chrome daemon and the
        # CloakBrowser daemon, because CDP capabilities differ by browser.
        env.setdefault("BU_NAME", "jobhunting-lightpanda")
        env.setdefault(
            "BU_CDP_URL",
            env.get("JOBHUNTING_LIGHTPANDA_CDP_URL", DEFAULT_LIGHTPANDA_CDP_URL),
        )
    elif browser == "browserless":
        # Browserless is a full Chromium backend and is suitable as the default
        # VPS browser. Keep it isolated from other browser-harness daemons.
        env.setdefault("BU_NAME", "jobhunting-browserless")

        token = env.get("JOBHUNTING_BROWSERLESS_TOKEN", "").strip()
        cdp_ws = env.get("JOBHUNTING_BROWSERLESS_CDP_WS", "").strip()
        cdp_url = env.get("JOBHUNTING_BROWSERLESS_CDP_URL", "").strip()

        if cdp_ws:
            env.setdefault(
                "BU_CDP_WS",
                _append_query_param(cdp_ws, "token", token) if token else cdp_ws,
            )
        else:
            if not cdp_url:
                cdp_url = DEFAULT_BROWSERLESS_CDP_URL
            parsed = urllib.parse.urlsplit(cdp_url)
            if parsed.scheme in {"ws", "wss"} or token or parsed.query:
                # browser-harness appends /json/version to BU_CDP_URL, which is
                # not safe for tokenized Browserless URLs. Use the direct WS URL
                # form for tokenized/self-hosted Browserless endpoints instead.
                ws_url = _http_to_ws_url(cdp_url)
                env.setdefault(
                    "BU_CDP_WS",
                    _append_query_param(ws_url, "token", token) if token else ws_url,
                )
            else:
                env.setdefault("BU_CDP_URL", cdp_url)
    return env


def load_script(name: str, **params: Any) -> str:
    """Load a harness script from tools/harness-scripts/ and substitute params.

    Uses string.Template ($var) so literal braces in embedded JS/JSON don't
    need escaping. Pass parameters by keyword:
        load_script("seek-list", url="https://nz.seek.com/jobs?...")
    Missing placeholders raise KeyError so a typo fails loudly instead of
    silently producing a broken script.
    """
    path = _SCRIPTS_DIR / f"{name}.py"
    text = path.read_text()
    return string.Template(text).substitute(**params)


def run_harness(script: str, timeout: int = 120) -> tuple[str, str, int]:
    """Run a browser-harness script and return stdout, stderr, returncode.

    Returns:
        (stdout, stderr, returncode)
    """
    try:
        result = subprocess.run(
            ["browser-harness"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_harness_env(),
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1
    except FileNotFoundError:
        return "", "browser-harness not found on PATH", 2


def parse_harness_json_output(stdout: str) -> list[dict[str, Any]]:
    """Parse JSON lines from browser-harness stdout.

    Returns:
        List of parsed JSON objects.
    """
    results = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            results.append(data)
        except json.JSONDecodeError:
            continue
    return results


def extract_company_from_page_title(title: str) -> str | None:
    """Extract company name from LinkedIn job page title.

    Format: "{job_title} | {company} | LinkedIn"
    """
    if not title:
        return None

    parts = title.split(" | ")
    if len(parts) >= 2 and parts[-1] == "LinkedIn":
        # Second-to-last part should be the company
        company = parts[-2].strip()
        if company and company != "LinkedIn":
            return company
    return None
