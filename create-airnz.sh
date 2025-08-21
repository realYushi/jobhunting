#!/bin/bash

# Create Air New Zealand application structure
COMPANY_NAME="Air New Zealand"
COMPANY_DIR="applications/active/$COMPANY_NAME"

# Create directory structure
mkdir -p "$COMPANY_DIR/company-research"
mkdir -p "$COMPANY_DIR/job-details"  
mkdir -p "$COMPANY_DIR/documents"
mkdir -p "$COMPANY_DIR/interview"

# Create gitkeep files
touch "$COMPANY_DIR/interview/.gitkeep"

echo "✅ Air New Zealand application structure created!"