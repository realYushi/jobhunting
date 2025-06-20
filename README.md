# Job Application Management System

A comprehensive system for managing job applications, tailoring resumes and cover letters, and tracking application status.

## Project Structure

```
- templates/
  - cover-letters/       # Cover letter templates and tailoring rules
  - resumes/             # Resume templates and content libraries
  - formatting/          # LaTeX and markdown templates for PDF generation

- applications/
  - active/              # Current job applications
  - completed/           # Completed applications with status
  - archived/            # Old applications organized by year

- output/                # Generated PDF documents
  - [company-name]/      # Company-specific output files

- tools/
  - scripts/             # Helper scripts
  - config/              # Configuration files
```

## Getting Started

1. Create a new job application:

    ```bash
    ./tools/scripts/create-application.sh company-name
    ```

2. Add the job description to:

    ```
    applications/active/company-name/job-details/job-description.md
    ```

3. Analyze the job description:

    ```bash
    ./tools/scripts/analyze-job-description.py company-name
    ```

4. Research the company and update:

    ```
    applications/active/company-name/company-research/company-profile.md
    applications/active/company-name/company-research/culture-notes.md
    applications/active/company-name/company-research/key-people.md
    ```

5. Tailor your resume and cover letter:

    ```
    applications/active/company-name/documents/resume.md
    applications/active/company-name/documents/cover-letter.md
    ```

6. Generate PDF documents:
    ```bash
    ./tools/scripts/generate-pdfs.sh company-name
    ```

## Requirements

-   Python 3.6+
-   Pandoc
-   LaTeX (XeLaTeX)
-   Zip (for packaging applications)

## Cover Letter Templates

Choose from different cover letter styles:

-   Achievement-focused
-   Innovation-focused
-   Leadership-focused
-   Problem-solving-focused
-   Standard

## Skills Libraries

Maintain libraries of your skills and achievements:

-   Technical skills
-   Soft skills
-   Professional achievements

## Application Tracking

Track your applications in `tools/config/application-tracker.json`
