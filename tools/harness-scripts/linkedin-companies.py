# pyright: reportMissingImports=false, reportUndefinedVariable=false
# ruff: noqa: F403,F405
import json

from browser_harness import *

# Params: $job_urls_json -- a JSON-encoded list of LinkedIn job URLs.
job_urls = json.loads("""$job_urls_json""")

results = []
for url in job_urls:
    goto_url(url)
    wait_for_load()
    wait(1)
    company = js('document.title.split(" | ").slice(-2, -1)[0] || ""')
    if "/jobs/view/" in url:
        job_id = url.split("/jobs/view/")[1].split("/")[0]
    else:
        job_id = url.split("/")[-1]
    results.append({"job_id": job_id, "company": company})

print(json.dumps({"phase": "companies", "results": results}))
