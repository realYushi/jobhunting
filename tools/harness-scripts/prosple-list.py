# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url, $page
# Prosple search results are rendered client-side enough that browser-harness is
# the most reliable path; plain HTTP requests return 403.
wait(4)

jobs = js(r"""
(() => {
  const out = [];
  const seen = new Set();

  function clean(text) {
    return (text || '').replace(/\s+/g, ' ').trim();
  }

  function slugFromHref(href) {
    const m = (href || '').match(/\/jobs-internships\/([^/?#]+)/);
    return m ? m[1] : '';
  }

  function postedFromText(text) {
    const m = text.match(/(Closing in \d+ days|Opening in \d+ months|Rolling Intake|Starts? ASAP|Start ASAP)/i);
    return m ? clean(m[1]) : null;
  }

  const links = Array.from(document.querySelectorAll('a[href*="/jobs-internships/"]'));
  for (const link of links) {
    const href = link.href || '';
    const jobId = slugFromHref(href);
    if (!jobId || seen.has(jobId)) continue;

    const section = link.closest('section[role="button"]');
    if (!section) continue;

    const title = clean(link.innerText);
    if (!title) continue;

    const text = section.innerText || '';
    const lines = text.split(/\n+/).map(clean).filter(Boolean);
    const company = lines[0] || 'Unknown';
    const location = lines.find(line => /auckland|wellington|christchurch|queenstown|tauranga|remote|anywhere/i.test(line)) || '';

    seen.add(jobId);
    out.push({
      job_id: jobId,
      url: href,
      title,
      company,
      location,
      snippet: clean(text),
      posted: postedFromText(text),
    });
  }

  return out.slice(0, 50);
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
