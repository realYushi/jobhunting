#!/usr/bin/env python3
"""
JSON Resume Manager
Generates role-optimized JSON resumes from the base template.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


# Per-role customizations. Skill-group names must match those in base-resume.json.
ROLE_CONFIGS = {
    "frontend": {
        "aliases": ["front-end", "ui", "react", "vue"],
        "summary": "<p>Frontend-focused product engineer building user-facing tools with React, Next.js, TypeScript, and Vue. Third-year CS student at AUT (GPA 7.75/9.0) with Azure AI certification. Build things that work.</p>",
        "skill_boost": ["Frontend", "AI Development"],
        "hide_sections": [],
    },
    "backend": {
        "aliases": ["back-end", "api", "server", "python"],
        "summary": "<p>Backend engineer building APIs and services with .NET Core, Node.js, Python, and SQL/NoSQL databases. Third-year CS student at AUT (GPA 7.75/9.0) with Azure AI certification. Build things that work.</p>",
        "skill_boost": ["Backend", "Database"],
        "hide_sections": [],
    },
    "fullstack": {
        "aliases": ["full-stack", "full stack"],
        "summary": None,
        "skill_boost": [],
        "hide_sections": [],
    },
    "devops": {
        "aliases": ["cloud", "infrastructure", "sre"],
        "summary": "<p>Engineer focused on cloud infrastructure, CI/CD, and DevOps practices with Docker, GitHub Actions, and Azure. Third-year CS student at AUT (GPA 7.75/9.0) with Azure AI certification. Build things that work.</p>",
        "skill_boost": ["DevOps", "Database"],
        "hide_sections": ["interests"],
    },
    "data": {
        "aliases": ["analytics", "ml", "ai", "machine-learning"],
        "summary": "<p>AI/ML-focused engineer building agentic systems and data-driven applications with Claude Code, Python, and modern LLM tooling. Third-year CS student at AUT (GPA 7.75/9.0) with Azure AI certification. Build things that work.</p>",
        "skill_boost": ["AI Development", "Database"],
        "hide_sections": ["interests"],
    },
}


# Maps a job keyword (lowercased) to the skill-group in base-resume.json
# it should be filed under. Anything not listed falls back to the role default.
KEYWORD_TO_GROUP = {
    # Frontend
    "react": "Frontend", "vue": "Frontend", "vue.js": "Frontend", "angular": "Frontend",
    "svelte": "Frontend", "next.js": "Frontend", "nextjs": "Frontend", "nuxt": "Frontend",
    "typescript": "Frontend", "javascript": "Frontend", "css": "Frontend",
    "tailwind": "Frontend", "tailwind css": "Frontend", "html": "Frontend", "sass": "Frontend",
    # Backend
    "python": "Backend", "django": "Backend", "flask": "Backend", "fastapi": "Backend",
    "node.js": "Backend", "nodejs": "Backend", "express": "Backend",
    ".net": "Backend", ".net core": "Backend", "c#": "Backend",
    "java": "Backend", "spring": "Backend", "go": "Backend", "rust": "Backend",
    "graphql": "Backend", "rest": "Backend",
    # DevOps
    "docker": "DevOps", "kubernetes": "DevOps", "k8s": "DevOps",
    "aws": "DevOps", "azure": "DevOps", "gcp": "DevOps",
    "terraform": "DevOps", "ci/cd": "DevOps", "github actions": "DevOps", "jenkins": "DevOps",
    # Database
    "mongodb": "Database", "postgresql": "Database", "postgres": "Database",
    "mysql": "Database", "sql server": "Database", "redis": "Database",
    "firebase": "Database", "dynamodb": "Database",
    # AI Development
    "openai": "AI Development", "langchain": "AI Development", "llm": "AI Development",
    "ai agents": "AI Development", "ml": "AI Development",
    "prompt engineering": "AI Development", "claude": "AI Development",
    "gpt": "AI Development", "mcp": "AI Development", "rag": "AI Development",
}


# Where unmatched keywords land, per role.
ROLE_DEFAULT_GROUP = {
    "frontend": "Frontend",
    "backend": "Backend",
    "fullstack": "Backend",
    "devops": "DevOps",
    "data": "AI Development",
}


def resolve_role(role_input: str) -> str:
    """Resolve a role alias to its canonical name."""
    role_lower = role_input.lower()
    for canonical, config in ROLE_CONFIGS.items():
        if role_lower == canonical or role_lower in config["aliases"]:
            return canonical
    return None


def load_base_resume(base_path: Path) -> Dict[str, Any]:
    """Load the base resume JSON file."""
    resume_path = base_path / "templates" / "base-resume.json"
    try:
        with open(resume_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Base resume not found at {resume_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in base resume: {e}", file=sys.stderr)
        sys.exit(1)


def apply_role_focus(resume: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Apply role-specific customizations to resume."""
    config = ROLE_CONFIGS.get(role)
    if not config:
        return resume

    skill_names = {s["name"] for s in resume["sections"]["skills"]["items"]}
    for boost_name in config["skill_boost"]:
        if boost_name not in skill_names:
            raise ValueError(
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


def add_keywords(resume: Dict[str, Any], keywords: List[str],
                 role: Optional[str] = None) -> Dict[str, Any]:
    """Add job-specific keywords to skill groups. Never silently drops a keyword."""
    skill_groups = {s["name"]: s for s in resume["sections"]["skills"]["items"]}
    default_group = ROLE_DEFAULT_GROUP.get(role or "", "Backend")
    if default_group not in skill_groups:
        # Fall back to the first available skill group so unmatched keywords still land.
        default_group = next(iter(skill_groups), None)
    if default_group is None:
        return resume

    for kw in keywords:
        target = KEYWORD_TO_GROUP.get(kw.lower(), default_group)
        if target not in skill_groups:
            target = default_group
        group = skill_groups[target]
        existing = {k.lower() for k in group.get("keywords", [])}
        if kw.lower() not in existing:
            group.setdefault("keywords", []).append(kw)
    return resume


def create_resume(base_path: Path, company: str, role: str = None,
                  hide: List[str] = None, show: List[str] = None,
                  keywords: List[str] = None) -> Dict[str, Any]:
    """Create a job-specific resume."""
    resume = load_base_resume(base_path)

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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate role-optimized JSON resumes")
    parser.add_argument("--company", help="Company name")
    parser.add_argument("--role", help="Role focus (frontend, backend, fullstack, devops, data)")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--hide", nargs="*", help="Sections to hide")
    parser.add_argument("--show", nargs="*", help="Sections to show")
    parser.add_argument("--keywords", nargs="*", help="Job keywords to add to skills")
    parser.add_argument("--validate", help="Validate a JSON resume file")
    parser.add_argument("--list-sections", action="store_true", help="List all sections")

    args = parser.parse_args()
    base_path = Path(".")

    if args.validate:
        try:
            with open(args.validate, 'r') as f:
                json.load(f)
            print("JSON validation: PASSED")
        except json.JSONDecodeError as e:
            print(f"JSON validation: FAILED - {e}")
        return

    if args.list_sections:
        resume = load_base_resume(base_path)
        print("Available sections:")
        for name, section in resume["sections"].items():
            vis = "hidden" if section.get("hidden", False) else "visible"
            print(f"  {name} ({vis})")
        return

    if not args.company:
        parser.error("--company is required for resume generation")

    # Resolve role
    role = None
    if args.role:
        role = resolve_role(args.role)
        if not role:
            valid = ", ".join(ROLE_CONFIGS.keys())
            parser.error(f"Unknown role: {args.role}. Valid: {valid}")

    resume = create_resume(base_path, args.company, role, args.hide, args.show, args.keywords)

    output_path = args.output or f"applications/active/{args.company}/documents/resume.json"
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w') as f:
        json.dump(resume, f, indent=2)
    print(f"Resume saved to: {output}")


if __name__ == "__main__":
    main()
