# JSON-Based Resume System Guide

## Overview

This system uses JSON as the primary data source for building resumes, compatible with Reactive Resume and other modern CV builders. The JSON format provides a structured, customizable approach to resume generation.

## File Structure

```
templates/resumes/
├── base-resume.json          # Master resume with all your data
├── json-resume-guide.md      # This guide
├── base-resume.md           # Legacy markdown (for reference)
└── skills-library/          # Skill data organized by category
    ├── technical-skills.md
    └── soft-skills.md
```

## JSON Resume Schema

### Core Structure

```json
{
  "basics": { ... },           # Personal information
  "sections": { ... },         # All resume content
  "metadata": { ... }          # Formatting and layout
}
```

### ID Requirements

⚠️ **Important**: Reactive Resume has specific ID format requirements:

#### Section IDs (Literal Strings)

Section IDs must be literal strings matching the section name:

-   `"summary"` for summary section
-   `"experience"` for experience section
-   `"skills"` for skills section
-   etc.

#### Item IDs (CUID2 Format)

Item IDs within sections must use CUID2 format (24 characters, lowercase + digits):

-   `t55obp1c6hmlbcsqca525ouh`
-   `289ox84qico7rah28sz2shhz`
-   `0ee4lludojq6q52z9bl2ae9c`

#### Invalid Item IDs:

-   `halo_systems` (contains underscore)
-   `azure_ai_fundamentals` (contains underscore)
-   `github_profile` (contains underscore)

#### Fixing ID Issues:

If you encounter ID validation errors, run:

```bash
python tools/scripts/fix-cuid2-ids.py
```

This script automatically:

-   Sets section IDs to literal strings
-   Updates item IDs to proper CUID2 format

### Section Types

#### 1. **basics** - Personal Information

-   `name`: Full name
-   `headline`: Professional title
-   `email`: Contact email
-   `location`: Current location
-   `customFields`: Additional info (visa status, etc.)
-   `picture`: Profile photo settings

#### 2. **sections** - Content Sections

-   `summary`: Professional summary (HTML content)
-   `experience`: Work experience items
-   `education`: Educational background
-   `projects`: Personal/professional projects
-   `skills`: Technical and soft skills
-   `certifications`: Professional certifications
-   `languages`: Language proficiencies
-   `interests`: Personal interests
-   `profiles`: Social media/professional profiles

#### 3. **metadata** - Formatting

-   `template`: Visual template (ditto, azurill, etc.)
-   `layout`: Section arrangement
-   `theme`: Colors and styling
-   `typography`: Font settings

## Customization Workflow

### For Job Applications

1. **Copy Base Resume**

    ```bash
    cp templates/resumes/base-resume.json applications/active/{company}/documents/resume.json
    ```

2. **Customize for Job**

    - Reorder sections in `metadata.layout`
    - Hide/show sections with `visible` property
    - Modify `keywords` to match job requirements
    - Adjust `summary` content for role focus

3. **Section Visibility**
    ```json
    "certifications": {
      "visible": true,  // Show for tech roles
      "visible": false  // Hide for non-tech roles
    }
    ```

### Skill Customization

#### Highlighting Relevant Skills

```json
"skills": {
  "items": [
    {
      "name": "Frontend Development",
      "level": 5,
      "keywords": ["React", "Vue.js", "TypeScript"],
      "visible": true  // Show for frontend roles
    },
    {
      "name": "Backend Development",
      "level": 4,
      "keywords": ["Python", ".NET Core", "Node.js"],
      "visible": false  // Hide for frontend-only roles
    }
  ]
}
```

#### Reordering Skills by Relevance

```json
"metadata": {
  "layout": [
    [
      ["profiles", "summary", "experience", "projects"],
      ["skills", "education", "certifications"]  // Skills first for tech roles
    ]
  ]
}
```

## Content Guidelines

### HTML Formatting

-   Use `<p>` tags for paragraphs
-   Use `<br>` for line breaks
-   Keep formatting minimal and clean

### Bullet Points

```json
"summary": "<p>• First achievement<br>• Second achievement<br>• Third achievement</p>"
```

### Keywords Strategy

-   Add relevant keywords to skill items
-   Match job description terminology
-   Include both technical and soft skills

## Templates and Themes

### Available Templates

-   **ditto**: Clean, modern layout
-   **azurill**: Professional, traditional
-   **onyx**: Minimalist design

### Theme Customization

```json
"theme": {
  "background": "#ffffff",
  "text": "#000000",
  "primary": "#dc2626"  // Accent color
}
```

## Integration with Reactive Resume

### Import Process

1. Open Reactive Resume
2. Create new resume or open existing
3. Go to Import section
4. Upload your JSON file
5. Review and adjust as needed

### Export Options

-   PDF generation
-   Multiple format support
-   Custom styling options

## Automation Scripts

### Future Enhancements

-   Script to generate job-specific resumes
-   Keyword matching against job descriptions
-   Automated section reordering
-   Skills relevance scoring

## Best Practices

### 1. Content Management

-   Keep `base-resume.json` as master source
-   Create job-specific copies for applications
-   Use consistent formatting across sections

### 2. Skill Organization

-   Group skills by category
-   Use appropriate skill levels (1-5)
-   Include relevant keywords for each skill

### 3. Customization Strategy

-   Analyze job requirements first
-   Prioritize relevant sections
-   Adjust keywords and emphasis
-   Test different layouts

### 4. Version Control

-   Track changes to base resume
-   Save job-specific versions
-   Document successful customizations

## Troubleshooting

### Common Issues

1. **JSON Validation**: Use JSON validator before import
2. **HTML Formatting**: Keep HTML tags simple
3. **Section Visibility**: Check `visible` properties
4. **Layout Issues**: Verify `metadata.layout` structure

### Validation

```bash
# Check JSON syntax
cat resume.json | python -m json.tool
```

## Migration from Markdown

Your existing markdown resume has been converted to JSON format. The markdown files are kept for reference but JSON is now the primary format.

### Key Changes

-   Structured data instead of free text
-   Granular control over visibility
-   Better keyword management
-   Multiple output format support

This JSON-based system provides more flexibility and automation possibilities while maintaining compatibility with modern resume builders.
