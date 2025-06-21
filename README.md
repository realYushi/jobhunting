# Job Hunting Workflow System

An AI-assisted workflow for systematic job applications: company research → job analysis → document creation → LaTeX formatting.

## Overview

This system provides a structured approach to job applications with AI assistance, ensuring consistent quality and comprehensive preparation for each opportunity.

## Project Structure

```
jobhunting/
├── applications/                # All job applications
│   ├── active/                  # Current applications in progress
│   │   └── {company-name}/      # Folder for each company
│   │       ├── company-research/    # Company information
│   │       │   ├── company-profile.md
│   │       │   ├── culture-notes.md
│   │       │   ├── key-people.md
│   │       │   ├── application-strategy.md
│   │       │   └── interview-preparation.md
│   │       ├── documents/           # Application documents
│   │       │   ├── cover-letter.md
│   │       │   └── resume.md
│   │       ├── job-details/         # Job information
│   │       │   ├── job-description.md
│   │       │   ├── matching-skills.md
│   │       │   └── requirements-analysis.md
│   │       └── interview/           # Interview preparation
│   │           ├── preparation-notes.md
│   │           └── questions-to-ask.md
│   ├── archived/               # Past applications (rejected)
│   └── completed/              # Completed application cycles
├── output/                     # Generated LaTeX files for Overleaf
│   └── {company-name}/
├── templates/                  # Reusable templates
│   ├── analysis/               # Job analysis templates
│   │   ├── requirements-analysis-template.md
│   │   └── matching-skills-template.md
│   ├── cover-letters/
│   │   ├── tailoring-rules.md
│   │   └── templates/
│   │       ├── achievement-focused.md
│   │       ├── innovation-focused.md
│   │       ├── leadership-focused.md
│   │       ├── problem-solving-focused.md
│   │       └── standard.md
│   ├── formatting/
│   │   ├── awesome-cv.cls       # LaTeX class file for resume styling
│   │   ├── cover-letter.tex
│   │   └── resume.tex
│   └── resumes/
│       ├── base-resume.md
│       └── skills-library/
│           ├── soft-skills.md
│           └── technical-skills.md
└── tools/                      # Scripts and utilities
    ├── config/
    │   └── application-tracker.json
    └── scripts/
        ├── create-application.sh
        └── generate-pdfs.sh
```

## Workflow Steps

### 1. Company Research Analysis

-   Analyze company profile, culture, and key people
-   Extract mission, values, work environment insights
-   Identify company positioning and recent achievements
-   Generate application strategy document

### 2. Job Description Analysis

-   Extract technical and soft skills requirements
-   Compare requirements to candidate skills library
-   Identify matching skills and potential gaps
-   Generate strategic insights for tailored applications

### 3. Document Creation

-   Create tailored cover letter using appropriate template
-   Customize resume highlighting relevant experience
-   Incorporate company-specific language and keywords

### 4. Document Formatting

-   Convert markdown documents to professional LaTeX format
-   Generate files ready for Overleaf upload
-   Apply consistent styling using awesome-cv.cls

## Getting Started

### Prerequisites

-   AI assistant with access to the rules system
-   Overleaf account for PDF generation
-   Basic understanding of markdown

### Setup

1. Clone or download this repository structure
2. Ensure all template files are in place
3. Review and customize the base resume and skills library
4. Set up your Overleaf account

### Creating a New Application

1. **Create Application Structure**

    ```bash
    ./tools/scripts/create-application.sh company-name
    ```

2. **Company Research**

    - Research the company and fill in `company-research/` files
    - Use AI command: "Analyze company profile and culture for [company-name]"

3. **Job Analysis**

    - Save job description to `job-details/job-description.md`
    - Use AI command: "Analyze job description for [company-name] [role-title]"

4. **Document Creation**

    - Use AI command: "Create cover letter for [company-name] [role-title]"
    - Use AI command: "Tailor resume for [company-name] [role-title]"

5. **LaTeX Generation**
    - Use AI command: "Generate LaTeX documents for [company-name]"
    - Upload generated `.tex` files and `awesome-cv.cls` to Overleaf

## AI Rules System

The system uses specialized AI rules for each workflow step:

-   **AI Agent Rules**: General workflow overview
-   **Company Research Analyzer**: Company profile and culture analysis
-   **Job Description Analyzer**: Systematic job requirement analysis
-   **Document Creation**: Cover letter and resume tailoring
-   **Document Formatting**: LaTeX conversion for Overleaf

## Templates

### Analysis Templates

-   **Requirements Analysis**: Structured job requirement breakdown
-   **Skills Matching**: Comprehensive skills assessment with scoring

### Cover Letter Templates

Choose based on company culture and role:

-   **Standard**: Traditional companies, formal environments
-   **Achievement-focused**: Results-driven companies, metrics roles
-   **Innovation-focused**: Tech startups, creative roles
-   **Leadership-focused**: Management roles, team positions
-   **Problem-solving-focused**: Consulting, engineering roles

### Resume Templates

-   **Base Resume**: Core resume structure and content
-   **Skills Library**: Technical and soft skills repository

## Key Features

### Systematic Analysis

-   Multi-layer job requirement extraction
-   Skills matching with percentage scores
-   Hidden requirement detection
-   Strategic keyword identification

### Template-Driven Consistency

-   Reusable templates ensure consistent output
-   Easy customization for different role types
-   Quality assurance checklists

### LaTeX Integration

-   Professional document formatting
-   Overleaf-ready output
-   Consistent branding across documents

### AI-Assisted Workflow

-   Intelligent analysis and recommendations
-   Company-specific customization
-   Application strategy generation

## Best Practices

### Research Phase

-   Gather comprehensive company information
-   Research key people and recent news
-   Understand company culture and values

### Analysis Phase

-   Be thorough in requirement extraction
-   Honestly assess skill matches and gaps
-   Identify specific examples and evidence

### Document Creation

-   Use appropriate templates for company culture
-   Incorporate company-specific language
-   Quantify achievements where possible

### Quality Assurance

-   Review all documents for accuracy
-   Ensure consistent messaging across documents
-   Test LaTeX compilation in Overleaf

## Commands Reference

### Company Research

-   "Analyze company profile and culture for [company-name]"
-   "Generate application strategy for [company-name]"
-   "Research key people at [company-name]"

### Job Analysis

-   "Analyze job description for [company-name] [role-title]"
-   "Generate comprehensive requirements analysis for [company-name]"
-   "Create skills matching report for [company-name] [role-title]"

### Document Creation

-   "Create cover letter for [company-name] [role-title]"
-   "Tailor resume for [company-name] [role-title]"
-   "Review and optimize documents for [company-name]"

### LaTeX Formatting

-   "Generate LaTeX documents for [company-name]"
-   "Prepare documents for Overleaf upload for [company-name]"
-   "Convert markdown to LaTeX for [company-name]"

## Troubleshooting

### Common Issues

-   **Missing Templates**: Ensure all template files are present
-   **LaTeX Errors**: Check special character escaping
-   **Overleaf Upload**: Include awesome-cv.cls file
-   **Inconsistent Formatting**: Use quality assurance checklists

### Support

-   Review AI rules for detailed guidance
-   Check template files for proper formatting
-   Verify project structure matches documentation

## Contributing

### Template Updates

-   Modify templates based on experience
-   Test changes with sample applications
-   Update documentation as needed

### Rule Improvements

-   Refine AI rules based on usage
-   Add new analysis frameworks
-   Enhance quality assurance processes

## License

This project is for personal use in job hunting activities.

---

**Happy Job Hunting!** 🚀

Remember: Quality over quantity. This system is designed to help you create thoughtful, well-researched applications that stand out from generic submissions.
