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
  const links = Array.from(document.querySelectorAll('a.job-desktop[href*="/jobs/"]'));
  const seen = new Set();
  const out = [];
  for (const a of links) {
    const href = a.href || '';
    const m = href.match(/\/jobs\/([^/?#]+)/);
    if (!m) continue;
    const slug = m[1];
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);

    const lines = (a.innerText || '')
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);
    if (lines.length < 3) continue;

    const title = lines[0] || '';
    const company = lines[1] || '';
    const knownLocations = new Set([
      'anywhere', 'apac', 'emea', 'north america', 'latin america', 'europe',
      'canada', 'united states', 'usa', 'uk', 'ireland', 'poland', 'germany',
      'bulgaria', 'spain', 'portugal', 'romania', 'hungary', 'estonia',
      'china', 'australia', 'new zealand'
    ]);
    const location = lines.find(line =>
      knownLocations.has(line.toLowerCase()) || line.includes(',')
    ) || '';
    const snippet = lines.slice(2).join(' | ');
    const posted = lines.find(line => line.toLowerCase().endsWith('ago')) || null;

    out.push({
      job_id: (() => {
        const last = slug.split('-').slice(-1)[0];
        return Number.isInteger(Number(last)) ? last : slug;
      })(),
      url: href,
      title,
      company,
      location,
      snippet,
      posted
    });
  }
  return out.slice(0, 50);
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
