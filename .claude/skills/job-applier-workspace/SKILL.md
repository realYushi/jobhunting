---
name: job-applier
description: Create complete job application packages with tailored CV and cover letter. Use this skill whenever the user wants to apply for a job, create a job application, generate a resume/CV, or mentions "apply for this job", "job application", "tailor my resume", "cover letter for job". Automatically analyzes job requirements, researches the company, generates role-optimized resume.json, creates resume in Reactive Resume, generates PDF, and creates customized cover letter.
compatibility: Requires file system access, Python 3 for JSON resume generation, and Reactive Resume MCP
---

# Job Application Skill

Automate the creation of complete, tailored job application packages from a job description, with automatic PDF generation via Reactive Resume.

## When This Skill Triggers

Use this skill proactively when users:
- Say "apply for this job" or "create application for X company"
- Paste a job description and ask for help applying
- Request a tailored resume/CV for a specific job
- Ask for a cover letter for a job application
- Mention they want to apply somewhere and need documents prepared

## Workflow Overview

1. **Parse job description** - Extract company name, role title, requirements, and key details
2. **Conduct company research** - Research the company's mission, values, recent news, and culture
3. **Analyze job fit** - Match job requirements against the user's background, calculate match score
4. **Create application structure** - Set up organized folder with research and documents
5. **Generate tailored resume locally** - Create role-optimized resume.json based on job type
6. **Create resume in Reactive Resume** - Upload to Reactive Resume via MCP and generate PDF
7. **Write customized cover letter** - Draft compelling cover letter using research insights
8. **Update tracking** - Log application in tracker with resume ID and PDF URL
9. **Lock resume** - Prevent accidental edits after submission

## Expected User Input

The user will provide a job description (pasted in chat). Extract:
- Company name
- Job title/role
- Role type (frontend/backend/fullstack/data/devops)
- Required skills and experience
- Preferred qualifications
- Company context and values

If role type is unclear, infer from job title and required skills:
- **frontend**: UI/UX, React, Vue, JavaScript, CSS, frontend web dev
- **backend**: API, server-side, Python, Java, databases, backend systems
- **fullstack**: Full-stack, end-to-end, both frontend and backend
- **data**: Data analysis, ML/AI, analytics, data science, machine learning
- **devops**: DevOps, cloud, infrastructure, CI/CD, deployment, SRE

## Step-by-Step Instructions

### 1. Initial Setup and Validation

**Check application tracker first:**
```bash
cat tools/application-tracker.json
```

Verify:
- Maximum 5 active applications (enforce limit)
- Check if application for this company already exists

**If company already has an active application:**
- Inform the user: "An application for [Company] already exists at `applications/active/[Company]/`"
- Ask: "Should I overwrite it, or use a different company identifier (e.g., 'Company-Role-Date')?"

**If at capacity (5 active applications):**
- Inform user they've reached the 5 application limit
- Suggest archiving completed applications before creating new ones

### 2. Extract Job Information

Parse the job description to extract:
- Company name (exact spelling)
- Job title
- Role type (map to: frontend, backend, fullstack, data, devops)
- Required technical skills
- Required experience level
- Key responsibilities
- Company values/mission (if mentioned)
- Location and work arrangement (remote/hybrid/onsite)

**Create application directory:**
```bash
mkdir -p "applications/active/{Company}/research"
mkdir -p "applications/active/{Company}/documents"
```

### 3. Conduct Company Research

**Research the company to understand:**
- What they do (products/services)
- Company mission and values
- Recent news or achievements
- Company culture and work environment
- Technology stack (if publicly known)
- Why someone would want to work there

**Sources to check:**
- Company website (About/Careers pages)
- Recent news articles
- LinkedIn company page
- Glassdoor reviews (if helpful for culture insights)
- GitHub or tech blog (for engineering culture)

**Synthesize research into 3-5 key insights** that will inform the cover letter hook and demonstrate genuine interest.

### 4. Create Job Analysis

**File**: `applications/active/{Company}/research/analysis.md`

Use the analysis template structure:
```markdown
# Job Analysis: {Company} - {Role Title}

## 1. Role Overview
[Extract from job description: level, department, location, etc.]

## 2. Requirements
[Mandatory and preferred skills with experience levels]

## 3. Skills Matching
**Match Score**: [Calculate based on requirements vs. LinkedIn-CV-Profile.md]

### Strong Matches (90-100%)
[List requirements user strongly meets with evidence]

### Good Matches (70-89%)
[List requirements user partially meets]

### Skill Gaps (Below 70%)
[List missing requirements with learning/positioning strategy]

## 4. Application Strategy
**Strategic Keywords**: [Extract from job description]
**Cover Letter Focus**: [Top 3 selling points based on strong matches]
**Resume Optimization**: [Which skills/projects to emphasize]

## 5. Red Flags & Concerns
[Any issues or gaps to address]
```

**To calculate match score:**
- Read `LinkedIn-CV-Profile.md` and `templates/base-resume.json` to understand user's background
- For each required skill, assess if user has demonstrated experience
- Strong match: Direct experience with evidence
- Good match: Related experience or academic background
- Gap: No clear evidence but can be learned or repositioned

### 5. Save Job Description

**File**: `applications/active/{Company}/research/job-description.md`

Save the original job description exactly as provided by the user.

### 6. Generate Tailored Resume (Local Backup)

**Use the json-resume-manager.py script:**

```bash
python3 tools/json-resume-manager.py \
  --company "{Company}" \
  --role "{role-type}" \
  --output "applications/active/{Company}/documents/resume.json"
```

**If you need to customize further**, you can:
- Use `--hide` to hide irrelevant sections
- Use `--show` to show specific sections
- Use `--keywords` to add job-specific keywords

**Role-specific customizations are already built into the script:**
- **frontend**: Prioritizes React/Vue/frontend skills, updates summary
- **backend**: Emphasizes backend/database skills, Python experience
- **fullstack**: Keeps balanced profile
- **devops**: Highlights Docker/cloud/DevOps skills
- **data**: Hides less relevant sections, focuses on data/ML

The script reads from `templates/base-resume.json` which contains the user's complete profile.

**Note:** This local file serves as a backup. The next step will create the active resume in Reactive Resume.

### 7. Create Resume in Reactive Resume and Generate PDF

**Create resume with MCP:**

Use the Reactive Resume MCP tools to create a resume directly in the platform:

```
mcp__reactive-resume__create_resume(
  name="{Company} - {Job Title}",
  slug="{company-slug}-{date}",
  tags=["active", "{role-type}"],
  withSampleData=false
)
```

**Naming convention:**
- `name`: "{Company} - {Job Title}" (e.g., "Acme Corp - Senior Frontend Developer")
- `slug`: "{company-slug}-{YYYY-MM-DD}" (e.g., "acme-corp-2026-03-09")
- Use lowercase, hyphens for spaces in slug
- Include date to ensure uniqueness

**Then patch the resume with the tailored content:**

After creating the resume, you'll get a resume ID. Read the local `resume.json` you generated in step 6, then use `patch_resume` to apply it to the Reactive Resume version.

**Key mappings from local resume.json to Reactive Resume format:**
- `/basics/name` → basics.name
- `/basics/email` → basics.email
- `/basics/phone` → basics.phone
- `/basics/location` → basics.location
- `/basics/url` → basics.website
- `/summary` → summary.content (as HTML)
- `/skills` → sections.skills.items
- `/work` → sections.experience.items (convert to HTML descriptions)
- `/education` → sections.education.items
- `/projects` → sections.projects.items

**Generate PDF:**

```
mcp__reactive-resume__export_resume_pdf(id=<resume-id>)
```

This returns a download URL for the PDF.

**Get preview screenshot (optional but helpful):**

```
mcp__reactive-resume__get_resume_screenshot(id=<resume-id>)
```

This returns a WebP preview of the first page.

**Save resume metadata:**

Create `applications/active/{Company}/documents/resume-metadata.json`:
```json
{
  "resume_id": "<resume-id>",
  "resume_name": "{Company} - {Job Title}",
  "slug": "{company-slug}-{date}",
  "pdf_url": "<pdf-download-url>",
  "screenshot_url": "<screenshot-url>",
  "created_at": "<timestamp>",
  "locked": false
}
```

### 8. Write Tailored Cover Letter

**File**: `applications/active/{Company}/documents/cover-letter.md`

**Read the cover letter template first:**
```bash
cat templates/cover-letter.md
```

**Customize based on:**
1. **Company research** - Open with specific company insight (recent news, mission alignment, product interest)
2. **Job analysis** - Emphasize the top 3 strong matches from skills matching
3. **Evidence** - Include specific project names and metrics from LinkedIn-CV-Profile.md
4. **Role type** - Adjust language to match role focus (frontend/backend/etc.)
5. **Gaps strategy** - If there are skill gaps, address them through adjacent experience or learning ability

**Cover letter structure:**
```markdown
# Cover Letter - {Company}

**Date:** [Current Date]
**Position:** {Job Title}

Hi [Hiring Manager Name or "Hiring Team"],

[Opening paragraph: Hook with specific company insight - why this company excites you]

[Middle paragraph: Top 3 strongest matches with specific evidence from your experience]

[Closing paragraph: Reiterate enthusiasm, call to action]

Sincerely,
Yushi Cui
```

**Key customization points:**
- Replace all [brackets] with specific details
- Use company's language from job description and research
- Include 2-3 specific metrics or achievements that align with job requirements
- Match tone to company culture (startup casual vs. enterprise formal)

### 9. Update Application Tracker

**File**: `tools/application-tracker.json`

Add new entry with resume tracking:
```json
{
  "company": "{Company}",
  "position": "{Job Title}",
  "date_applied": "[YYYY-MM-DD]",
  "status": "In Progress",
  "priority": "High",
  "resume_id": "<resume-id-from-reactive-resume>",
  "resume_url": "https://rxresu.me/dashboard/resumes/<resume-id>",
  "pdf_url": "<pdf-download-url>"
}
```

Update metadata `last_updated` field.

### 10. Lock Resume (After Submission)

**Important:** Only lock the resume AFTER the user confirms they've submitted the application.

When the user confirms submission:
```
mcp__reactive-resume__lock_resume(id=<resume-id>)
```

Update `resume-metadata.json`:
```json
{
  "locked": true,
  "locked_at": "<timestamp>"
}
```

This prevents accidental edits to a resume that's already been submitted.

### 11. Final Summary

Tell the user:
```
✅ Job application package created for {Company}!

📁 Location: applications/active/{Company}/
├── research/
│   ├── job-description.md (Original job posting)
│   └── analysis.md (Skills matching & strategy)
└── documents/
    ├── resume.json (Local backup)
    ├── resume-metadata.json (Reactive Resume tracking)
    └── cover-letter.md (Customized for {Company})

📊 Match Score: {X}% - {Readiness assessment}

📄 Resume PDF: {pdf-url}
👀 Resume Preview: {screenshot-url}

🎯 Next steps:
1. Review the cover letter and customize any specifics
2. Download and review the PDF resume from the link above
3. Submit application through company portal
4. Tell me when you've submitted so I can lock the resume

Good luck! 🍀
```

## Edge Cases

### Vague or Short Job Description
If the job description is very brief or missing key details:
- Do your best to extract available information
- Note in the analysis what information is missing
- Make reasonable assumptions based on role title and company
- Suggest the user review and fill gaps before submitting

### Unclear Role Type
If you can't determine the role type from the job description:
- Default to `fullstack` as it keeps the resume balanced
- Note in your analysis that you made this assumption
- Suggest the user verify and regenerate if needed

### Company Research Fails
If you can't find company information:
- Focus on what's in the job description
- Use general statements about the role/industry
- Note in the cover letter that you're excited to learn more about the company
- Don't fabricate specific company insights

### Non-Standard Role Types
If the job doesn't fit the 5 predefined types (e.g., "Mobile Developer", "Security Engineer"):
- Map to the closest type based on technical requirements
- Example: Mobile Developer → frontend (if React Native) or fullstack
- Example: Security Engineer → backend or devops depending on focus
- Note the mapping in your analysis

### Resume Creation Fails
If the Reactive Resume MCP is unavailable or fails:
- Fall back to local resume.json generation only
- Inform the user they'll need to manually import to Reactive Resume
- Continue with the rest of the workflow

### Resume Already Exists
If a resume with the same slug already exists:
- Append a number to make it unique (e.g., "acme-corp-2026-03-09-2")
- Or use a timestamp for guaranteed uniqueness

## Important Notes

- **File paths are relative to the jobhunting project root**
- **Always read existing files first** (LinkedIn-CV-Profile.md, base-resume.json) to understand the user's background
- **Don't fabricate experience** - only use what's documented in the profile files
- **Keep cover letter concise** - 3-4 paragraphs max, hiring managers skim
- **Use specific metrics** - "40% performance improvement" is better than "improved performance"
- **Match job description language** - if they say "TypeScript", don't say "JavaScript" if you have TypeScript experience
- **Be honest about gaps** - it's better to acknowledge a gap than to overstate experience
- **Lock resumes after submission** - prevents accidental changes to submitted applications
- **Keep local backup** - the local resume.json serves as a backup if Reactive Resume is unavailable

## Dependencies

- `tools/json-resume-manager.py` - Generates role-specific resume.json
- `templates/base-resume.json` - Master resume data
- `templates/cover-letter.md` - Cover letter template reference
- `LinkedIn-CV-Profile.md` - User's professional background
- `tools/application-tracker.json` - Application tracking database
- **Reactive Resume MCP** - Creates resumes, generates PDFs, manages resume lifecycle
