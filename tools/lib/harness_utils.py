"""Browser-harness utilities for job scraping."""

from __future__ import annotations

import json
import os
import shutil
import socket
import string
import subprocess
import tempfile
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "harness-scripts"
_JS_HELPERS_PATH = _SCRIPTS_DIR / "_js_helpers.js"
_DEFAULT_CDP_URL = os.environ.get("JOBHUNTING_BROWSER_CDP_URL", "http://127.0.0.1:9333")
_DEFAULT_DAEMON_NAME = os.environ.get("JOBHUNTING_BROWSER_NAME", "jobhunting")
_DEFAULT_PROFILE_DIR = Path(
    os.environ.get(
        "JOBHUNTING_BROWSER_PROFILE_DIR",
        str(Path.home() / ".cache" / "jobhunting" / "browser-profile"),
    )
)
_TRANSIENT_HEADED_SOURCES = frozenset({"prosple"})


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def _chrome_candidates() -> tuple[str, ...]:
    explicit = os.environ.get("CHROME_BIN")
    if explicit:
        return (explicit,)
    return (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
        "chromium-browser",
    )


def _find_chrome_binary() -> str | None:
    for candidate in _chrome_candidates():
        path = Path(candidate)
        if path.is_file():
            return str(path)
        if "/" not in candidate:
            resolved = subprocess.run(
                ["bash", "-lc", f"command -v {candidate}"],
                capture_output=True,
                text=True,
            )
            binary = resolved.stdout.strip()
            if resolved.returncode == 0 and binary:
                return binary
    return None


def _cdp_ready(cdp_url: str, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(
            f"{cdp_url.rstrip('/')}/json/version", timeout=timeout
        ):
            return True
    except Exception:
        return False


def _launch_chrome_args(
    chrome_path: str, cdp_url: str, profile_dir: Path, headless: bool
) -> list[str]:
    parsed = urlparse(cdp_url)
    port = parsed.port or 9222
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1400,1000",
        "about:blank",
    ]
    if headless:
        args[1:1] = ["--headless=new", "--disable-gpu"]
    return args


def _chrome_app_bundle(chrome_path: str) -> Path | None:
    path = Path(chrome_path)
    if path.parts[-4:-1] == ("Google Chrome.app", "Contents", "MacOS"):
        return path.parents[2]
    if ".app" in path.parts:
        for idx, part in enumerate(path.parts):
            if part.endswith(".app"):
                return Path(*path.parts[: idx + 1])
    return None


def _launch_chrome_process(
    chrome_path: str,
    cdp_url: str,
    profile_dir: Path,
    headless: bool,
    *,
    background: bool,
) -> subprocess.Popen:
    args = _launch_chrome_args(chrome_path, cdp_url, profile_dir, headless)
    if background and os.uname().sysname == "Darwin":
        bundle = _chrome_app_bundle(chrome_path)
        if bundle and bundle.exists():
            return subprocess.Popen(
                ["open", "-g", "-n", "-a", str(bundle), "--args", *args[1:]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _pick_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run_browser_harness(
    script: str, timeout: int, env: dict[str, str]
) -> tuple[str, str, int]:
    result = subprocess.run(
        ["browser-harness"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def _stop_browser_harness_daemon(env: dict[str, str]) -> None:
    try:
        subprocess.run(
            ["browser-harness", "--reload"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except Exception:
        pass


def _kill_browser_on_port(port: int) -> None:
    subprocess.run(
        ["bash", "-lc", f"pkill -f 'remote-debugging-port={port}' || true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_harness_with_transient_browser(
    script: str, timeout: int, source: str
) -> tuple[str, str, int]:
    chrome_path = _find_chrome_binary()
    if not chrome_path:
        return "", "Chrome binary not found for transient browser", 2

    port = _pick_free_port()
    cdp_url = f"http://127.0.0.1:{port}"
    profile_dir = Path(tempfile.mkdtemp(prefix=f"jobhunting-{source}-"))
    env = os.environ.copy()
    env["BU_CDP_URL"] = cdp_url
    env["BU_NAME"] = f"{_DEFAULT_DAEMON_NAME}-{source}-{uuid.uuid4().hex[:8]}"

    proc = _launch_chrome_process(
        chrome_path,
        cdp_url,
        profile_dir,
        False,
        background=True,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if _cdp_ready(cdp_url):
                return _run_browser_harness(script, timeout, env)
            time.sleep(0.25)
        return "", f"Timed out waiting for transient {source} browser", 1
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1
    except FileNotFoundError:
        return "", "browser-harness not found on PATH", 2
    finally:
        _stop_browser_harness_daemon(env)
        _kill_browser_on_port(port)
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(profile_dir, ignore_errors=True)


def _ensure_dedicated_browser() -> str | None:
    if os.environ.get("BU_CDP_URL") or os.environ.get("BU_CDP_WS"):
        return None
    if not _env_flag("JOBHUNTING_BROWSER_USE_DEDICATED", True):
        return None

    cdp_url = _DEFAULT_CDP_URL
    if _cdp_ready(cdp_url):
        return cdp_url

    chrome_path = _find_chrome_binary()
    if not chrome_path:
        return None

    profile_dir = _DEFAULT_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)
    headless = _env_flag("JOBHUNTING_BROWSER_HEADLESS", True)
    _launch_chrome_process(
        chrome_path,
        cdp_url,
        profile_dir,
        headless,
        background=False,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        if _cdp_ready(cdp_url):
            return cdp_url
        time.sleep(0.25)
    return None


def _harness_env(source: str | None = None) -> dict[str, str]:
    """Return environment for browser-harness subprocesses.

    By default this project uses a dedicated automation Chrome wired through
    ``BU_CDP_URL`` so scraping runs in the background and does not steal focus
    from the user's normal browser. Set ``JOBHUNTING_BROWSER_USE_DEDICATED=0``
    to fall back to browser-harness' default browser discovery, or set
    ``BU_CDP_URL`` / ``BU_CDP_WS`` explicitly to override this helper.
    """
    env = os.environ.copy()
    if source in _TRANSIENT_HEADED_SOURCES:
        return env
    cdp_url = _ensure_dedicated_browser()
    if cdp_url:
        env.setdefault("BU_NAME", _DEFAULT_DAEMON_NAME)
        env["BU_CDP_URL"] = cdp_url
    return env


def load_script(name: str, **params: Any) -> str:
    """Load a harness script from tools/harness-scripts/ and substitute params.

    Uses string.Template ($var) so literal braces in embedded JS/JSON don't
    need escaping. Pass parameters by keyword:
        load_script("seek-list", url="https://nz.seek.com/jobs?...")
    Missing placeholders raise KeyError so a typo fails loudly instead of
    silently producing a broken script.

    A `$js_helpers` placeholder is always available; it expands to the
    contents of `_js_helpers.js` (shared JS utilities like `clean`).

    List scrapers (script name ends with '-list' or '-list-paginated') that
    receive a ``url`` parameter are automatically wrapped with tab lifecycle
    (open a dedicated tab via ``new_tab(url)``, wait for load, close it after).
    This keeps every listing scraper isolated from the user's active browser
    session.
    """
    path = _SCRIPTS_DIR / f"{name}.py"
    text = path.read_text()
    params.setdefault("js_helpers", _JS_HELPERS_PATH.read_text())
    substituted = string.Template(text).substitute(**params)

    # List scrapers get automatic tab lifecycle.
    if (name.endswith("-list") or name.endswith("-list-paginated")) and "url" in params:
        url_repr = repr(params["url"])
        prefix = f"_bh_tab = new_tab({url_repr})\nwait_for_load()\n"
        suffix = "\ntry:\n    cdp(\"Target.closeTarget\", targetId=_bh_tab)\nexcept Exception:\n    pass"
        return prefix + substituted + suffix
    return substituted


def run_harness(
    script: str, timeout: int = 120, source: str | None = None
) -> tuple[str, str, int]:
    """Run a browser-harness script and return stdout, stderr, returncode.

    Returns:
        (stdout, stderr, returncode)
    """
    try:
        if source in _TRANSIENT_HEADED_SOURCES:
            return _run_harness_with_transient_browser(script, timeout, source)
        return _run_browser_harness(script, timeout, _harness_env(source=source))
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


@dataclass(frozen=True)
class HarnessResult:
    """Result of a single harness script run."""

    stdout: str
    stderr: str
    retcode: int


class LiveHarnessRunner:
    """Adapter that runs scripts against the real browser via run_harness + load_script."""

    def run(
        self,
        script_name: str,
        *,
        timeout: int,
        source: str | None = None,
        **params: Any,
    ) -> HarnessResult:
        script = load_script(script_name, **params)
        stdout, stderr, retcode = run_harness(script, timeout=timeout, source=source)
        return HarnessResult(stdout=stdout, stderr=stderr, retcode=retcode)
