#!/bin/bash

# Script to create a new job application folder structure for JSON-based workflow

# Check if company name is provided
if [ -z "$1" ]; then
  echo "Error: Please provide a company name."
  echo "Usage: $0 <company-name> [role-type]"
  echo "Role types: frontend, backend, fullstack, devops, data"
  exit 1
fi

COMPANY_NAME=$1
ROLE_TYPE=${2:-"fullstack"}  # Default to fullstack if not specified
COMPANY_DIR="applications/active/$COMPANY_NAME"
TEMPLATE_DIR="templates"

# Check if company directory already exists
if [ -d "$COMPANY_DIR" ]; then
  echo "Error: Application for $COMPANY_NAME already exists."
  exit 1
fi

# Create directory structure
echo "Creating application structure for $COMPANY_NAME..."
mkdir -p "$COMPANY_DIR/company-research"
mkdir -p "$COMPANY_DIR/job-details"
mkdir -p "$COMPANY_DIR/documents"

# Copy templates
echo "Copying templates..."

# Generate JSON resume for specific role
echo "Generating JSON resume for $ROLE_TYPE role..."
python tools/scripts/json-resume-manager.py --company "$COMPANY_NAME" --role "$ROLE_TYPE" --output "$COMPANY_DIR/documents/resume.json"

# Copy standard cover letter template
cp "$TEMPLATE_DIR/cover-letters/templates/standard.md" "$COMPANY_DIR/documents/cover-letter.md"

# Create company research files with basic templates
cat > "$COMPANY_DIR/company-research/company-profile.md" << 'EOF'
# Company Profile: [Company Name]

## Basic Information
- **Company Name**: 
- **Industry**: 
- **Size**: 
- **Founded**: 
- **Headquarters**: 
- **Website**: 

## Mission & Values

## Business Model

## Recent News & Achievements

## Key Technologies

## Competitive Advantages
EOF

cat > "$COMPANY_DIR/company-research/culture-notes.md" << 'EOF'
# Culture & Work Environment: [Company Name]

## Work Environment
- **Remote/Hybrid/Office**: 
- **Team Size**: 
- **Work Hours**: 

## Company Culture
- **Values**: 
- **Communication Style**: 
- **Collaboration Approach**: 

## Learning & Development
- **Growth Opportunities**: 
- **Learning Culture**: 
- **Career Paths**: 

## Diversity & Inclusion

## Employee Benefits
EOF

cat > "$COMPANY_DIR/company-research/key-people.md" << 'EOF'
# Key People: [Company Name]

## Leadership Team
- **CEO**: 
- **CTO**: 
- **Head of Engineering**: 

## Hiring Manager
- **Name**: 
- **Title**: 
- **Background**: 

## Team Members
- **Potential Teammates**: 
- **Team Lead**: 

## Company Alumni
- **Notable Alumni**: 
- **Career Paths**: 
EOF

# Create job details templates
cat > "$COMPANY_DIR/job-details/job-description.md" << 'EOF'
# Job Description: [Position Title] at [Company Name]

## Position Overview
- **Title**: 
- **Department**: 
- **Location**: 
- **Type**: Full-time/Part-time/Contract

## Responsibilities

## Requirements
### Must-Have
### Preferred
### Nice-to-Have

## Benefits & Compensation

## Application Deadline
EOF

cp "$TEMPLATE_DIR/analysis/requirements-analysis-template.md" "$COMPANY_DIR/job-details/requirements-analysis.md"
cp "$TEMPLATE_DIR/analysis/matching-skills-template.md" "$COMPANY_DIR/job-details/matching-skills.md"

echo ""
echo "✅ Application structure created successfully!"
echo ""
echo "📁 Created directories:"
echo "  - $COMPANY_DIR/company-research/"
echo "  - $COMPANY_DIR/job-details/"
echo "  - $COMPANY_DIR/documents/"
echo ""
echo "📄 Generated files:"
echo "  - JSON resume: $COMPANY_DIR/documents/resume.json (optimized for $ROLE_TYPE)"
echo "  - Cover letter template: $COMPANY_DIR/documents/cover-letter.md"
echo "  - Company research templates"
echo "  - Job analysis templates"
echo ""
echo "🚀 Next steps:"
echo "  1. Fill in job description: $COMPANY_DIR/job-details/job-description.md"
echo "  2. Research company: $COMPANY_DIR/company-research/"
echo "  3. Analyze job requirements and customize documents"
echo "  4. Import JSON resume to Reactive Resume for final PDF" 