"""Candidate profile + score-result helpers for the job-research pipeline.

Scoring itself is done by a Claude Code subagent reading
``tools/scoring-rubric.md`` (see the ``job-research`` skill). This module only
builds the candidate context the scrape-only dump carries, and provides the
``ScoreResult`` shape plus filter/sort helpers used by the packaging stage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

from .paths import base_resume_path, project_root


def _plain(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _section_items(resume: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return resume.get("sections", {}).get(name, {}).get("items", []) or []


def build_candidate_context(
    root: Path | None = None,
    resume: dict[str, Any] | None = None,
) -> str:
    """Return a compact, evidence-focused candidate summary for scoring."""
    root = root or project_root()
    if resume is None:
        resume = json.loads(base_resume_path(root).read_text())

    basics = resume.get("basics", {})
    parts: list[str] = []
    parts.append(f"Name: {basics.get('name', 'Yushi Cui')}")
    headline = basics.get("headline") or basics.get("label")
    if headline:
        parts.append(f"Headline: {headline}")
    if basics.get("location"):
        parts.append(f"Location: {basics['location']}")

    summary = _plain(resume.get("summary", {}).get("content", ""))
    if summary:
        parts.append(f"Summary: {summary}")

    skill_lines = []
    for item in _section_items(resume, "skills"):
        if item.get("hidden"):
            continue
        kws = item.get("keywords") or []
        if kws:
            skill_lines.append(f"- {item.get('name', 'Skills')}: {', '.join(kws)}")
    if skill_lines:
        parts.append("Skills:\n" + "\n".join(skill_lines))

    exp_lines = []
    for item in _section_items(resume, "experience")[:5]:
        if item.get("hidden"):
            continue
        desc = _plain(item.get("description", ""))
        exp_lines.append(
            f"- {item.get('position')} at {item.get('company')} ({item.get('period')}): {desc}"
        )
    if exp_lines:
        parts.append("Experience evidence:\n" + "\n".join(exp_lines))

    project_lines = []
    for item in _section_items(resume, "projects")[:6]:
        if item.get("hidden"):
            continue
        desc = _plain(item.get("description", ""))
        project_lines.append(f"- {item.get('name')} ({item.get('period')}): {desc}")
    if project_lines:
        parts.append("Project evidence:\n" + "\n".join(project_lines))

    edu_lines = []
    for item in _section_items(resume, "education")[:3]:
        if item.get("hidden"):
            continue
        edu_lines.append(
            f"- {item.get('degree') or item.get('description')} at {item.get('school')} "
            f"({item.get('period')}); grade: {item.get('grade', '')}"
        )
    if edu_lines:
        parts.append("Education:\n" + "\n".join(edu_lines))

    linkedin = root / "LinkedIn-CV-Profile.md"
    if linkedin.exists():
        parts.append("LinkedIn mirror excerpt:\n" + linkedin.read_text(errors="replace")[:5000])

    return "\n\n".join(parts)


@dataclass(frozen=True)
class ScoreResult:
    """Result of scoring a listing."""

    job_id: str
    source: str
    title: str
    company: str
    url: str | None
    score: int  # 0-100
    reason: str  # One-line explanation


def load_candidate_profile() -> dict[str, Any]:
    """Load the candidate's base resume."""
    resume_path = base_resume_path()
    with open(resume_path) as f:
        return json.load(f)


def candidate_summary(profile: dict[str, Any]) -> str:
    """Generate a text summary of the candidate's profile.

    The project uses Reactive Resume format (``sections.skills.items`` etc.),
    not legacy JSON Resume's top-level ``skills``/``work`` fields. Reuse the
    fit scorer's context builder so list scoring and JD scoring see the same
    evidence-rich candidate summary.
    """
    return build_candidate_context(resume=profile)


def sort_by_score(results: list[ScoreResult]) -> list[ScoreResult]:
    """Sort results by score descending."""
    return sorted(results, key=lambda r: r.score, reverse=True)
