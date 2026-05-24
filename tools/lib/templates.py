"""Render application templates from on-disk markdown files."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .paths import base_resume_path, templates_dir


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


def _strip_html(text: str) -> str:
    """Remove simple HTML tags from stored resume content."""
    return re.sub(r"<[^>]+>", "", text).replace("&nbsp;", " ").strip()


def _candidate_current_sentence(root: Path | None = None) -> str:
    """Return a verified one-sentence current-role summary."""
    fallback = (
        "I’m currently a full-stack product engineer at GrowLab Technologies, "
        "building internal tools, client applications, and AI-powered workflows."
    )
    try:
        doc = json.loads(base_resume_path(root).read_text())
        summary = _strip_html(doc.get("summary", {}).get("content", ""))
        first = re.split(r"(?<=[.!?])\s+", summary.strip())[0].strip()
        if not first:
            return fallback
        if first.startswith("I"):
            return first
        return f"I’m currently a {first[0].lower()}{first[1:]}"
    except Exception:
        return fallback


def _specific_reason(position: str, keywords: tuple[str, ...], job_text: str) -> str:
    """Build a concise, role-specific why-this-role sentence."""
    preferred = [
        kw for kw in keywords if kw and kw.casefold() not in {"ownership", "scrum team"}
    ]
    focus = " and ".join(preferred[:2]) if len(preferred) >= 2 else (preferred[0] if preferred else position)
    reason = f"the role’s focus on {focus} lines up well with the kind of product and engineering work I enjoy"
    if "airport" in job_text.casefold():
        reason += ", especially in software that supports real airport operations"
    return reason


def _recent_example(keywords: tuple[str, ...]) -> str:
    """Choose a verified recent example that roughly matches the role focus."""
    lowered = [kw.casefold() for kw in keywords]
    if any(token in kw for kw in lowered for token in (".net", "c#", "aws", "kubernetes")):
        return (
            "I recently built a personal full-stack task management application "
            "with a React and TypeScript frontend and a .NET Core backend, "
            "deployed on Azure with GitHub Actions CI/CD."
        )
    if any(token in kw for kw in lowered for token in ("ai", "llm", "copilot", "agent")):
        return (
            "I recently helped build a full-stack coding agent platform using "
            "the OpenAI Agent SDK and shaped the QA and review workflow around it."
        )
    return (
        "I recently shipped a customer-facing RAG chatbot for a client project, "
        "built as a Next.js app with semantic search over product documentation."
    )


def _cold_email_style(source: str | None, url: str | None) -> str:
    """Infer whether outreach should read like a recruiter or hiring-manager note."""
    recruiter_sources = {
        "seek",
        "linkedin",
        "hiringcafe",
        "workingnomads",
        "wellfound",
        "weworkremotely",
    }
    recruiter_hosts = (
        "bamboohr.com",
        "greenhouse.io",
        "lever.co",
        "workday.com",
        "smartrecruiters.com",
        "ashbyhq.com",
        "jobvite.com",
    )
    if source in recruiter_sources:
        return "recruiter"
    if url and any(host in url for host in recruiter_hosts):
        return "recruiter"
    return "hiring-manager"


def _cold_email_cta(style: str) -> str:
    """Return the closing ask for the chosen outreach style."""
    if style == "recruiter":
        return (
            "If you’re the right person to chat with, I’d be grateful for a quick "
            "conversation, or happy to be pointed to whoever handles hiring for this role."
        )
    return (
        "If this role sits with you or someone on your team, I’d be glad to share a few "
        "relevant examples of my work and learn more about what you need."
    )


def _cold_email_notes(style: str) -> str:
    """Return tailoring notes for the chosen outreach style."""
    if style == "recruiter":
        return (
            "- Replace `[First Name]` with the actual contact if you have it.\n"
            "- Swap `[LinkedIn / Portfolio]` for the best link for this outreach.\n"
            "- Keep the generated proof point truthful; edit for tone, not invention.\n"
            "- This draft is recruiter-style: short, easy to route, and low-pressure."
        )
    return (
        "- Replace `[First Name]` with the actual contact if you have it.\n"
        "- Swap `[LinkedIn / Portfolio]` for the best link for this outreach.\n"
        "- Keep the generated proof point truthful; edit for tone, not invention.\n"
        "- This draft is hiring-manager-style: slightly more direct about fit and team contribution."
    )


def render_cold_email(
    company: str,
    position: str,
    root: Path | None = None,
    keywords: tuple[str, ...] = (),
    job_text: str = "",
    source: str | None = None,
    url: str | None = None,
) -> str:
    """Render templates/cold-email.md into a job-specific outreach draft."""
    text = _read("cold-email.md", root)
    style = _cold_email_style(source, url)
    rendered = (
        text.replace("[Company Name]", company)
        .replace("[Job Title]", position)
        .replace("[YYYY-MM-DD]", date.today().isoformat())
        .replace("[Specific Reason]", _specific_reason(position, keywords, job_text))
        .replace("[Current Role]", _candidate_current_sentence(root))
        .replace("[Relevant Example]", _recent_example(keywords))
        .replace("[CTA]", _cold_email_cta(style))
        .replace("[Style Notes]", _cold_email_notes(style))
    )
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
    return rendered + context_block


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
