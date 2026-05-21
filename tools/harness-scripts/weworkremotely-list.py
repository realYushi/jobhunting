# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url
goto_url("$url")
wait_for_load()
wait(3)

jobs = js(r"""
(() => {
  function clean(text) {
    return (text || '').replace(/\s+/g, ' ').trim();
  }

  function slugFromUrl(href) {
    const m = (href || '').match(/\/remote-jobs\/([^/?#]+)/);
    return m ? m[1] : '';
  }

  const out = [];
  const seen = new Set();

  for (const li of Array.from(document.querySelectorAll('li.new-listing-container'))) {
    const link = li.querySelector('a.listing-link--unlocked[href*="/remote-jobs/"]');
    if (!link) continue;
    const url = link.href || '';
    const job_id = slugFromUrl(url);
    if (!job_id || seen.has(job_id)) continue;

    const title = clean(li.querySelector('.new-listing__header__title__text')?.innerText);
    const company = clean(li.querySelector('.new-listing__company-name')?.innerText);
    const headquarters = clean(li.querySelector('.new-listing__company-headquarters')?.innerText);
    const postedRaw = clean(li.querySelector('.new-listing__header__icons__date')?.innerText);
    const posted = /^new$$/i.test(postedRaw) ? 'today' : postedRaw.toLowerCase();
    const categories = Array.from(li.querySelectorAll('.new-listing__categories__category'))
      .map(el => clean(el.innerText))
      .filter(Boolean);
    const location = categories.find(c => /anywhere in the world/i.test(c))
      || categories.filter(c => !/boosted|featured|top 100|full-time|contract|usd|\$$|salary/i.test(c)).join(' | ')
      || headquarters;

    seen.add(job_id);
    out.push({
      job_id,
      url,
      title: title || 'Unknown',
      company: company || 'Unknown',
      location,
      snippet: [headquarters, categories.join(' | '), clean(li.innerText)].filter(Boolean).join(' | '),
      posted
    });
  }

  return out.slice(0, 80);
})()
""")
print(json.dumps({"jobs": jobs}))
