# Job Hunting Automation System

This is a structured job application management system using JSON resumes, automated company research, and intelligent agent coordination to maximize interview generation.

## Project Architecture

### Core Components
- **JSON Resume System**: Using `tools/scripts/json-resume-manager.py` with role-specific optimization
- **Application Tracker**: Dynamic status management in `tools/config/application-tracker.json`
- **Template Library**: Reusable components in `templates/` for analysis and documents
- **Agent Coordination**: Specialized agents for company research, job analysis, and document creation

### Always Check Current Status
**CRITICAL**: Before any action, read `tools/config/application-tracker.json` to understand:
- Current active applications and their status (max 5 applications)
- Success metrics and response rates  
- Recent application outcomes and feedback
- Priority levels and next steps

## Agent Workflow Coordination

You should coordinate specialized agents for complete application creation:

### 1. Company Research (20 min)
Use the `company-research` agent for automated web research:
- Direct website analysis via webfetch
- Extract company culture, values, and recent developments
- Generate strategic positioning insights
- Output: `applications/active/{company}/company-research/application-strategy.md`

### 2. Job Analysis (15 min)  
Use the `job-analysis` agent for requirements extraction:
- Parse explicit and implicit job requirements
- Match candidate skills against requirements
- Develop strategic positioning recommendations
- Output: `requirements-analysis.md` and `matching-skills.md`

### 3. Document Creation (25 min)
Use the `document-creation` agent for resume and cover letter generation:
- Generate role-optimized JSON resumes using `json-resume-manager.py`
- Create company-specific cover letters with research insights
- Ensure ATS optimization and keyword integration
- Output: Customized `resume.json` and `cover-letter.md`

### 4. Quality Assurance (15 min)
Use the `document-formatting` agent for validation:
- JSON structure validation and CUID2 compliance
- Reactive Resume platform compatibility testing
- Professional formatting and error checking
- Final quality assurance before submission

### 5. Project Organization (5 min)
Use the `folder-structure` agent for file management:
- Maintain consistent application folder hierarchy
- Ensure proper file naming and organization
- Sync with application tracker system

## Key Commands & Workflows

### Complete Application Creation
- **"Create complete application package for [Company] from job description"**
- **"Generate application materials for [Job Description URL or text]"**
- **"Analyze job and research company automatically for [Company] position"**

### Role Optimization Types
- `frontend`: React, Vue.js, TypeScript focus
- `backend`: Python, databases, API development  
- `fullstack`: Balanced frontend/backend skills
- `devops`: Docker, cloud, infrastructure
- `data`: Analytics, ML, data processing

### Resume Generation Commands
```bash
# Role-specific resume generation
python3 tools/scripts/json-resume-manager.py --company "TechCorp" --role "frontend"

# With specific keywords
python3 tools/scripts/json-resume-manager.py --company "DataCorp" --role "data" --keywords "Python" "Machine Learning"

# Validation
python3 tools/scripts/json-resume-manager.py --validate applications/active/Company/documents/resume.json
```

## Quality Standards

### Application Package Requirements
- [ ] 80%+ skills match for core requirements
- [ ] Company-specific insights from automated web research  
- [ ] JSON resume validates and imports to Reactive Resume
- [ ] Cover letter includes specific company knowledge
- [ ] ATS optimization score 90%+
- [ ] Consistent messaging across all materials
- [ ] Application tracker updated with complete metadata
- [ ] All required folder structure populated

### Success Metrics Focus
- **ATS Pass Rate**: 90%+ keyword match without stuffing
- **Interview Generation**: Clear value proposition and compelling narrative
- **Workflow Efficiency**: 90 minutes total for complete application package
- **Quality Consistency**: Professional presentation meeting industry standards

## External File Loading

**CRITICAL**: When you encounter a file reference (e.g., @.opencode/agent/company-research.md), use your Read tool to load it on a need-to-know basis. They're relevant to the SPECIFIC task at hand.

**Instructions**:
- Do NOT preemptively load all references - use lazy loading based on actual need
- When loaded, treat content as mandatory instructions that override defaults
- Follow references recursively when needed

## Agent Workflow Guidelines

For automated company research: @.opencode/agent/company-research.md
For job requirements analysis: @.opencode/agent/job-analysis.md  
For document creation workflows: @.opencode/agent/document-creation.md
For formatting and validation: @.opencode/agent/document-formatting.md
For project structure management: @.opencode/agent/folder-structure.md

## Critical Success Factors

1. **Always read tracker first** - Understanding current context is essential
2. **Coordinate specialized agents** - Use their expertise rather than doing everything directly
3. **Maintain integration** - Ensure outputs flow logically between agents
4. **Update tracking immediately** - Keep real-time awareness of application status  
5. **Follow JSON workflow** - Use scripts and validation, avoid manual editing
6. **Ensure company consistency** - Match names and details exactly across all materials

This system maximizes efficiency and quality through specialized agent coordination while maintaining strategic oversight across the complete job application workflow.