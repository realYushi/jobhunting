# Job Hunting Workflow System

AI-assisted workflow for systematic job applications: company research → job analysis → document creation → modern formatting.

## 🚀 Modern JSON-Based System

This project uses **JSON as the primary format** for resume management, compatible with modern CV builders like Reactive Resume, with simple markdown cover letters.

### Key Benefits

-   **Single Source of Truth**: One JSON file with all your data
-   **Easy Customization**: Modify sections/skills per job application
-   **Automation Ready**: Scripts can manipulate JSON data
-   **Modern Output**: Professional PDFs via Reactive Resume
-   **Simple Cover Letters**: Clean markdown format for easy editing

## Quick Start

### 1. Create New Job Application

```bash
# Create application structure with role-specific resume
./create-application.sh "TechCorp" frontend

# Available role types: frontend, backend, fullstack, devops, data
```

### 2. Generate Custom Resume

```bash
# Generate customized resume for a company
python tools/scripts/json-resume-manager.py --company "TechCorp" --role "frontend"

# With specific customizations
python tools/scripts/json-resume-manager.py \
  --company "DataCorp" \
  --role "data" \
  --hide "interests" \
  --keywords "Python" "Machine Learning" "SQL"
```

### 3. Import to Reactive Resume

1. Open [Reactive Resume](https://rxresu.me)
2. Create new resume or open existing
3. Import your generated JSON file
4. Customize and export as PDF

## Project Structure

```
jobhunting/
├── templates/
│   ├── resumes/
│   │   ├── base-resume.json          # 🎯 Master JSON resume
│   │   ├── json-resume-guide.md      # Complete JSON guide
│   │   └── skills-library/
│   ├── cover-letters/
│   │   └── templates/                # Markdown templates
│   └── analysis/                     # Job analysis templates
├── applications/
│   └── active/{company}/
│       ├── documents/
│       │   ├── resume.json          # 🎯 Job-specific JSON
│       │   └── cover-letter.md      # Simple markdown
│       ├── company-research/
│       └── job-details/
├── tools/
│   ├── config/
│   │   └── application-tracker.json
│   └── scripts/
│       ├── json-resume-manager.py    # Primary resume tool
│       └── fix-cuid2-ids.py         # ID validation fixer
└── create-application.sh            # Application structure creator
```

## Workflow

### 1. Company Research Analysis

-   Analyze company profile, culture, and key people
-   Extract mission, values, work environment insights
-   Identify company positioning and recent achievements

### 2. Job Description Analysis

-   Extract technical and soft skills requirements
-   Compare requirements to candidate skills library
-   Identify matching skills and potential gaps

### 3. Document Creation (JSON-Based)

-   Generate job-specific resume from base JSON
-   Customize sections and keywords for role
-   Create tailored cover letter using markdown templates

### 4. Document Formatting

-   Import JSON to Reactive Resume
-   Apply professional styling and templates
-   Export as PDF for applications

## JSON Resume Features

### Role-Specific Customization

The system automatically customizes resumes based on role type:

-   **Frontend**: Emphasizes React, Vue.js, TypeScript skills
-   **Backend**: Highlights Python, databases, API development
-   **Full-Stack**: Balanced frontend and backend skills
-   **DevOps**: Focuses on Docker, cloud, infrastructure
-   **Data**: Emphasizes analytics, ML, data processing

### Section Management

```bash
# Hide sections not relevant to specific roles
python tools/scripts/json-resume-manager.py --company "StartupCorp" --hide "interests" "volunteer"

# Show additional sections for senior roles
python tools/scripts/json-resume-manager.py --company "BigTech" --show "publications" "awards"
```

### Keyword Optimization

```bash
# Add job-specific keywords to skills
python tools/scripts/json-resume-manager.py \
  --company "CloudCorp" \
  --keywords "AWS" "Kubernetes" "Microservices"
```

## Available Tools

### JSON Resume Manager

```bash
python tools/scripts/json-resume-manager.py [OPTIONS]

Options:
  --company TEXT          Company name [required]
  --role TEXT            Role focus (frontend, backend, fullstack, devops, data)
  --output TEXT          Output file path
  --hide TEXT            Sections to hide
  --show TEXT            Sections to show
  --keywords TEXT        Job keywords to emphasize
  --validate TEXT        Validate JSON file
  --list-sections        List all available sections
```

### CUID2 ID Fixer

```bash
python tools/scripts/fix-cuid2-ids.py
```

Fixes CUID2 validation errors in resume JSON files.

### Application Creator

```bash
./create-application.sh CompanyName [role-type]
```

Creates complete application structure with role-optimized JSON resume.

## Documentation

-   **[JSON Resume Guide](templates/resumes/json-resume-guide.md)**: Complete guide to JSON resume system
-   **[Template Rules](templates/cover-letters/tailoring-rules.md)**: Cover letter customization
-   **[Skills Library](templates/resumes/skills-library/)**: Organized skill data

## Best Practices

### JSON Resume Workflow

-   Use base-resume.json as single source of truth
-   Generate job-specific copies for applications
-   Validate JSON before importing to platforms
-   Test different templates for optimal presentation
-   Keep keywords current with job requirements

### Cover Letter Workflow

-   Keep markdown simple and readable
-   Focus on content quality over formatting
-   Use company-specific language and insights
-   Maintain consistency with resume messaging
-   Ensure easy copy/paste for online forms

## Examples

### Generate Resume for Frontend Role

```bash
python tools/scripts/json-resume-manager.py \
  --company "ReactCorp" \
  --role "frontend" \
  --keywords "React" "TypeScript" "Tailwind"
```

### Create Data Science Resume

```bash
python tools/scripts/json-resume-manager.py \
  --company "DataScience Inc" \
  --role "data" \
  --hide "interests" "volunteer" \
  --keywords "Python" "Pandas" "Machine Learning"
```

### Validate JSON Resume

```bash
python tools/scripts/json-resume-manager.py --validate applications/active/TechCorp/documents/resume.json
```

### Create New Application

```bash
./create-application.sh "TechCorp" "backend"
```

---

The modern JSON-based system provides streamlined document creation with professional output while maintaining complete customization control for each application.
