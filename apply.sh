#!/bin/bash

# Simplified Application Script
# Creates complete application package with research and documents

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: $0 <company-name> <role-type> [job-description-file]"
    echo ""
    echo "Role types: frontend, backend, fullstack, data, devops"
    echo ""
    echo "Examples:"
    echo "  $0 \"TechCorp\" \"frontend\"                    # Interactive mode"
    echo "  $0 \"DataCorp\" \"data\" job-description.txt  # From file"
    echo ""
    exit 1
}

# Function to log messages
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1" >&2
    exit 1
}

# Validate arguments
if [[ $# -lt 2 ]]; then
    usage
fi

COMPANY_NAME="$1"
ROLE_TYPE="$2"
JOB_DESC_FILE="${3:-}"

# Validate role type
VALID_ROLES=("frontend" "backend" "fullstack" "data" "devops")
if [[ ! " ${VALID_ROLES[@]} " =~ " ${ROLE_TYPE} " ]]; then
    error "Invalid role type: $ROLE_TYPE. Valid options: ${VALID_ROLES[*]}"
fi

# Setup paths
COMPANY_DIR="applications/active/$COMPANY_NAME"
RESEARCH_DIR="$COMPANY_DIR/research"
DOCUMENTS_DIR="$COMPANY_DIR/documents"

# Check if application already exists
if [[ -d "$COMPANY_DIR" ]]; then
    error "Application for '$COMPANY_NAME' already exists at $COMPANY_DIR"
fi

# Get job description
JOB_DESCRIPTION=""
if [[ -n "$JOB_DESC_FILE" ]]; then
    if [[ ! -f "$JOB_DESC_FILE" ]]; then
        error "Job description file not found: $JOB_DESC_FILE"
    fi
    JOB_DESCRIPTION=$(cat "$JOB_DESC_FILE")
else
    # Interactive mode
    echo "Paste job description (Ctrl+D when done):"
    JOB_DESCRIPTION=$(cat)
fi

if [[ -z "$JOB_DESCRIPTION" ]]; then
    error "Job description cannot be empty"
fi

log "Creating application for $COMPANY_NAME ($ROLE_TYPE role)"

# Create directory structure
log "Setting up directory structure..."
mkdir -p "$RESEARCH_DIR"
mkdir -p "$DOCUMENTS_DIR"

# Save job description
echo "$JOB_DESCRIPTION" > "$RESEARCH_DIR/job-description.md"
log "Job description saved to $RESEARCH_DIR/job-description.md"

# Generate research and analysis
log "Generating company research and job analysis..."
cat > "$RESEARCH_DIR/analysis.md" << EOF
# Research & Analysis: $COMPANY_NAME

## Job Description
$(cat "$RESEARCH_DIR/job-description.md")

## Company Research
*Research to be completed by agent*

## Job Requirements Analysis
*Analysis to be completed by agent*

## Strategic Positioning
*Strategy to be completed by agent*

Last updated: $(date)
EOF

# Generate resume
log "Generating role-optimized resume..."
python3 tools/scripts/json-resume-manager.py --company "$COMPANY_NAME" --role "$ROLE_TYPE" --output "$DOCUMENTS_DIR/resume.json"

# Generate cover letter template
log "Creating cover letter template..."
cat > "$DOCUMENTS_DIR/cover-letter.md" << EOF
# Cover Letter: $ROLE_TYPE Position at $COMPANY_NAME

*Cover letter to be customized based on research and job analysis*

## Key Points to Address:
- Company-specific insights from research
- Job requirements and skills matching
- Strategic positioning and value proposition

Draft created: $(date)
EOF

# Update application tracker
log "Updating application tracker..."
python3 << EOF
import json
import sys
from datetime import datetime

# Read current tracker
try:
    with open('tools/config/application-tracker.json', 'r') as f:
        tracker = json.load(f)
except FileNotFoundError:
    error("Application tracker not found")

# Add new application
new_application = {
    "company": "$COMPANY_NAME",
    "position": "$ROLE_TYPE Position",
    "date_applied": datetime.now().strftime('%Y-%m-%d'),
    "status": "In Progress",
    "priority": "High"
}

tracker["applications"]["active"].append(new_application)

# Update metadata
tracker["meta"]["last_updated"] = datetime.now().strftime('%Y-%m-%d')

# Save tracker
with open('tools/config/application-tracker.json', 'w') as f:
    json.dump(tracker, f, indent=2)

print("Application tracker updated")
EOF

# Summary
log "✅ Application package created successfully!"
echo ""
echo "📁 Created directories:"
echo "  - $RESEARCH_DIR/ (research and analysis)"
echo "  - $DOCUMENTS_DIR/ (resume and cover letter)"
echo ""
echo "📄 Generated files:"
echo "  - Job description: $RESEARCH_DIR/job-description.md"
echo "  - Research analysis: $RESEARCH_DIR/analysis.md"
echo "  - Resume: $DOCUMENTS_DIR/resume.json"
echo "  - Cover letter: $DOCUMENTS_DIR/cover-letter.md"
echo ""
echo "🚀 Next steps:"
echo "  1. Complete company research and job analysis in $RESEARCH_DIR/analysis.md"
echo "  2. Customize cover letter based on research findings"
echo "  3. Import resume to Reactive Resume for PDF generation"
echo "  4. Submit application through company portal"
echo ""
echo "⏱️  Expected total time: 30 minutes"
echo ""