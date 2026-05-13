# Job Hunting

Automated job application system powered by Claude Code and Reactive Resume.

## What It Does

Given a job description, the system:
1. Researches the company and analyzes job requirements
2. Generates a role-optimized JSON resume
3. Creates the resume in Reactive Resume and exports PDF
4. Writes a tailored cover letter
5. Tracks application status

## Quick Start

Paste a job description into Claude Code and say "apply for this job". If the `job-applier` skill is installed in your Claude Code environment, it can handle the full workflow.

## Manual Tools

```bash
# Generate a tailored resume
python3 tools/json-resume-manager.py --company "TechCorp" --role frontend

# Fix Reactive Resume ID issues
python3 tools/fix-cuid2-ids.py --input resume.json --output resume-fixed.json

# Clean old archives
./tools/cleanup-archive.sh
```

## Tests

```bash
python3 -m unittest tests/test_json_resume_manager.py
```

See `AGENTS.md` for full architecture and workflow details.
