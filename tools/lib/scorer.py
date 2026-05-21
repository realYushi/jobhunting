"""Job listing scorer.

Uses semantic matching to score listing snippets against the candidate's profile.
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

try:
    from anthropic import Anthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

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


_SCORING_INSTRUCTIONS = """You are scoring job listings for fit against a candidate. Return ONLY valid JSON.

Score each listing 0-100 based on:
- Alignment of skills and experience
- Seniority match
- Industry/domain relevance
- Growth opportunity

Return JSON array with objects containing:
- job_id (exact string from input)
- score (integer 0-100)
- reason (one sentence, max 15 words)

Example output format:
[
  {"job_id": "12345", "score": 82, "reason": "Strong Python/backend match with senior growth potential"},
  {"job_id": "67890", "score": 45, "reason": "Heavy focus on legacy Java, mismatch with candidate's stack"}
]"""


def _build_anthropic_client() -> "Anthropic":
    if not HAS_ANTHROPIC:
        raise RuntimeError("anthropic package required for LLM scoring")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable required for LLM scoring"
        )
    return Anthropic(api_key=api_key)


def _llm_score_batch(
    client: "Anthropic",
    listings: list[dict[str, Any]],
    profile_text: str,
) -> list[dict[str, Any]]:
    """Score a batch of listings using Claude API.

    The instructions + candidate profile are sent as cacheable system blocks
    so that batches 2..N (sharing the same prefix) hit the prompt cache and
    only pay for the listings block on each call.
    """
    listing_blocks = []
    for i, lst in enumerate(listings):
        listing_blocks.append(
            f"{i + 1}. job_id={lst['job_id']}\n"
            f"   title: {lst.get('title', 'Unknown')}\n"
            f"   company: {lst.get('company', 'Unknown')}\n"
            f"   snippet: {lst.get('snippet', 'No description')}\n"
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        temperature=0,
        system=[
            {"type": "text", "text": _SCORING_INSTRUCTIONS},
            {
                "type": "text",
                "text": f"CANDIDATE PROFILE:\n{profile_text}",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[
            {
                "role": "user",
                "content": "JOB LISTINGS TO SCORE:\n" + "\n".join(listing_blocks),
            }
        ],
    )

    result_text = response.content[0].text
    json_start = result_text.find("[")
    json_end = result_text.rfind("]") + 1
    if json_start >= 0 and json_end > json_start:
        result_text = result_text[json_start:json_end]

    return json.loads(result_text)


def score_listings(
    listings: list[dict[str, Any]],
    profile_summary: str | None = None,
    use_llm: bool = True,
) -> list[ScoreResult]:
    """Score a batch of listings against the candidate profile.

    Args:
        listings: List of job listing dicts with keys:
            - job_id, source, title, company, snippet, [url]
        profile_summary: Pre-computed candidate summary (optional).
        use_llm: Use Claude API for scoring. Falls back to keyword overlap if False.

    Returns:
        List of ScoreResult objects with score (0-100) and one-line reason.
    """
    if profile_summary is None:
        profile = load_candidate_profile()
        profile_summary = candidate_summary(profile)

    if not listings:
        return []

    # Try LLM scoring if available and requested
    if use_llm and HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            client = _build_anthropic_client()
            batch_size = 20
            batches = [
                listings[i : i + batch_size]
                for i in range(0, len(listings), batch_size)
            ]
            llm_results: list[dict[str, Any]] = []
            if len(batches) == 1:
                llm_results.extend(
                    _llm_score_batch(client, batches[0], profile_summary)
                )
            else:
                # Run the first batch alone so its cache write lands before the
                # rest race for the same prefix; remaining batches go parallel
                # and hit the cache.
                llm_results.extend(
                    _llm_score_batch(client, batches[0], profile_summary)
                )
                with ThreadPoolExecutor(max_workers=3) as pool:
                    for batch_results in pool.map(
                        lambda b: _llm_score_batch(client, b, profile_summary),
                        batches[1:],
                    ):
                        llm_results.extend(batch_results)

            # Merge LLM results back with listing metadata
            results_by_id: dict[str, dict[str, Any]] = {
                r["job_id"]: r for r in llm_results
            }

            results = []
            for lst in listings:
                job_id = lst["job_id"]
                llm_result = results_by_id.get(
                    job_id, {"score": 50, "reason": "Scoring failed, using default"}
                )
                results.append(
                    ScoreResult(
                        job_id=job_id,
                        source=lst["source"],
                        title=lst.get("title", "Unknown"),
                        company=lst.get("company", "Unknown"),
                        url=lst.get("url"),
                        score=llm_result["score"],
                        reason=llm_result["reason"],
                    )
                )
            return results

        except Exception as e:
            # Fall back to keyword scoring on error
            print(
                f"LLM scoring failed: {e}. Using keyword overlap.",
                file=sys.stderr,
            )
            use_llm = False

    # Keyword-based fallback scoring — target dev / software engineer roles
    # at junior / intermediate / mid level. Drop senior+ and non-IC roles.
    DEV_TITLE_TERMS = (
        "software engineer",
        "software developer",
        "full stack",
        "fullstack",
        "full-stack",
        "backend",
        "back-end",
        "back end",
        "frontend",
        "front-end",
        "front end",
        "developer",
        "engineer",
    )
    STACK_TERMS = (
        "python",
        "typescript",
        "javascript",
        "react",
        "node",
        "next.js",
        "fastapi",
        "django",
        "postgres",
        "aws",
        "ai",
        "ml",
        "llm",
    )
    JUNIOR_TERMS = ("junior", "graduate", "entry", "intern", "associate")
    SENIOR_DROP_TERMS = (
        "senior",
        "lead",
        "principal",
        "staff",
        "head of",
        "architect",
        "manager",
        "director",
    )
    EXCLUDE_TERMS = (
        "sales",
        "marketing",
        "recruiter",
        "designer",
        "qa engineer",
        "test engineer",
        "devops",
        "sre",
        "data engineer",
        "security engineer",
        "network engineer",
        "hardware",
        "mechanical",
        "electrical",
    )

    def _has_token(title: str, term: str) -> bool:
        # word-boundary-ish match so "lead" doesn't catch "Leading", and
        # "head of" still works as a phrase.
        if " " in term:
            return term in title
        return any(t == term for t in title.replace("/", " ").replace("-", " ").split())

    results = []
    for lst in listings:
        title = lst.get("title", "").lower()
        snippet = lst.get("snippet", "").lower()

        # Hard drops first.
        if any(_has_token(title, t) for t in SENIOR_DROP_TERMS):
            results.append(
                ScoreResult(
                    job_id=lst["job_id"],
                    source=lst["source"],
                    title=lst.get("title", "Unknown"),
                    company=lst.get("company", "Unknown"),
                    url=lst.get("url"),
                    score=20,
                    reason="Senior/lead/principal level — out of target",
                )
            )
            continue

        score = 50
        matched_title = next((t for t in DEV_TITLE_TERMS if t in title), None)
        if matched_title:
            score = 75
            if matched_title in (
                "software engineer",
                "software developer",
                "full stack",
                "fullstack",
                "full-stack",
            ):
                score = 80

        if any(_has_token(title, t) for t in JUNIOR_TERMS):
            score += 8

        stack_hits = sum(1 for t in STACK_TERMS if t in title or t in snippet)
        score += min(stack_hits * 3, 12)

        if any(t in title for t in EXCLUDE_TERMS):
            score -= 30

        score = max(0, min(100, score))
        reason = (
            f"Title match: '{matched_title}', stack hits: {stack_hits}"
            if matched_title
            else f"No dev/SWE title match, stack hits: {stack_hits}"
        )

        results.append(
            ScoreResult(
                job_id=lst["job_id"],
                source=lst["source"],
                title=lst.get("title", "Unknown"),
                company=lst.get("company", "Unknown"),
                url=lst.get("url"),
                score=score,
                reason=reason,
            )
        )

    return results


def filter_by_score(results: list[ScoreResult], cutoff: int = 65) -> list[ScoreResult]:
    """Filter scored listings by score cutoff."""
    return [r for r in results if r.score >= cutoff]


def sort_by_score(results: list[ScoreResult]) -> list[ScoreResult]:
    """Sort results by score descending."""
    return sorted(results, key=lambda r: r.score, reverse=True)
