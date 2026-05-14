"""Render application templates from on-disk markdown files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .paths import templates_dir


def _read(name: str, root: Path | None = None) -> str:
    return (templates_dir(root) / name).read_text()


def render_cover_letter(
    company: str,
    position: str,
    root: Path | None = None,
    keywords: tuple[str, ...] = (),
    job_text: str = "",
) -> str:
    """Render templates/cover-letter.md with the company, position, and date filled in."""
    text = _read("cover-letter.md", root)
    rendered = (
        text.replace("[Company Name]", company)
        .replace("[Job Title]", position)
        .replace("[YYYY-MM-DD]", date.today().isoformat())
    )
    if keywords or job_text:
        keyword_line = ", ".join(keywords) if keywords else "(none specified)"
        excerpt = job_text[:800]
        context_block = (
            "\n<!--\n"
            "Context for editing (auto-generated, remove before sending):\n"
            f"Strategic keywords: {keyword_line}\n"
            "Job description excerpt:\n"
            f"{excerpt}\n"
            "-->\n"
        )
        rendered = rendered + context_block
    return rendered


def render_analysis(
    company: str,
    position: str,
    job_text: str,
    keywords: tuple[str, ...],
    root: Path | None = None,
) -> str:
    """Render templates/analysis-template.md with company/role + an appended source excerpt.

    The template is structural — it contains bracketed prompts for human review.
    We replace the obvious header fields and append a Strategic Keywords block and
    a Source excerpt block so the file is immediately useful as a scaffold.
    """
    text = _read("analysis-template.md", root)
    text = text.replace("[Company]", company).replace("[Role Title]", position)

    keyword_text = (
        ", ".join(keywords) if keywords else "Review job description manually"
    )
    appendix = f"""

---

## Strategic Keywords (auto-seeded)

{keyword_text}

## Source Job Description Excerpt

```text
{job_text[:3000]}
```
"""
    return text + appendix
