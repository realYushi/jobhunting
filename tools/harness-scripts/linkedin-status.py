# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *


def fetch_main_text() -> str:
    return js(
        """
(() => {
    const main = document.querySelector('main')?.innerText || '';
    const body = document.body?.innerText || '';
    return (main || body).slice(0, 20000);
})()
"""
    )


# Open our own tab first so we never navigate (and clobber) a LinkedIn tab the
# user has open. Chrome shares the logged-in session, so a fresh tab is already
# authenticated. Subsequent goto_url calls stay within this tab.
sections = {}
opened = False
for name, url in [
    ("notifications", "https://www.linkedin.com/notifications/"),
    ("messaging", "https://www.linkedin.com/messaging/"),
]:
    if not opened:
        new_tab(url)
        opened = True
    else:
        goto_url(url)
    wait_for_load()
    wait(3)
    sections[name] = fetch_main_text()

print(json.dumps(sections))
