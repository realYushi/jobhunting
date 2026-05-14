# JSON Resume Guide

## Structure

```json
{
  "basics": {},      // Name, headline, email, location, customFields
  "sections": {},    // summary, experience, education, projects, skills, certifications, languages, profiles, interests
  "metadata": {}     // template, layout, theme, typography
}
```

## ID Format Requirements (Reactive Resume)

**Section IDs** must be literal strings matching the section name: `"summary"`, `"experience"`, `"skills"`, etc.

**Item IDs** must be CUID2 format (24 chars, lowercase + digits):
- Valid: `t55obp1c6hmlbcsqca525ouh`
- Invalid: `halo_systems` (underscores not allowed)

Fix invalid IDs:
```bash
python3 tools/fix_cuid2_ids.py --input resume.json --output resume-fixed.json
```

## Customization for Job Applications

1. Copy `templates/base-resume.json` to application documents folder
2. Toggle sections with `"visible": true/false`
3. Reorder sections via `metadata.layout`
4. Update `keywords` arrays to match job description terminology
5. Adjust `summary` content for role focus

## Content Format

- Use HTML in content fields: `<p>`, `<br>` for formatting
- Bullet points: `<p>* First point<br>* Second point</p>`
- Keep formatting minimal

## Available Templates

`gengar` (default), `ditto`, `azurill`, `onyx`
