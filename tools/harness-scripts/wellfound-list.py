# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url, $page
goto_url("$url")
wait_for_load()
wait(3)

jobs = js(r"""
(() => {
  $js_helpers

  const out = [];
  const seen = new Set();

  function jobIdFromUrl(href) {
    const m = (href || '').match(/\/jobs\/(\d+)(?:-|[/?#]|$$)/);
    return m ? m[1] : '';
  }

  function looksPosted(text) {
    const t = clean(text).toLowerCase();
    return /^(today|yesterday|\d+\s+(day|days|week|weeks|month|months)\s+ago)$$/.test(t);
  }

  function looksMoney(text) {
    const t = clean(text).toLowerCase();
    return /[$$€£]\d|\d+\.\d+%|no equity|equity|\bk\b|\d+k/.test(t);
  }

  function rowForLink(link, card) {
    let el = link;
    while (el && el !== card) {
      const text = el.innerText || '';
      if (text.includes('Apply') && text.includes('Full-time')) return el;
      el = el.parentElement;
    }
    return link.parentElement;
  }

  const cards = Array.from(document.querySelectorAll('[data-testid="startup-header"]'))
    .map(header => header.closest('div.mb-6.w-full.rounded.border') || header.parentElement)
    .filter(Boolean);

  for (const card of cards) {
    const company = clean(card.querySelector('[data-testid="startup-header"] h2')?.innerText)
      || clean(card.querySelector('a[href*="/company/"]')?.innerText)
      || 'Unknown';
    const companyDescription = clean(
      Array.from(card.querySelectorAll('[data-testid="startup-header"] span'))
        .map(s => clean(s.innerText))
        .find(t => t && !/employees$$/i.test(t))
    );

    for (const link of Array.from(card.querySelectorAll('a[href*="/jobs/"]'))) {
      const href = link.href || '';
      const job_id = jobIdFromUrl(href);
      if (!job_id || seen.has(job_id)) continue;

      const row = rowForLink(link, card);
      const rowText = clean(row?.innerText);
      if (!rowText || !rowText.includes('Full-time')) continue;

      const title = clean(link.innerText) || 'Unknown';
      const spans = Array.from(row.querySelectorAll('span'))
        .map(s => clean(s.innerText))
        .filter(Boolean);
      const posted = spans.find(looksPosted) || null;
      const location = spans.find(s =>
        s !== 'Full-time'
        && !looksPosted(s)
        && !looksMoney(s)
        && !/^\+\d+$$/.test(s)
        && !/\d+\s+years? of exp/i.test(s)
      ) || '';

      seen.add(job_id);
      out.push({
        job_id,
        url: href,
        title,
        company,
        location,
        snippet: [companyDescription, rowText].filter(Boolean).join(' | '),
        posted
      });
    }
  }

  // Fallback for the Wellfound jobs landing page, which has a simpler list.
  if (out.length === 0) {
    for (const link of Array.from(document.querySelectorAll('a[href*="/jobs/"]'))) {
      const href = link.href || '';
      const job_id = jobIdFromUrl(href);
      if (!job_id || seen.has(job_id)) continue;
      const title = clean(link.innerText) || 'Unknown';
      const parent = link.closest('div, li, article, section') || link.parentElement;
      seen.add(job_id);
      out.push({
        job_id,
        url: href,
        title,
        company: 'Unknown',
        location: '',
        snippet: clean(parent?.innerText),
        posted: null
      });
    }
  }

  return out.slice(0, 12);
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
