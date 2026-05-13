---
name: linkedin
description: Pull profile data from LinkedIn and push updates back. Use when the user wants to sync their LinkedIn profile, update their CV from LinkedIn, scrape job postings, or push profile changes. Triggers: "sync LinkedIn", "pull from LinkedIn", "update LinkedIn profile", "scrape LinkedIn jobs", "LinkedIn job search".
allowed-tools: Bash(browser-harness:*)
---

# LinkedIn Integration via browser-harness

Sync LinkedIn.com (source of truth) with local files. Uses browser-harness connected to the user's real Chrome session.

## Prerequisites

- `browser-harness` installed and on `$PATH`
- Chrome running with `chrome://inspect/#remote-debugging` enabled
- User logged into LinkedIn in their Chrome

Verify with: `browser-harness --doctor` — chrome running + daemon alive must pass.

## Commands

All commands use the heredoc pattern:

```bash
browser-harness <<'PY'
# Python code here — helpers pre-imported
PY
```

## Pull: LinkedIn → Local Files

### Full Profile Pull

Scrapes all profile sections and writes to `LinkedIn-CV-Profile.md`.

```bash
browser-harness <<'PY'
import json, time

# Switch to a LinkedIn tab (find existing or navigate)
tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    new_tab("https://www.linkedin.com/feed/")
    wait(3)

# Navigate to own profile
goto_url("https://www.linkedin.com/in/yushi-cui/")
wait(3)

# Extract About
about = js("""
(() => {
    const sections = {};
    document.querySelectorAll('section').forEach(s => {
        const h = s.querySelector('h2');
        if (h && h.innerText.trim() === 'About') {
            sections['about'] = s.innerText.replace(/^About\\n*/, '').trim();
        }
    });
    return JSON.stringify(sections);
})()
""")
about_data = json.loads(about)
print("About:", about_data.get('about', '')[:200])

# Extract Experience (detail page)
goto_url("https://www.linkedin.com/in/yushi-cui/details/experience/")
wait(3)
experience = js("document.querySelector('main')?.innerText?.slice(0, 5000) || ''")
print("Experience extracted:", len(experience), "chars")

# Extract Education (detail page)
goto_url("https://www.linkedin.com/in/yushi-cui/details/education/")
wait(3)
education = js("document.querySelector('main')?.innerText?.slice(0, 2000) || ''")
print("Education extracted:", len(education), "chars")

# Extract Skills (detail page)
goto_url("https://www.linkedin.com/in/yushi-cui/details/skills/")
wait(3)
skills = js("document.querySelector('main')?.innerText?.slice(0, 3000) || ''")
print("Skills extracted:", len(skills), "chars")

# Extract Certifications (detail page)
goto_url("https://www.linkedin.com/in/yushi-cui/details/certifications/")
wait(3)
certs = js("document.querySelector('main')?.innerText?.slice(0, 3000) || ''")
print("Certifications extracted:", len(certs), "chars")

# Output as structured JSON for the agent to write to file
output = {
    "headline": "AI-Native Product Engineer & Full Stack Developer",
    "about": about_data.get('about', ''),
    "experience": experience,
    "education": education,
    "skills": skills,
    "certifications": certs
}
print("\\n=== LINKEDIN_DATA_START ===")
print(json.dumps(output))
print("=== LINKEDIN_DATA_END ===")
PY
```

After extracting, the agent should:
1. Parse the structured data from the JSON output
2. Update `LinkedIn-CV-Profile.md` with the fresh data
3. Update `templates/base-resume.json` if needed
4. Report what changed

### Headline Pull (quick)

```bash
browser-harness <<'PY'
import json
tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    new_tab("https://www.linkedin.com/feed/")
    wait(3)

goto_url("https://www.linkedin.com/in/yushi-cui/")
wait(3)
headline = js("""
(() => {
    const h = document.querySelector('h2');
    const name = h?.innerText?.trim() || '';
    const sub = h?.parentElement?.querySelector('div')?.innerText?.trim() || '';
    return JSON.stringify({name, headline: sub});
})()
""")
print(headline)
PY
```

## Push: Local Files → LinkedIn

### Update About Section

```bash
browser-harness <<'PY'
import json, time

tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    new_tab("https://www.linkedin.com/feed/")
    wait(3)

# Navigate to About edit
goto_url("https://www.linkedin.com/in/yushi-cui/")
wait(3)

# Find and click "Edit about" — use the snapshot approach
snapshot_text = js("document.body.innerText")
if "Edit about" in snapshot_text:
    # Click the edit about link
    js("""
    (() => {
        const links = document.querySelectorAll('a');
        for (const link of links) {
            if (link.innerText.trim() === 'Edit about') {
                link.click();
                return 'clicked';
            }
        }
        return 'not found';
    })()
    """)
    wait(2)
    print("Edit about dialog opened")
else:
    print("Edit about link not found")
PY
```

Then fill the textarea with new content from `LinkedIn-CV-Profile.md` and save.

**Important**: For push operations, always show the user what will change before making edits. Use `--headed` behavior (the real Chrome is already visible).

## Scrape: Job Postings

### Search Jobs

```bash
browser-harness <<'PY'
import json, time

tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    new_tab("https://www.linkedin.com/feed/")
    wait(3)

# Search for jobs
search_query = "full stack developer"
location = "New Zealand"
goto_url(f"https://www.linkedin.com/jobs/search/?keywords={search_query}&location={location}")
wait(3)

# Scroll to load job cards
for i in range(3):
    js("window.scrollBy(0, 600)")
    time.sleep(0.5)

# Extract job listings
jobs = js("""
(() => {
    const cards = document.querySelectorAll('[class*="job-card"]');
    const seen = new Set();
    const results = [];
    cards.forEach(card => {
        const text = card.innerText.trim();
        const lines = text.split('\\n').filter(l => l.trim());
        if (lines.length >= 2) {
            const title = lines[0];
            const company = lines[1];
            const key = title + company;
            if (!seen.has(key) && title.length > 3 && company.length > 1) {
                seen.add(key);
                const link = card.querySelector('a[href*="/jobs/view/"]')?.href || '';
                results.push({title, company, link: link.slice(0, 150)});
            }
        }
    });
    return JSON.stringify(results.slice(0, 10));
})()
""")
print(jobs)
PY
```

### Get Full Job Description

```bash
browser-harness <<'PY'
import json, time

# Navigate to a specific job posting
job_url = "JOB_URL_HERE"
goto_url(job_url)
wait(3)

# Extract the full job description
jd = js("""
(() => {
    const desc = document.querySelector('.jobs-description__content') ||
                 document.querySelector('.show-more-less-html__markup');
    return desc ? desc.innerText.trim() : document.querySelector('main')?.innerText?.slice(0, 5000) || 'not found';
})()
""")
print(jd)
PY
```

## Tab Management

Always reuse existing LinkedIn tabs when possible:

```bash
# Find existing LinkedIn tab
tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    # Navigate to feed (will use existing session cookies)
    new_tab("https://www.linkedin.com/feed/")
    wait(3)
```

## Key Rules

- LinkedIn is the **source of truth** — always pull fresh data before pushing
- Never push without showing the user the diff first
- Use detail pages (`/details/experience/`, `/details/skills/`) for reliable data extraction
- The main profile page lazy-loads sections — use detail pages instead
- Rate limit: add `wait(2)` between page navigations to avoid LinkedIn throttling
- If LinkedIn shows an auth wall, ask the user to log in to LinkedIn in their Chrome
- Always close any test tabs when done
