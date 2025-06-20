#!/bin/bash

# Script to create a new job application folder structure

# Check if company name is provided
if [ -z "$1" ]; then
  echo "Error: Please provide a company name."
  echo "Usage: $0 <company-name>"
  exit 1
fi

COMPANY_NAME=$1
COMPANY_DIR="../../applications/active/$COMPANY_NAME"
TEMPLATE_DIR="../../templates"

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
mkdir -p "output/$COMPANY_NAME"

# Copy templates
echo "Copying templates..."

cp $TEMPLATE_DIR/resumes/base-resume.md "$COMPANY_DIR/documents/resume.md"
cp $TEMPLATE_DIR/formatting/markdown-templates/cover-letter.md "$COMPANY_DIR/documents/cover-letter.md"

# Create company research files
touch "$COMPANY_DIR/company-research/company-profile.md"
touch "$COMPANY_DIR/company-research/culture-notes.md"
touch "$COMPANY_DIR/company-research/key-people.md"

# Create job details files
touch "$COMPANY_DIR/job-details/job-description.md"
cp $TEMPLATE_DIR/resumes/skills-library/technical-skills.md "$COMPANY_DIR/job-details/requirements-analysis.md"
cp $TEMPLATE_DIR/resumes/skills-library/soft-skills.md "$COMPANY_DIR/job-details/matching-skills.md"

echo "Application structure for $COMPANY_NAME created successfully!"
echo "Next steps:"
echo "1. Add the job description to $COMPANY_DIR/job-details/job-description.md"
echo "2. Research the company and update the company profile and culture notes"
echo "3. Analyze job requirements and update your resume and cover letter"
echo ""
echo "Good luck with your application!" 