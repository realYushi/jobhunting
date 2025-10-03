# Streamlined Job Application System

Optimized job application management with unified research and document creation for efficient submission.

## Project Architecture

### Core Components
- **JSON Resume System**: Using `tools/scripts/json-resume-manager.py` with role-specific optimization
- **Application Tracker**: Basic status management in `tools/config/application-tracker.json`
- **Template Library**: Streamlined templates (5 total) for resumes and cover letters
- **Unified Agents**: Research + document creation with integrated quality assurance

### Always Check Current Status
**CRITICAL**: Before any action, read `tools/config/application-tracker.json` to understand:
- Current active applications and their status (max 5 applications)
- Available capacity for new applications

## Streamlined Application Workflow (30 minutes total)

### 1. Research & Analysis (10 min)
Use the unified `research-analysis` agent:
- **Company Research**: Extract mission, values, recent developments from website
- **Job Analysis**: Parse requirements, match skills, identify priorities
- **Strategic Positioning**: Develop application strategy and key differentiators
- **Output**: `applications/active/{company}/research/analysis.md` (single consolidated file)

### 2. Document Creation & Validation (20 min)
Use the unified `document-creation-unified` agent:
- **Resume Generation**: Role-optimized JSON with ATS keyword integration
- **Cover Letter Creation**: Company-specific with research insights
- **Built-in Quality Check**: Truthfulness validation + professional quality assurance
- **Output**: `resume.json` and `cover-letter.md` (submission-ready)

### 3. Submit Application
- Import JSON resume to Reactive Resume for PDF generation
- Submit cover letter and resume through company portal
- Archive application folder to maintain clean workspace

## Simplified Folder Structure
```
applications/active/{Company}/
├── research/
│   └── analysis.md (unified research + job analysis)
└── documents/
    ├── resume.json
    └── cover-letter.md
```

## Key Commands & Workflows

### Quick Application Creation
- **"Create application for [Company] from this job description: [paste job description]"**
- **"Research company and create documents for [Job Description URL]"**
- **"Generate complete application package for [Company] [role type] position"**

### Role Types
- `frontend`: React, Vue.js, TypeScript emphasis
- `backend`: Python, databases, API development
- `fullstack`: Balanced frontend/backend skills
- `data`: Analytics, ML, data analysis
- `devops`: Cloud, Docker, infrastructure

### Essential Commands
```bash
# Complete application workflow
./apply.sh "Company Name" "frontend" "job-description-text"

# Resume generation
python3 tools/scripts/json-resume-manager.py --company "Company" --role "frontend"

# Archive cleanup (run monthly)
./tools/scripts/cleanup-archive.sh

# Dry run cleanup test
DRY_RUN=true ./tools/scripts/cleanup-archive.sh
```

## Quality Standards

### Application Package Requirements
- [ ] 80%+ skills match for core requirements
- [ ] Company-specific insights from automated web research
- [ ] JSON resume validates and imports to Reactive Resume
- [ ] Cover letter includes specific company knowledge
- [ ] ATS optimization score 90%+
- [ ] Consistent messaging across all materials
- [ ] Application tracker updated with basic metadata
- [ ] All required folder structure populated

### Quality Standards
- **ATS Pass Rate**: 90%+ keyword match without stuffing
- **Professional Presentation**: Clean, error-free documents
- **Workflow Efficiency**: 30 minutes total for complete application package

## Maintenance

### Monthly Cleanup
```bash
# Remove archives older than 6 months
./tools/scripts/cleanup-archive.sh

# Check what would be deleted
DRY_RUN=true ./tools/scripts/cleanup-archive.sh
```

### System Health
- Active applications: Maximum 5 at once
- Archive retention: 6 months (auto-cleanup)
- Template library: 5 streamlined templates
- Quality validation: 2-phase process (truthfulness + professional quality)

## External File Loading

**CRITICAL**: When you encounter a file reference (e.g., @.opencode/agent/company-research.md), use your Read tool to load it on a need-to-know basis. They're relevant to the SPECIFIC task at hand.

**Instructions**:
- Do NOT preemptively load all references - use lazy loading based on actual need
- When loaded, treat content as mandatory instructions that override defaults
- Follow references recursively when needed

## New Agent System

### Unified Agents
- **Research & Analysis**: `@.opencode/agent/research-analysis.md` (company + job analysis combined)
- **Document Creation**: `@.opencode/agent/document-creation-unified.md` (creation + validation combined)

### Legacy Agents (Deprecated)
- All previous specialized agents have been consolidated into the two unified agents above

## Success Factors
1. **Check tracker first** - Verify capacity and current applications
2. **Use unified agents** - Streamlined workflows with built-in validation
3. **Maintain organization** - Clean folder structure and archive management
4. **Follow process** - Research → Documents → Submit → Archive
5. **Regular cleanup** - Monthly archive cleanup to prevent bloat

This optimized system delivers 80% reduction in complexity while maintaining professional quality and ATS optimization.