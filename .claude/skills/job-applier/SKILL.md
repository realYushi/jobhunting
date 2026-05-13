---
name: job-applier
description: Create complete job application packages with tailored CV and cover letter. Use this skill whenever the user wants to apply for a job, create a job application, generate a resume/CV, or mentions "apply for this job", "job application", "tailor my resume", "cover letter for job". Automatically analyzes job requirements, researches the company, generates role-optimized resume.json, creates resume in Reactive Resume, generates PDF, and creates customized cover letter.
compatibility: Requires file system access, Python 3, and Reactive Resume API key in .env
---

# Job Application Skill

Create tailored application packages from a job description. See `AGENTS.md` for project structure and file references.

## Trigger Conditions

- User pastes a job description and asks for help applying
- "apply for this job", "create application for X", "tailor my resume for"
- Requests for cover letter or resume for a specific job
- "search LinkedIn for jobs", "find jobs on LinkedIn"

## Workflow

### 0. (Optional) Scrape Job from LinkedIn

If the user asks to find jobs rather than pasting a JD:

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
goto_url("https://www.linkedin.com/jobs/search/?keywords={query}&location=New+Zealand")
wait(3)
for i in range(3):
    js("window.scrollBy(0, 600)")
    time.sleep(0.5)
jobs = js("""(() => {
    const cards = document.querySelectorAll('[class*=\"job-card\"]');
    const seen = new Set();
    const results = [];
    cards.forEach(card => {
        const text = card.innerText.trim();
        const lines = text.split('\\n').filter(l => l.trim());
        if (lines.length >= 2) {
            const title = lines[0]; const company = lines[1];
            const key = title + company;
            if (!seen.has(key) && title.length > 3) {
                seen.add(key);
                const link = card.querySelector('a[href*=\"/jobs/view/\"]')?.href || '';
                results.push({title, company, link: link.slice(0, 150)});
            }
        }
    });
    return JSON.stringify(results.slice(0, 10));
})()""")
print(jobs)
PY
```

Present the list to the user. When they pick one, navigate to that job URL and extract the full JD:

```bash
browser-harness <<'PY'
goto_url("{job_url}")
wait(3)
jd = js("""(() => {
    const desc = document.querySelector('.jobs-description__content') ||
                 document.querySelector('.show-more-less-html__markup');
    return desc ? desc.innerText.trim() : 'not found';
})()""")
print(jd)
PY
```

Then feed the JD into step 1.

### 1. Validate Capacity

Read `applications/application-tracker.json`:

- Max 5 active applications
- Check for duplicate company entries
- If at capacity, suggest archiving before creating new

### 2. Parse Job Description

Extract: company name, job title, role type, required/preferred skills, location, work arrangement.

Infer role type from job title and skills:

- **frontend**: UI/UX, React, Vue, CSS, frontend web dev
- **backend**: API, server-side, Python, databases
- **fullstack**: End-to-end, both frontend and backend
- **data**: Data analysis, ML/AI, analytics
- **devops**: Cloud, infrastructure, CI/CD, SRE

Default to `fullstack` if unclear.

### 3. Research Company

Use web search to find: mission/values, recent news, tech stack, culture, why someone would want to work there.

Synthesize into 3-5 key insights for the cover letter.

### 4. Analyze Job Fit

Read `LinkedIn-CV-Profile.md` and `templates/base-resume.json` for candidate background.

Create `applications/active/{Company}/research/analysis.md` using `templates/analysis-template.md`:

- Calculate match score per requirement
- Identify top 3 selling points
- Note skill gaps with positioning strategy
- Extract strategic keywords for ATS

### 5. Save Job Description

Save original to `applications/active/{Company}/research/job-description.md`.

### 6. Generate Resume

```bash
python3 tools/json-resume-manager.py \
  --company "{Company}" --role "{role}" \
  --output "applications/active/{Company}/documents/resume.json" \
  --keywords "keyword1" "keyword2"
```

### 7. Push to Reactive Resume + Export PDF

```bash
python3 tools/reactive-resume-client.py push \
  --file "applications/active/{Company}/documents/resume.json" \
  --name "{Company} - {Job Title}" \
  --slug "{company-slug}-{YYYY-MM-DD}" \
  --tags "active" "{role}" \
  --pdf "applications/active/{Company}/documents/resume.pdf"
```

Save the output to `applications/active/{Company}/documents/resume-metadata.json`:

```json
{
  "resume_id": "<id>",
  "name": "{Company} - {Job Title}",
  "slug": "<slug>",
  "tags": ["active", "{role}"],
  "pdf_path": "applications/active/{Company}/documents/resume.pdf",
  "created_at": "<timestamp>",
  "locked": false
}
```

If the API key is missing or the request fails, fall back to local resume.json only.

### 8. Write Cover Letter

Read `templates/cover-letter.md` for structure. Create `applications/active/{Company}/documents/cover-letter.md`.

Customize with:

- Company-specific opening from research insights
- Top 3 skill matches with specific evidence and metrics
- Tone matched to company culture
- 200-400 words, 3 paragraphs max

### 9. Update Tracker

Add entry to `applications/application-tracker.json` with company, position, date, status, resume_id, and pdf_path.

### 10. Validate

Run through `templates/quality-framework.md` checklist before presenting to user.

### 11. Lock After Submission

Only when user confirms submission:

```bash
python3 tools/reactive-resume-client.py lock <resume-id>
```

## Edge Cases

- **Vague job description**: Note missing info, make reasonable assumptions, suggest user review
- **Unclear role type**: Default to `fullstack`, note assumption
- **Company research fails**: Use only job description info, don't fabricate insights
- **Duplicate slug**: Append number (e.g., `acme-corp-2026-03-09-2`)

## Key Rules

- Never fabricate experience -- only use what's in `LinkedIn-CV-Profile.md` and `base-resume.json`
- Use specific metrics from real experience
- Match job description terminology exactly
- Keep cover letter concise -- hiring managers skim
