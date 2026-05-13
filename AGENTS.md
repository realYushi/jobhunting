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
  json-resume-manager.py        # Generates role-optimized resume.json
  reactive-resume-client.py     # Reactive Resume API client (create, push, PDF, lock)
  fix-cuid2-ids.py              # Fixes IDs for Reactive Resume compatibility
  cleanup-archive.sh            # Removes old archived applications
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
  "meta": { "last_updated": "YYYY-MM-DD", "version": "5.0" },
  "applications": {
    "active": [
      {
        "company": "Name",
        "position": "Title",
        "date_applied": "YYYY-MM-DD",
        "status": "In Progress|Submitted|Interview",
        "priority": "High|Medium|Low",
        "resume_id": "reactive-resume-id",
        "pdf_path": "path/to/resume.pdf"
      }
    ],
    "interviews": [],
    "offers": [],
    "rejected": [],
    "withdrawn": []
  }
}
```

## Resume Generation

```bash
# Role-optimized resume
python3 tools/json-resume-manager.py --company "Company" --role frontend --output path/resume.json

# With extra keywords
python3 tools/json-resume-manager.py --company "Company" --role backend --keywords "FastAPI" "Redis"

# List sections
python3 tools/json-resume-manager.py --list-sections
```

Role types: `frontend`, `backend`, `fullstack`, `data`, `devops`

## Reactive Resume API

Requires `.env` with `REACTIVE_RESUME_API_KEY` and `REACTIVE_RESUME_BASE_URL`.

```bash
# Full workflow: push local resume.json → create in Reactive Resume → export PDF
python3 tools/reactive-resume-client.py push \
  --file path/resume.json --name "Company - Role" --slug "company-role" \
  --tags "active" "frontend" --pdf path/resume.pdf

# List all resumes
python3 tools/reactive-resume-client.py list

# Export PDF only
python3 tools/reactive-resume-client.py pdf <resume-id> -o output.pdf

# Lock resume after submission
python3 tools/reactive-resume-client.py lock <resume-id>

# Delete a resume
python3 tools/reactive-resume-client.py delete <resume-id>
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
4. Generate tailored resume.json via json-resume-manager.py
5. Create resume in Reactive Resume via API client, export PDF
6. Write cover letter using research insights and analysis
7. Validate via quality-framework.md
8. Update applications/application-tracker.json
9. Lock resume after submission
