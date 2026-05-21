# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url, $page
goto_url("$url")
wait_for_load()
wait(2)

jobs = js(r"""
(() => {
  const cards = Array.from(document.querySelectorAll(
    'div.relative.bg-white.rounded-xl.border'
  ));
  const out = [];
  for (const card of cards) {
    const jobLink = card.querySelector('a[href*="/job/"], a[href*="/viewjob/"]');
    if (!jobLink) continue;
    const m = jobLink.href.match(/\/(?:job|viewjob)\/([^/?#]+)/);
    if (!m) continue;
    const jobId = m[1];

    const titleEl = card.querySelector('span.font-bold.text-start');
    const locEl = card.querySelector('span.line-clamp-2:not(.font-light):not(.font-bold)');
    const snippetEl = card.querySelector('span.line-clamp-2.font-light');

    let company = '';
    const fontBolds = card.querySelectorAll('span.font-bold');
    for (const sp of fontBolds) {
      if (!sp.classList.contains('text-start')) {
        company = sp.innerText.trim();
        break;
      }
    }

    out.push({
      job_id: jobId,
      url: jobLink.href,
      title: titleEl ? titleEl.innerText.trim() : '',
      company: company,
      location: locEl ? locEl.innerText.trim() : '',
      snippet: snippetEl ? snippetEl.innerText.trim() : ''
    });
  }
  return out;
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
