# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url, $page  (one-shot callers pass page=0)
# Uses new_tab (not goto_url) so scraping the user's live Chrome opens its own
# tab instead of hijacking whatever tab is currently in focus.
_tab_id = new_tab("$url")
wait_for_load()
wait(2)

jobs = js(r"""
(() => {
    $js_helpers

    function asArray(value) {
        if (Array.isArray(value)) return value;
        if (!value) return [];
        return [value];
    }

    function labelOf(item) {
        if (!item || typeof item !== 'object') return item;
        return item.label || item.description || item.name || item.displayName || item.id || '';
    }

    const seen = new Set();
    const jobs = [];
    const cards = document.querySelectorAll(
        "article[data-automation='normalJob'], " +
        "article[data-automation='premiumJob'], " +
        "article[data-job-id]"
    );

    for (const card of cards) {
        const titleEl = card.querySelector("[data-automation='jobTitle']");
        const companyEl = card.querySelector("[data-automation='jobCompany']");
        const titleLink = titleEl?.closest("a[href*='/job/']");
        const linkEl = titleLink || card.querySelector("a[href*='/job/']");
        const link = linkEl?.href || "";

        if (!titleEl || !link.includes("/job/")) continue;

        const jobId = card.getAttribute("data-job-id") ||
            link.split("/job/")[1].split(/[?#]/)[0];
        if (!jobId || seen.has(jobId)) continue;
        seen.add(jobId);

        jobs.push({
            job_id: jobId,
            url: link,
            title: titleEl.textContent.trim(),
            company: companyEl?.textContent.trim() || "Unknown",
            snippet: card.innerText.trim()
        });
    }

    // Lightpanda can fetch SEEK's server-rendered payload but currently may
    // fail before React materializes the card DOM. Fall back to the embedded
    // Redux search results so the lightweight VPS path still discovers jobs.
    if (jobs.length === 0) {
        const data = window.SEEK_REDUX_DATA || seekReduxDataFromHtml();
        const rows = data?.results?.results?.jobs || [];
        for (const row of rows) {
            const jobId = String(row.id || row.solMetadata?.jobId || '');
            if (!jobId || seen.has(jobId)) continue;
            seen.add(jobId);

            const locationText = (row.locations || [])
                .map(loc => clean(loc.label))
                .filter(Boolean)
                .join(' | ');
            const workTypes = asArray(row.workTypes)
                .map(item => clean(labelOf(item)))
                .filter(Boolean)
                .join(' | ');
            const arrangements = asArray(row.workArrangements)
                .map(item => clean(labelOf(item)))
                .filter(Boolean)
                .join(' | ');
            const snippet = [
                clean(row.teaser),
                ...(row.bulletPoints || []).map(clean),
                clean(row.salaryLabel),
                workTypes,
                arrangements,
                clean(row.listingDateDisplay)
            ].filter(Boolean).join(' | ');

            jobs.push({
                job_id: jobId,
                url: window.location.origin + '/job/' + jobId,
                title: clean(row.title) || 'Unknown',
                company: clean(row.companyName || row.advertiser?.description) || 'Unknown',
                snippet,
                location: locationText
            });
        }
    }

    return jobs;
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))

# Close the tab we opened so the user's own tabs are left untouched.
try:
    cdp("Target.closeTarget", targetId=_tab_id)
except Exception:
    pass
