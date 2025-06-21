#!/bin/bash

# Script to create a new job application folder structure

# Check if company name is provided
if [ -z "$1" ]; then
  echo "Error: Please provide a company name."
  echo "Usage: $0 <company-name>"
  exit 1
fi

COMPANY_NAME=$1
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
mkdir -p "$COMPANY_DIR/interview"
mkdir -p "output/$COMPANY_NAME"

# Copy templates
echo "Copying templates..."

# Copy base resume
cp "$TEMPLATE_DIR/resumes/base-resume.md" "$COMPANY_DIR/documents/resume.md"

# Create a basic cover letter template
cat > "$COMPANY_DIR/documents/cover-letter.md" << 'EOF'
# Cover Letter for [Company Name] - [Position]

## Header
Yushi Cui  
Auckland, New Zealand  
realYushi@gmail.com  
https://linkedin.com/in/yushi-cui-6043aa285  
https://github.com/realYushi  

[Date]

[Hiring Manager Name]  
[Company Name]  
[Company Address]  

## Letter Content

Dear [Hiring Manager/Team],

[Opening paragraph - mention the position and how you found it]

[Body paragraph 1 - why you're interested in the company]

[Body paragraph 2 - your relevant experience and skills]

[Body paragraph 3 - what you can contribute]

[Closing paragraph - next steps]

Kind regards,  
Yushi Cui
EOF

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


## Products & Services


## Recent News & Achievements


## Company Culture


## Notable Leadership

EOF

cat > "$COMPANY_DIR/company-research/culture-notes.md" << 'EOF'
# Culture Notes: [Company Name]

## Work Environment


## Company Values in Practice


## Employee Reviews & Insights


## Benefits & Perks


## Remote/Hybrid Policy


## Growth Opportunities

EOF

cat > "$COMPANY_DIR/company-research/key-people.md" << 'EOF'
# Key People: [Company Name]

## Hiring Manager/Contact


## Team Leadership


## Company Leadership


## Notable Team Members

EOF

cat > "$COMPANY_DIR/company-research/application-strategy.md" << 'EOF'
# Application Strategy: [Company Name]

## Key Points to Emphasize


## Skills to Highlight


## Company-Specific Keywords


## Potential Challenges/Gaps


## Follow-up Strategy

EOF

cat > "$COMPANY_DIR/company-research/interview-preparation.md" << 'EOF'
# Interview Preparation: [Company Name]

## Company Research Summary


## Technical Topics to Review


## Behavioral Questions Preparation


## Questions to Ask Them


## Project Examples to Discuss

EOF

# Create job details files
cat > "$COMPANY_DIR/job-details/job-description.md" << 'EOF'
# Job Description: [Position] at [Company Name]

## Original Job Posting
[Paste the full job description here]

## Key Requirements
### Technical Skills


### Soft Skills


### Experience Level


## Nice to Have


## Compensation & Benefits

EOF

cp "$TEMPLATE_DIR/analysis/requirements-analysis-template.md" "$COMPANY_DIR/job-details/requirements-analysis.md"
cp "$TEMPLATE_DIR/analysis/matching-skills-template.md" "$COMPANY_DIR/job-details/matching-skills.md"

# Create interview preparation files
cat > "$COMPANY_DIR/interview/preparation-notes.md" << 'EOF'
# Interview Preparation Notes: [Company Name]

## Research Summary


## Technical Preparation


## Behavioral Questions


## Project Discussions


## Questions for Them

EOF

cat > "$COMPANY_DIR/interview/questions-to-ask.md" << 'EOF'
# Questions to Ask: [Company Name]

## About the Role


## About the Team


## About the Company


## About Growth & Development

EOF

echo "Application structure for $COMPANY_NAME created successfully!"
echo "Directory structure:"
echo "  $COMPANY_DIR/"
echo "  ├── company-research/"
echo "  │   ├── company-profile.md"
echo "  │   ├── culture-notes.md"
echo "  │   ├── key-people.md"
echo "  │   ├── application-strategy.md"
echo "  │   └── interview-preparation.md"
echo "  ├── documents/"
echo "  │   ├── cover-letter.md"
echo "  │   └── resume.md"
echo "  ├── job-details/"
echo "  │   ├── job-description.md"
echo "  │   ├── requirements-analysis.md"
echo "  │   └── matching-skills.md"
echo "  └── interview/"
echo "      ├── preparation-notes.md"
echo "      └── questions-to-ask.md"
echo ""
echo "Next steps:"
echo "1. Add the job description to $COMPANY_DIR/job-details/job-description.md"
echo "2. Research the company and update the company profile and culture notes"
echo "3. Analyze job requirements and update your resume and cover letter"
echo ""
echo "Good luck with your application!" 