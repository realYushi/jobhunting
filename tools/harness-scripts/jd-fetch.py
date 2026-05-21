# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: url, pre_extract
# pre_extract is a Python snippet (possibly empty) that runs after navigation
# but before extraction. Used by hiring.cafe to click into the JD tab.
#
# Uses new_tab (not goto_url) so concurrent jd-fetch subprocesses each get
# their own isolated tab — required for parallel JD fetching from pipeline.py.
_tab_id = new_tab("$url")
wait_for_load()
wait(2)
exec(r'''$pre_extract''')
jd_text = js(r"""
(() => {
    $js_helpers

    function htmlToText(html) {
        const el = document.createElement('div');
        el.innerHTML = html || '';
        return (el.innerText || el.textContent || '').trim();
    }

    // Try LinkedIn
    const llDesc = document.querySelector(".show-more-less-html__markup");
    if (llDesc) return llDesc.innerText;

    // Try Seek
    const seekDesc = document.querySelector("[data-automation='jobDetails']");
    if (seekDesc) return seekDesc.innerText;

    // Lightpanda can fetch SEEK job pages but may not materialize the React DOM.
    // The server-rendered Redux payload still contains the full HTML JD.
    const seekData = window.SEEK_REDUX_DATA || seekReduxDataFromHtml();
    const seekJob = seekData?.jobdetails?.result?.job;
    const seekText = htmlToText(seekJob?.content2 || seekJob?.content || '');
    if (seekText) return seekText;

    // Try We Work Remotely
    const wwrDesc = document.querySelector(".lis-container__job, .lis-container");
    if (wwrDesc) return wwrDesc.innerText;

    // Fallback: get the main content area
    const main = document.querySelector("main");
    if (main) return main.innerText;

    // Hiring.cafe job detail pages currently do not expose a <main>, but the
    // detail page body is bounded enough to use after direct job navigation.
    if (location.hostname.includes("hiring.cafe") && location.pathname.includes("/job/")) {
        return document.body?.innerText || "";
    }

    return "";
})()
""")

print(json.dumps({"jd": jd_text}))

# Close the tab we opened so concurrent fetches don't accumulate stale tabs.
try:
    cdp("Target.closeTarget", targetId=_tab_id)
except Exception:
    pass
