# Job Application System

Automated job application workflow: analyze job descriptions, generate tailored resumes, and create cover letters.

## Project Structure

```
templates/
  base-resume.json              # Master resume (Reactive Resume format)
  cover-letter.md               # Cover letter template
  analysis-template.md          # Job analysis template
  quality-framework.md          # Truthfulness + quality validation
  json-resume-guide.md          # JSON resume format reference
tools/
  apply.py                      # Orchestrates the full application package (dry-run supported)
  status.py                     # Prints tracker status and missing PDFs
  resume.py                     # Generates role-optimized resume.json
  reactive_resume.py            # Reactive Resume API client (create, push, PDF, lock)
  fix_cuid2_ids.py              # Fixes IDs for Reactive Resume compatibility
  cleanup-archive.sh            # Removes old archived applications
  lib/                          # Shared library (api, config, paths, resume, templates, tracker, validation, workflow)
applications/                   # Created on first application run
  application-tracker.json      # Application status tracking
  active/{Company}/             # Current applications
    research/
      job-description.md        # Original posting
      analysis.md               # Skills matching & strategy
    documents/
      resume.json               # Tailored resume
      resume-metadata.json      # Reactive Resume tracking (ID, PDF path)
      resume.pdf                # Exported PDF
      cover-letter.md           # Customized cover letter
  archive/                      # Completed/withdrawn applications
LinkedIn-CV-Profile.md          # Professional background source
.agents/skills/                 # Local Claude Code skills used by this repo
```

## Source of Truth

- **Background/experience**: `LinkedIn-CV-Profile.md` and `templates/base-resume.json`
- **Never fabricate** claims not supported by these files
- **Validation**: Run through `templates/quality-framework.md` before submission

## Application Tracker Schema

```json
{
  "meta": { "last_updated": "YYYY-MM-DD", "version": "5.1" },
  "applications": {
    "active": [
      {
        "company": "Name",
        "position": "Title",
        "date_applied": "YYYY-MM-DD",
        "status": "In Progress|Submitted|Interview",
        "priority": "High|Medium|Low",
        "resume_id": "reactive-resume-id",
        "pdf_path": "path/to/resume.pdf",
        "source": "linkedin|seek",
        "job_id": "stable-source-side-id",
        "url": "https://..."
      }
    ],
    "interviews": [],
    "offers": [],
    "rejected": [],
    "withdrawn": []
  },
  "seen_jobs": {
    "linkedin": ["job-id-1", "job-id-2"],
    "seek": []
  }
}
```

Dedup: when a record has both `source` and `job_id`, that pair is the primary
key (the scraper can distinguish "Caruso" from "Caruso Corp" when they share an
LinkedIn job ID). Manually pasted JDs without those fields fall back to
`(company, position)`. `seen_jobs` is the scraper's "skip these" set.

## Resume Generation

```bash
# Role-optimized resume
python3 tools/resume.py --company "Company" --role frontend --output path/resume.json

# With extra keywords
python3 tools/resume.py --company "Company" --role backend --keywords "FastAPI" "Redis"

# List sections
python3 tools/resume.py --list-sections
```

Role types: `frontend`, `backend`, `fullstack`, `data`, `devops`

## Reactive Resume API

Requires `.env` with `REACTIVE_RESUME_API_KEY` and `REACTIVE_RESUME_BASE_URL`.

```bash
# Full workflow: push local resume.json → create in Reactive Resume → export PDF
python3 tools/reactive_resume.py push \
  --file path/resume.json --name "Company - Role" --slug "company-role" \
  --tags "active" "frontend" --pdf path/resume.pdf

# List all resumes
python3 tools/reactive_resume.py list

# Export PDF only
python3 tools/reactive_resume.py pdf <resume-id> -o output.pdf

# Lock resume after submission
python3 tools/reactive_resume.py lock <resume-id>

# Delete a resume
python3 tools/reactive_resume.py delete <resume-id>
```

## Archive Cleanup

```bash
./tools/cleanup-archive.sh              # Interactive cleanup (6+ months old)
DRY_RUN=true ./tools/cleanup-archive.sh # Preview only
```

## Workflow

1. Parse job description, extract company/role/requirements
2. Research company (mission, values, tech stack, recent news)
3. Analyze job fit against candidate background
4. Generate tailored resume.json via tools/resume.py
5. Create resume in Reactive Resume via API client, export PDF
6. Write cover letter using research insights and analysis
7. Validate via quality-framework.md
8. Update applications/application-tracker.json
9. Lock resume after submission

## LinkedIn Integration

Uses `browser-harness` connected to your real Chrome. Requires Chrome running with `chrome://inspect/#remote-debugging` enabled.

### Pull profile from LinkedIn (source of truth)

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
goto_url("https://www.linkedin.com/in/yushi-cui/details/experience/")
wait(3)
experience = js("document.querySelector('main')?.innerText?.slice(0, 5000) || ''")
print(experience)
PY
```

Detail pages for extraction: `/details/experience/`, `/details/education/`, `/details/skills/`, `/details/certifications/`

### Scrape job postings from LinkedIn

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
goto_url("https://www.linkedin.com/jobs/search/?keywords=full+stack&location=New+Zealand")
wait(3)
# ... extract job cards
PY
```

### Update LinkedIn profile

Navigate to edit pages, fill content from local files, save.
