---
name: linkedin
description: >
  Pull profile data from LinkedIn and push updates back. Use when the user
  wants to sync their LinkedIn profile, update their CV from LinkedIn, scrape
  job postings, or push profile changes. Triggers include "sync LinkedIn",
  "pull from LinkedIn", "update LinkedIn profile", "scrape LinkedIn jobs",
  "LinkedIn job search".
allowed-tools: "Bash(browser-harness:*)"
---

# LinkedIn Integration via browser-harness

LinkedIn.com is the source of truth. This skill drives the user's real Chrome (via browser-harness) to pull profile/job data into local files and push edits back.

## Setup

- `browser-harness` on `$PATH`, Chrome running with remote debugging enabled, user logged into LinkedIn.
- Verify: `browser-harness --doctor` (chrome running + daemon alive must pass).

Every script below begins with the same tab-attach boilerplate — reuse an existing LinkedIn tab or open the feed:

```python
tabs = list_tabs()
li_tab = next((t for t in tabs if "linkedin.com" in t.get("url","")), None)
if li_tab:
    switch_tab(li_tab["targetId"])
else:
    new_tab("https://www.linkedin.com/feed/")
    wait(3)
```

This snippet is implied at the top of every `browser-harness <<'PY'` block.

## Pull: LinkedIn → local files

The main profile page lazy-loads sections, so always use the `/details/<section>/` URLs. They render cleanly into `main`'s innerText.

```bash
browser-harness <<'PY'
import json
# [tab-attach boilerplate]

sections = {}
for name, url in [
    ("about",          "https://www.linkedin.com/in/yushi-cui/"),
    ("experience",     "https://www.linkedin.com/in/yushi-cui/details/experience/"),
    ("education",      "https://www.linkedin.com/in/yushi-cui/details/education/"),
    ("skills",         "https://www.linkedin.com/in/yushi-cui/details/skills/"),
    ("certifications", "https://www.linkedin.com/in/yushi-cui/details/certifications/"),
]:
    goto_url(url); wait(3)
    sections[name] = js("document.querySelector('main')?.innerText?.slice(0, 5000) || ''")

print("=== LINKEDIN_DATA_START ===")
print(json.dumps(sections))
print("=== LINKEDIN_DATA_END ===")
PY
```

Then parse the JSON, update `LinkedIn-CV-Profile.md` (and `templates/base-resume.json` if needed), and report what changed.

**Verify the pull isn't silently empty.** `/details/skills/` and `/details/certifications/` sometimes return only nav + footer text (the list items render lazily, below the slice window). Before writing files, sanity-check each section: if it's under ~200 chars or contains "Sign in" / "Join LinkedIn", treat it as an auth-wall or render failure, surface to the user, and skip the file update for that section.

**Quick headline-only pull** — useful when you only need the name + headline:

```python
goto_url("https://www.linkedin.com/in/yushi-cui/"); wait(3)
print(js("JSON.stringify({name: document.querySelector('h1')?.innerText?.trim(), headline: document.querySelector('.text-body-medium')?.innerText?.trim()})"))
```

## Optimize: profile audit

Use when the user asks to "optimize my LinkedIn", "audit my profile", "improve my headline", or wants recruiter visibility. Pull fresh data first, then score `LinkedIn-CV-Profile.md` against the checklist below and surface gaps.

**Headline** (220 chars)
- Searchable role titles recruiters actually query (e.g., "Full Stack Engineer")
- 2-4 high-value keywords (stack, domain, tools)
- Avoid: "Open to work", "Student at…", emoji spam

**About** (target 1,500-2,000 of 2,600 chars)
- First ~300 chars stand alone as a hook (preview-visible)
- 3-5 paragraphs: who → achievements → what you're looking for
- Explicit `Key skills:` line with 10-15 searchable terms
- Closes with a call-to-action

**Experience** — each role: 4-6 metric-bearing bullets, skill tags (LinkedIn weights these in search), scope sentence.

**Skills** — fill toward 50; top 3 pinned match target roles; endorsements on top 5.

**Featured / Recommendations / Photo / Banner** — featured items present; ≥3 recommendations; face fills ~60% of photo; custom 1584×396 banner.

**Target-role keyword gap** — ask the user what roles they're targeting (or infer from recent applications in `applications/application-tracker.json`). Diff that keyword set against headline + About + skills, and list which to add where.

Output format the user can act on:

```
Headline: 142/220 chars. Missing "Full Stack" and "TypeScript" (top searched).
  Suggested: "Full Stack Engineer | TypeScript, Python, AWS | Shipping 0→1 AI-native products"

About: 1,820 chars ✓. Weak hook. No `Key skills:` line.
  Suggested hook: "I build AI-native products end-to-end — from prompt design to production infra."

Skills: 23/50. Add: TypeScript, Next.js, Postgres, CDP, Playwright
Experience: 2 of 4 roles missing bullets. Role X has no skill tags.
Featured: 0 items. Recommendations: 1 — ask 2 former colleagues.
```

Show the diff before pushing. Never push optimizer suggestions automatically.

## Push: local files → LinkedIn

LinkedIn's edit dialogs are stateful and easy to break. Open the edit surface and **let the user review the field before you fill it** — or surface what you'd type and ask them to paste.

```bash
browser-harness <<'PY'
# [tab-attach boilerplate]
goto_url("https://www.linkedin.com/in/yushi-cui/"); wait(3)
js("""
(() => {
    for (const a of document.querySelectorAll('a')) {
        if (a.innerText.trim() === 'Edit about') { a.click(); return 'clicked'; }
    }
    return 'not found';
})()
""")
wait(2)
capture_screenshot()  # verify the dialog opened
PY
```

Once the dialog is open, screenshot to confirm and fill the textarea (selector varies by LinkedIn build — read it from the DOM, don't hardcode). Always show the user the new text first.

## Scrape: jobs

This is the canonical home for the LinkedIn job-search path used by the `job-applier` skill.

**Search:**

```bash
browser-harness <<'PY'
import json, time
# [tab-attach boilerplate]
goto_url("https://www.linkedin.com/jobs/search/?keywords=full+stack+developer&location=New+Zealand"); wait(3)
for _ in range(3): js("window.scrollBy(0, 600)"); time.sleep(0.5)

jobs = js("""
(() => {
    const seen = new Set(), out = [];
    document.querySelectorAll('[class*="job-card"]').forEach(card => {
        const lines = card.innerText.trim().split('\\n').filter(l => l.trim());
        if (lines.length < 2) return;
        const [title, company] = lines, key = title + company;
        if (seen.has(key) || title.length < 4) return;
        seen.add(key);
        const link = card.querySelector('a[href*="/jobs/view/"]')?.href || '';
        out.push({title, company, link: link.slice(0, 150)});
    });
    return JSON.stringify(out.slice(0, 10));
})()
""")
print(jobs)
PY
```

**Get a full JD:**

```bash
browser-harness <<'PY'
# [tab-attach boilerplate]
goto_url("JOB_URL_HERE"); wait(3)
print(js("""
(() => {
    const desc = document.querySelector('.jobs-description__content') ||
                 document.querySelector('.show-more-less-html__markup');
    return desc ? desc.innerText.trim() : document.querySelector('main')?.innerText?.slice(0, 5000) || 'not found';
})()
"""))
PY
```

## Notes

- LinkedIn is the source of truth — always pull before pushing.
- Use `/details/<section>/` URLs, not the main profile (lazy-loaded).
- `wait(2)` between navigations to avoid throttling.
- Auth wall → stop and ask the user to log in.
- Never push without showing the diff first.
