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
  fix-cuid2-ids.py              # Fixes IDs for Reactive Resume compatibility
  cleanup-archive.sh            # Removes old archived applications
  application-tracker.json      # Application status tracking
applications/
  active/{Company}/             # Current applications
    research/
      job-description.md        # Original posting
      analysis.md               # Skills matching & strategy
    documents/
      resume.json               # Tailored resume
      resume-metadata.json      # Reactive Resume tracking (ID, PDF URL)
      cover-letter.md           # Customized cover letter
  archive/                      # Completed/withdrawn applications
LinkedIn-CV-Profile.md          # Professional background source
.claude/skills/job-applier/     # Claude Code skill for full workflow
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
    "active": [{
      "company": "Name",
      "position": "Title",
      "date_applied": "YYYY-MM-DD",
      "status": "In Progress|Submitted|Interview",
      "priority": "High|Medium|Low",
      "resume_id": "reactive-resume-id",
      "pdf_url": "url"
    }],
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
5. Create resume in Reactive Resume via MCP, export PDF
6. Write cover letter using research insights and analysis
7. Validate via quality-framework.md
8. Update application-tracker.json
9. Lock resume after submission
