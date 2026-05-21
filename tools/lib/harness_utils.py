"""Browser-harness utilities for job scraping."""

from __future__ import annotations

import json
import os
import string
import subprocess
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "harness-scripts"
_JS_HELPERS_PATH = _SCRIPTS_DIR / "_js_helpers.js"


def _harness_env() -> dict[str, str]:
    """Return environment for browser-harness subprocesses.

    Connects to the user's local Chrome via browser-harness defaults.
    """
    return os.environ.copy()


def load_script(name: str, **params: Any) -> str:
    """Load a harness script from tools/harness-scripts/ and substitute params.

    Uses string.Template ($var) so literal braces in embedded JS/JSON don't
    need escaping. Pass parameters by keyword:
        load_script("seek-list", url="https://nz.seek.com/jobs?...")
    Missing placeholders raise KeyError so a typo fails loudly instead of
    silently producing a broken script.

    A `$js_helpers` placeholder is always available; it expands to the
    contents of `_js_helpers.js` (shared JS utilities like `clean`).
    """
    path = _SCRIPTS_DIR / f"{name}.py"
    text = path.read_text()
    params.setdefault("js_helpers", _JS_HELPERS_PATH.read_text())
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
