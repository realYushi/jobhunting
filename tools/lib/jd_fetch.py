"""Full job-description fetching via browser-harness.

Serialized by default: although each fetch opens its own tab, browser-harness
subprocesses share one Chrome session and concurrent runs have produced
cross-contaminated JDs.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from lib.harness_utils import LiveHarnessRunner, parse_harness_json_output

if TYPE_CHECKING:
    from lib.scorer import JobScore


JD_FETCH_PARALLELISM = 1


def _fetch_full_jd(url: str, runner: LiveHarnessRunner | None = None) -> str:
    """Fetch the full job description from a listing URL.

    browser-harness subprocesses all talk to the same Chrome instance. In
    practice, concurrent JD fetches can read the wrong active tab and return a
    different listing's content, so callers should serialize access.
    """
    if runner is None:
        runner = LiveHarnessRunner()
    # hiring.cafe needs a tab click to reveal the full JD
    pre_extract = ""
    if "hiring.cafe/viewjob" in url or "hiring.cafe/job" in url:
        pre_extract = r'''
js(r"""
(() => {
  const tabs = Array.from(document.querySelectorAll('button, a'))
    .filter(el => (el.innerText||'').trim() === 'Job Description');
  if (tabs.length) tabs[0].click();
})()
""")
wait(2)
'''
    source = None
    if "prosple.com" in url:
        source = "prosple"
    result = runner.run("jd-fetch", url=url, pre_extract=pre_extract, timeout=60, source=source)
    if result.retcode != 0:
        return f"# Failed to fetch JD from {url}\n\nError: {result.stderr}"

    results = parse_harness_json_output(result.stdout)
    if results and "jd" in results[0]:
        return results[0]["jd"]

    return f"# Could not extract JD from {url}"


def _fetch_jds_parallel(
    items: list["JobScore"],
    max_workers: int = JD_FETCH_PARALLELISM,
    runner: LiveHarnessRunner | None = None,
) -> dict[str, str]:
    """Fetch JDs for many listings. Keyed by item.url.

    This is intentionally serialized by default. Although each fetch opens its
    own tab, browser-harness subprocesses still share one Chrome session and
    concurrent runs have produced cross-contaminated JDs. Failures fall back to
    a placeholder string, the same shape `_fetch_full_jd` returns on its own
    error path.
    """
    urls = [item.url for item in items if item.url]
    if not urls:
        return {}

    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_full_jd, url, runner): url for url in urls}
        for fut in futures:
            url = futures[fut]
            try:
                out[url] = fut.result()
            except Exception as e:
                out[url] = f"# Failed to fetch JD from {url}\n\nError: {e}"
    return out
