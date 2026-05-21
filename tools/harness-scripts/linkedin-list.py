# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url, $page  (one-shot callers pass page=0)
goto_url("$url")
wait_for_load()
wait(2)

jobs = js(r"""
(() => {
    $js_helpers

    function cleanTitle(text) {
        return clean(text)
            .replace(/\s+with verification$$/i, '')
            .replace(/\s+New$$/i, '')
            .trim();
    }

    function jobIdFromHref(href) {
        const match = String(href || '').match(/\/jobs\/view\/(\d+)/);
        return match?.[1] || '';
    }

    const seen = new Set();
    const jobs = [];
    const cards = document.querySelectorAll(
        ".base-search-card, " +
        "li[data-occludable-job-id], " +
        ".jobs-search-results__list-item"
    );

    for (const card of cards) {
        const urnEl = card.hasAttribute("data-entity-urn")
            ? card : card.querySelector("[data-entity-urn]");
        const urn = urnEl?.getAttribute("data-entity-urn") || "";
        const linkEl = card.querySelector("a[href*='/jobs/view/']");
        const jobId = card.getAttribute("data-occludable-job-id")
            || card.querySelector("[data-job-id]")?.getAttribute("data-job-id")
            || urn.split(":").pop()
            || jobIdFromHref(linkEl?.href);
        if (!jobId || seen.has(jobId)) continue;
        seen.add(jobId);

        if (!linkEl) continue;

        const titleEl = card.querySelector(
            ".job-card-list__title--link, " +
            ".job-card-container__link, " +
            "h3, h4, [class*='title']"
        );
        const companyEl = card.querySelector(
            ".artdeco-entity-lockup__subtitle, " +
            ".base-search-card__subtitle, " +
            "[class*='subtitle']"
        );
        const locEl = card.querySelector(
            ".job-card-container__metadata-wrapper li, " +
            ".job-search-card__location, " +
            "[class*='location']"
        );

        jobs.push({
            job_id: jobId,
            url: linkEl.href,
            title: cleanTitle(linkEl.getAttribute("aria-label") || titleEl?.textContent),
            company: clean(companyEl?.textContent),
            location: clean(locEl?.textContent)
        });
    }

    return jobs;
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
