#!/bin/bash

# Script to generate PDF files from markdown using pandoc

# Check if company name is provided
if [ -z "$1" ]; then
  echo "Error: Please provide a company name."
  echo "Usage: $0 <company-name>"
  exit 1
fi

COMPANY_NAME=$1
COMPANY_DIR="applications/active/$COMPANY_NAME"
OUTPUT_DIR="output/$COMPANY_NAME"

# Check if company directory exists
if [ ! -d "$COMPANY_DIR" ]; then
  echo "Error: Application for $COMPANY_NAME does not exist."
  exit 1
fi

# Check if pandoc is installed
if ! command -v pandoc &> /dev/null; then
  echo "Error: pandoc is not installed. Please install it first."
  exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "Generating PDF files for $COMPANY_NAME application..."

# Generate resume PDF
if [ -f "$COMPANY_DIR/documents/resume.md" ]; then
  echo "Generating resume PDF..."
  pandoc "$COMPANY_DIR/documents/resume.md" \
    -o "$OUTPUT_DIR/resume.pdf" \
    --template=templates/formatting/resume.tex \
    --pdf-engine=xelatex
  
  if [ $? -eq 0 ]; then
    echo "Resume PDF generated successfully: $OUTPUT_DIR/resume.pdf"
  else
    echo "Error generating resume PDF."
  fi
else
  echo "Warning: Resume markdown file not found."
fi

# Generate cover letter PDF
if [ -f "$COMPANY_DIR/documents/cover-letter.md" ]; then
  echo "Generating cover letter PDF..."
  pandoc "$COMPANY_DIR/documents/cover-letter.md" \
    -o "$OUTPUT_DIR/cover-letter.pdf" \
    --template=templates/formatting/cover-letter.tex \
    --pdf-engine=xelatex
  
  if [ $? -eq 0 ]; then
    echo "Cover letter PDF generated successfully: $OUTPUT_DIR/cover-letter.pdf"
  else
    echo "Error generating cover letter PDF."
  fi
else
  echo "Warning: Cover letter markdown file not found."
fi

# Create application package zip
echo "Creating application package zip..."
zip -j "$OUTPUT_DIR/application-package.zip" \
  "$OUTPUT_DIR/resume.pdf" \
  "$OUTPUT_DIR/cover-letter.pdf" \
  2>/dev/null

if [ $? -eq 0 ]; then
  echo "Application package created successfully: $OUTPUT_DIR/application-package.zip"
else
  echo "Error creating application package."
fi

echo "PDF generation complete!" 