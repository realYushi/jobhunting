---
name: job-applier
description: Create complete job application packages with tailored CV and cover letter. Use this skill whenever the user wants to apply for a job, create a job application, generate a resume/CV, or mentions "apply for this job", "job application", "tailor my resume", "cover letter for job". Automatically analyzes job requirements, researches the company, generates role-optimized resume.json, creates resume in Reactive Resume, generates PDF, and creates customized cover letter.
compatibility: Requires file system access, Python 3, and `typst` on PATH (brew install typst). Reactive Resume API key is optional and only needed if you want to also push to the server.
---

# Job Application Skill

Build a tailored application package from a job description. See `AGENTS.md` for project structure.

If the user wants to find jobs first (not paste a JD), use the `linkedin` skill to search and extract the JD, then return here.

## Workflow

### 1. Validate capacity

Read `applications/application-tracker.json`. Max 5 active applications; check for duplicate company entries. If at capacity, suggest archiving first.

### 2. Parse the JD

Extract company, job title, location, work arrangement, required vs preferred skills. Infer `role` from the title:

- `frontend` — UI/UX, React, Vue, CSS
- `backend` — APIs, servers, databases
- `fullstack` — both
- `data` — analysis, ML/AI
- `devops` — cloud, infra, CI/CD

Default to `fullstack` when unclear.

### 3. Score & decide (apply/skip gate)

Don't burn effort tailoring a package you won't send. Save the JD to a temp file, then:

```bash
python3 tools/match_score.py \
  --jd "{path-to-jd}" \
  --required "Skill A" "Skill B" "5+ years X" \
  --preferred "Nice C"
```

Verdict rubric: **90-100%** overqualified (flight-risk) · **75-89%** apply · **60-74%** apply with strong cover · **<60%** skip unless dream role.

The match score is a deterministic keyword count, not a judgment. Before trusting a low verdict, scan each MISS for **adjacent tech** in the candidate's profile (NestJS ≈ FastAPI, Azure ≈ AWS, Vue ≈ React) and surface those to the user — they're partial matches the score ignores. Then show the tool's output verbatim, add the adjacency notes, and ask `Proceed with this application? (y/n)`. On skip, stop here. The red-flag scan misses context and false-positives on any `$` — treat as a prompt for judgment, not a verdict.

### 4. Research the company

Web search for mission, recent news, tech stack, culture. Synthesize 3-5 insights you'll actually use in the cover letter. If research fails, fall back to JD-only — don't fabricate.

### 5. Build the package skeleton

One call creates the directory, saves the JD, scaffolds analysis.md, generates resume.json, drafts the cover letter, and upserts the tracker:

```bash
python3 tools/apply.py \
  --job "{path-to-jd}" \
  --company "{Company}" \
  --position "{Job Title}" \
  --role "{role}" \
  --keywords "keyword1" "keyword2" \
  --priority "Medium"
```

`--keywords` seeds the tailored resume (injected into the right skill group) and the analysis.md scaffold. Pass the strategic JD terms here — not every word, just the 5-10 the role hinges on.

Output lands in `applications/active/{Company}/`.

### 6. Fill in the human parts

`apply.py` only scaffolds — these still need your judgment:

- `research/analysis.md` — match score per requirement, top 3 selling points, skill gaps with positioning. See `templates/analysis-template.md` for structure (already seeded into the file).
- `documents/cover-letter.md` — replace the scaffold with the real opening, top 3 evidence-backed matches, and tone matched to company culture. 200-400 words, 3 paragraphs.

Pull candidate background from `LinkedIn-CV-Profile.md` and `templates/base-resume.json`. Never invent experience.

### 7. ATS coverage check

```bash
python3 tools/ats_check.py \
  --resume "applications/active/{Company}/documents/resume.json" \
  --jd "applications/active/{Company}/research/job-description.md" \
  --critical "Skill A" "exact phrase B"
```

Without `--critical`, the tool auto-discovers the top 10 JD keywords. Exits 1 below `--threshold` (default 80%). Density target 2-4× per keyword.

If coverage fails, either re-run `tools/resume.py --keywords <missing>` to inject the term into the right skill group, or — if it's a genuine gap — leave it out and let the cover letter address it.

### 8. PDF render

`apply.py` already renders `documents/resume.pdf` locally via Typst — confirm
it exists and inspect it. If the render was skipped (e.g. typst missing), the
warning surfaces in step 9's output and you can re-render with:

```bash
python3 -c "from pathlib import Path; from tools.lib.pdf import \
  render_resume_pdf_from_file; \
  render_resume_pdf_from_file(Path('applications/active/{Company}/documents/resume.json'), \
                              Path('applications/active/{Company}/documents/resume.pdf'))"
```

**Optional**: also push to Reactive Resume if the user wants the editable copy
on the server — not required for submission.

```bash
python3 tools/reactive_resume.py push \
  --file "applications/active/{Company}/documents/resume.json" \
  --name "{Company} - {Job Title}" \
  --slug "{company-slug}-{YYYY-MM-DD}" \
  --tags "active" "{role}"
```

Add `--dry-run` to preview without hitting the API.

### 9. Validate, then hand off

`apply.py` already emits warnings for unresolved placeholders, off-target cover
letter length, and wrong paragraph count — surface those to the user.

Then run the **semantic** checks in `templates/quality-framework.md` before
handing off: truthfulness against `templates/base-resume.json` +
`LinkedIn-CV-Profile.md`, tone match, no buzzword stuffing. Those are judgment
calls code can't make for you.

### 10. Lock after submission

Only when the user confirms they've submitted:

```bash
python3 tools/reactive_resume.py lock <resume-id>
```

## Notes

- Never fabricate experience — only what's in `LinkedIn-CV-Profile.md` and `base-resume.json`.
- Match JD terminology exactly; hiring managers and ATS both pattern-match.
- Vague JD → note missing info and make assumptions explicit.
- Duplicate slug → append a number (`acme-corp-2026-03-09-2`).
