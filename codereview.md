Starting CodeRabbit review in plain text mode...

Connecting to review service
Setting up
Analyzing
Reviewing

============================================================================
File: applications/active/Emergency Q/company-research/key-people.md
Line: 56 to 133
Type: potential_issue

Prompt for AI Agent:
applications/active/Emergency Q/company-research/key-people.md lines 56-133: several plain URLs and email addresses (e.g., www.emergencyq.com and contact@emergencyq.co.nz) trigger markdownlint rule MD034; replace bare links/emails with Markdown link syntax or angle-bracket form (e.g.,  or Website, and  or contact@emergencyq.co.nz) wherever they appear to satisfy the linter and keep CI green.



============================================================================
File: applications/active/Emergency Q/job-details/matching-skills.md
Line: 13 to 29
Type: potential_issue

Prompt for AI Agent:
In applications/active/Emergency Q/job-details/matching-skills.md around lines 13 to 29, both Markdown tables are missing surrounding blank lines which violates MD058; insert one empty line immediately before and one empty line immediately after each table (i.e., add a blank line above the first table, a blank line below it, then a blank line above the second table and a blank line below it) so the tables are separated from surrounding text and satisfy the linter.



Review completed ✔
