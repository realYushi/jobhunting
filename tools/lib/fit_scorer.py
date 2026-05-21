"""LLM-first fit scoring for full job descriptions.

This module separates fit judgment from ATS keyword coverage. It uses the full
JD plus a structured summary of the candidate's Reactive Resume/LinkedIn mirror
when an Anthropic API key is available, and falls back to a conservative local
heuristic otherwise.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from html import unescape
from pathlib import Path
from typing import Any

try:
    from anthropic import Anthropic

    HAS_ANTHROPIC = True
except ImportError:  # pragma: no cover - depends on local env
    HAS_ANTHROPIC = False

from .paths import base_resume_path, project_root


@dataclass(frozen=True)
class FitScore:
    """Structured fit decision for a job description."""

    score: int
    verdict: str  # apply | maybe | skip
    confidence: str
    reason: str
    matched_requirements: list[str] = field(default_factory=list)
    partial_matches: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    role: str = "fullstack"
    ats_keywords: list[str] = field(default_factory=list)
    resume_keywords: list[str] = field(default_factory=list)
    cover_letter_angle: str = ""
    scorer: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ROLE_ALIASES = {
    "frontend": ("frontend", "front-end", "front end", "react", "ui", "ux"),
    "backend": ("backend", "back-end", "back end", "api", "server"),
    "fullstack": ("fullstack", "full-stack", "full stack"),
    "data": ("data", "analytics", "machine learning", "ml", "ai engineer"),
    "devops": ("devops", "sre", "platform", "infrastructure", "cloud"),
}


def _plain(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _section_items(resume: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return resume.get("sections", {}).get(name, {}).get("items", []) or []


def build_candidate_context(root: Path | None = None) -> str:
    """Return a compact, evidence-focused candidate summary for scoring."""
    root = root or project_root()
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
        # Include a bounded mirror so the LLM can use profile-only evidence, but
        # keep prompt size predictable.
        parts.append("LinkedIn mirror excerpt:\n" + linkedin.read_text(errors="replace")[:5000])

    return "\n\n".join(parts)


def infer_role(title: str, jd_text: str) -> str:
    text = f"{title}\n{jd_text}".lower()
    scores = {
        role: sum(1 for alias in aliases if alias in text)
        for role, aliases in ROLE_ALIASES.items()
    }
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "fullstack"


def _extract_keywords(jd_text: str) -> list[str]:
    known = [
        "React", "TypeScript", "JavaScript", "HTML5", "CSS3", "Responsive Design",
        "Redux", "React Hooks", "REST APIs", "Git", "Unit Testing",
        "Integration Testing", "Performance Optimization", "Node.js", "Next.js",
        "Vue.js", "Tailwind CSS", "SCSS", "Accessibility", "Cross-browser Testing",
    ]
    lower = jd_text.lower()
    return [kw for kw in known if kw.lower() in lower]


def _heuristic_score(jd_text: str, company: str = "", title: str = "") -> FitScore:
    text = f"{title}\n{jd_text}".lower()
    role = infer_role(title, jd_text)
    candidate_terms = {
        "react", "typescript", "javascript", "vue", "scss", "tailwind", "astro",
        "next.js", "node", "rest", "api", "git", "github actions", "azure",
        "docker", "testing", "vitest", "responsive", "frontend", "front-end",
        "full-stack", "ui", "mapbox", "geojson", ".net", "c#",
    }
    senior_terms = ("senior", "lead", "principal", "staff", "architect", "manager")
    matched = sorted({term for term in candidate_terms if term in text})
    score = 45 + min(len(matched) * 5, 35)

    if role == "frontend":
        score += 8
    if any(term in text for term in ("junior", "graduate", "entry", "intern")):
        score += 6
    title_lower = title.lower()
    senior_in_title = any(
        re.search(rf"\b{re.escape(term)}\b", title_lower) for term in senior_terms
    )
    if senior_in_title:
        score -= 25
    if "5+" in text or "five years" in text or "5 years" in text:
        score -= 12
    if "remote" in text or "auckland" in text or "new zealand" in text:
        score += 4

    score = max(0, min(100, score))
    verdict = "apply" if score >= 75 else "maybe" if score >= 60 else "skip"
    ats_keywords = _extract_keywords(jd_text)
    gaps = [
        kw for kw in ats_keywords
        if kw.lower() not in {m.lower() for m in matched}
        and kw.lower() not in {"rest apis", "unit testing", "integration testing"}
    ]
    red_flags = []
    if not re.search(r"\$|salary|remuneration|compensation", jd_text, re.I):
        red_flags.append("No salary range present")
    if senior_in_title:
        red_flags.append("Seniority may be above target")

    angle_by_role = {
        "frontend": (
            "Emphasize production-ready UI delivery, TypeScript frontend work, "
            "API integration, and collaboration with product/design."
        ),
        "backend": "Emphasize API/backend delivery, TypeScript/Node/.NET evidence, and pragmatic production work.",
        "fullstack": "Emphasize full-stack product delivery, React/TypeScript UI work, API integration, and ownership.",
        "data": "Emphasize applied AI/data-adjacent project work only where the JD aligns with verified evidence.",
        "devops": "Emphasize GitHub Actions, Azure, Docker, and deployment evidence without overstating infrastructure depth.",
    }

    return FitScore(
        score=score,
        verdict=verdict,
        confidence="medium",
        reason=f"{role} role with {len(matched)} candidate skill/evidence overlaps",
        matched_requirements=matched[:12],
        partial_matches=["Vue/SCSS frontend work can support React UI delivery"]
        if role == "frontend" and "vue" not in matched else [],
        gaps=gaps[:8],
        red_flags=red_flags,
        role=role,
        ats_keywords=ats_keywords[:12],
        resume_keywords=ats_keywords[:10],
        cover_letter_angle=angle_by_role.get(role, angle_by_role["fullstack"]),
        scorer="heuristic",
    )


def _coerce_fit(data: dict[str, Any], scorer: str) -> FitScore:
    score = int(data.get("score", 0))
    score = max(0, min(100, score))
    verdict = str(data.get("verdict") or ("apply" if score >= 75 else "maybe" if score >= 60 else "skip")).lower()
    if verdict not in {"apply", "maybe", "skip"}:
        verdict = "apply" if score >= 75 else "maybe" if score >= 60 else "skip"
    return FitScore(
        score=score,
        verdict=verdict,
        confidence=str(data.get("confidence", "medium")),
        reason=str(data.get("reason", ""))[:500],
        matched_requirements=list(data.get("matched_requirements", []))[:20],
        partial_matches=list(data.get("partial_matches", []))[:20],
        gaps=list(data.get("gaps", []))[:20],
        red_flags=list(data.get("red_flags", []))[:20],
        role=str(data.get("role", "fullstack")),
        ats_keywords=list(data.get("ats_keywords", []))[:20],
        resume_keywords=list(data.get("resume_keywords", []))[:12],
        cover_letter_angle=str(data.get("cover_letter_angle", ""))[:1000],
        scorer=scorer,
    )


def llm_score_fit(
    jd_text: str,
    candidate_context: str,
    company: str = "",
    title: str = "",
    model: str = "claude-3-haiku-20250303",
) -> FitScore:
    """Score with Anthropic and return a structured fit decision."""
    if not HAS_ANTHROPIC:
        raise RuntimeError("anthropic package required for LLM scoring")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for LLM scoring")

    prompt = f"""You are evaluating job fit for a New Zealand early-career software developer.
Return ONLY valid JSON. Do not fabricate candidate evidence.

SCORING RUBRIC:
- Skills/stack alignment: 35%
- Evidence strength from candidate profile/projects: 25%
- Seniority fit: 15%
- Location/work rights fit: 10%
- Growth/interest fit: 10%
- Red flags subtract 5-20 points when serious

DECISION RULES:
- 75-100: verdict "apply"
- 60-74: verdict "maybe"
- 0-59: verdict "skip"
- Adjacent skills can be partial matches, not hard failures.
- Missing nice-to-have tools should not dominate if core evidence is strong.

CANDIDATE CONTEXT:
{candidate_context}

JOB:
Company: {company or 'Unknown'}
Title: {title or 'Unknown'}
JD:
{jd_text}

Return this exact JSON object shape:
{{
  "score": 0,
  "verdict": "apply|maybe|skip",
  "confidence": "low|medium|high",
  "reason": "one concise paragraph",
  "matched_requirements": ["requirement + candidate evidence"],
  "partial_matches": ["JD term + adjacent candidate evidence"],
  "gaps": ["real gap or weak evidence"],
  "red_flags": ["concern"],
  "role": "frontend|backend|fullstack|data|devops",
  "ats_keywords": ["important exact JD terms"],
  "resume_keywords": ["truthful keywords to include in resume"],
  "cover_letter_angle": "brief angle for a tailored cover letter"
}}
"""
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return _coerce_fit(json.loads(text), scorer="llm")


def score_fit(
    jd_text: str,
    company: str = "",
    title: str = "",
    root: Path | None = None,
    use_llm: bool = True,
) -> FitScore:
    """LLM-first fit scoring with heuristic fallback."""
    if use_llm and HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return llm_score_fit(
                jd_text,
                build_candidate_context(root),
                company=company,
                title=title,
            )
        except Exception as exc:  # noqa: BLE001 - CLI should fail soft
            fallback = _heuristic_score(jd_text, company=company, title=title)
            return FitScore(
                **{**fallback.to_dict(), "scorer": "heuristic", "reason": f"LLM scoring failed ({exc}); {fallback.reason}"}
            )
    return _heuristic_score(jd_text, company=company, title=title)
