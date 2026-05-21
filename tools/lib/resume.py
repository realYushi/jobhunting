"""Resume generation: role-optimized customization of the base resume."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import base_resume_path, project_root
from .scoring import load_role_configs


class ResumeError(Exception):
    """Raised when resume input is missing or malformed."""


def _get_configs() -> tuple[dict, dict[str, str], dict[str, str]]:
    cfg = load_role_configs()
    return cfg["roles"], cfg["keyword_to_group"], cfg["role_default_group"]


def _get_synonyms() -> dict[str, str]:
    return load_role_configs().get("synonyms", {})


def _canon(keyword: str, synonyms: dict[str, str]) -> str:
    """Lowercase + map known synonyms to a canonical form for dedup comparisons."""
    k = keyword.lower().strip()
    return synonyms.get(k, k)


def resolve_role(role_input: str) -> str | None:
    """Resolve a role alias to its canonical name."""
    role_configs, _, _ = _get_configs()
    role_lower = role_input.lower()
    for canonical, config in role_configs.items():
        if role_lower == canonical or role_lower in config["aliases"]:
            return canonical
    return None


def load_base_resume(root: Path | None = None) -> dict:
    """Load the base resume JSON file. Raises ResumeError on failure."""
    resume_path = base_resume_path(root)
    try:
        with open(resume_path) as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise ResumeError(f"Base resume not found at {resume_path}") from exc
    except json.JSONDecodeError as exc:
        raise ResumeError(f"Invalid JSON in base resume: {exc}") from exc


def apply_role_focus(resume: dict, role: str) -> dict:
    """Apply role-specific customizations to resume (mutates in place)."""
    role_configs, _, _ = _get_configs()
    config = role_configs.get(role)
    if not config:
        return resume

    skill_names = {s["name"] for s in resume["sections"]["skills"]["items"]}
    for boost_name in config["skill_boost"]:
        if boost_name not in skill_names:
            raise ResumeError(
                f"Role '{role}' boosts skill group '{boost_name}', but no such group "
                f"exists in base-resume.json. Available: {sorted(skill_names)}"
            )
        for skill in resume["sections"]["skills"]["items"]:
            if skill["name"] == boost_name:
                skill["level"] = 5

    if config["summary"]:
        resume["summary"]["content"] = config["summary"]

    for section_name in config["hide_sections"]:
        if section_name in resume["sections"]:
            resume["sections"][section_name]["hidden"] = True

    return resume


def add_keywords(
    resume: dict,
    keywords: list[str],
    role: str | None = None,
) -> dict:
    """Add job-specific keywords to skill groups. Never silently drops a keyword."""
    _, keyword_map, default_map = _get_configs()
    synonyms = _get_synonyms()
    skill_groups = {s["name"]: s for s in resume["sections"]["skills"]["items"]}
    default_group = default_map.get(role or "", "Backend")
    if default_group not in skill_groups:
        default_group = next(iter(skill_groups), None)
    if default_group is None:
        return resume

    for kw in keywords:
        target = keyword_map.get(kw.lower(), default_group)
        if target not in skill_groups:
            target = default_group
        group = skill_groups[target]
        existing = {_canon(k, synonyms) for k in group.get("keywords", [])}
        if _canon(kw, synonyms) not in existing:
            group.setdefault("keywords", []).append(kw)
    return resume


def create_resume(
    root: Path | None,
    company: str,
    role: str | None = None,
    hide: list[str] | None = None,
    show: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """Create a job-specific resume."""
    resume = load_base_resume(root or project_root())

    if role:
        resume = apply_role_focus(resume, role)

    if hide:
        for section in hide:
            if section in resume["sections"]:
                resume["sections"][section]["hidden"] = True

    if show:
        for section in show:
            if section in resume["sections"]:
                resume["sections"][section]["hidden"] = False

    if keywords:
        resume = add_keywords(resume, keywords, role)

    resume["metadata"]["notes"] = f"Customized for {company}"
    return resume


def list_role_names() -> list[str]:
    """Return canonical role names from the config."""
    role_configs, _, _ = _get_configs()
    return list(role_configs.keys())
