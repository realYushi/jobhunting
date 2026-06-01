# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $url (hiring.cafe homepage carrying ?searchState=...), $page (1-indexed)
#
# hiring.cafe is a Next.js SSR app. Instead of scraping the rendered cards (which
# only exposes the first viewport and no posted date), we read the JSON the app
# itself fetches: /_next/data/<buildId>/index.json?searchState=...&page=N.
# That JSON carries the full hit list with dates, honours dateFetchedPastNDays,
# and paginates via the page query param (0-indexed; ssrIsLastPage marks the end).
goto_url("$url")
wait_for_load()
wait(1)

# $page is 1-indexed (the shared paginator's convention); the API is 0-indexed.
jobs = js(r"""
(async () => {
  const apiPage = Math.max(0, parseInt("$page", 10) - 1);
  const bid = window.__NEXT_DATA__ && window.__NEXT_DATA__.buildId;
  const ss = new URLSearchParams(location.search).get('searchState') || '';
  if (!bid || !ss) return [];
  const r = await fetch(
    '/_next/data/' + bid + '/index.json?searchState=' +
    encodeURIComponent(ss) + '&page=' + apiPage
  );
  if (!r.ok) return [];
  const pp = (await r.json()).pageProps || {};
  const hits = pp.ssrHits || [];
  const out = [];
  for (const h of hits) {
    if (h.is_expired === true || h.is_expired === 'true') continue;
    const reqId = h.requisition_id;
    if (!reqId) continue;
    const v5 = h.v5_processed_job_data || {};
    let posted = v5.estimated_publish_date || null;
    if (posted && posted.includes('T')) posted = posted.split('T')[0];  // ISO date only
    let snippet = v5.requirements_summary || '';
    if (snippet.length > 300) snippet = snippet.slice(0, 300);
    out.push({
      job_id: reqId,
      url: 'https://hiring.cafe/job/' + reqId,
      title: (h.job_information && h.job_information.title) || '',
      company: (h.enriched_company_data && h.enriched_company_data.name) || h.board_token || '',
      location: v5.formatted_workplace_location || '',
      snippet: snippet,
      posted: posted
    });
  }
  return out;
})()
""")
print(json.dumps({"page": int("$page"), "jobs": jobs}))
