#!/usr/bin/env python3
"""
JSON Resume Manager
Generates role-optimized JSON resumes from the base template.
"""

import json
import secrets
import string
import sys
from pathlib import Path
from typing import Dict, List, Any


ROLE_CONFIGS = {
    "frontend": {
        "aliases": ["front-end", "ui", "react", "vue"],
        "summary_replace": ("full-stack development", "frontend development with modern JavaScript frameworks"),
        "skill_boost": ["Languages & Frameworks", "AI & LLM"],
        "layout": [
            [
                ["profiles", "summary", "experience", "projects"],
                ["skills", "education", "certifications", "languages"]
            ]
        ],
        "hide_sections": [],
    },
    "backend": {
        "aliases": ["back-end", "api", "server", "python"],
        "summary_replace": ("modern web technologies", "backend systems, APIs, and database design"),
        "skill_boost": ["Databases", "Languages & Frameworks"],
        "layout": [
            [
                ["profiles", "summary", "experience", "projects"],
                ["skills", "education", "certifications", "languages"]
            ]
        ],
        "hide_sections": [],
    },
    "fullstack": {
        "aliases": ["full-stack", "full stack"],
        "summary_replace": None,
        "skill_boost": [],
        "layout": None,
        "hide_sections": [],
    },
    "devops": {
        "aliases": ["cloud", "infrastructure", "sre"],
        "summary_replace": ("modern web technologies", "cloud infrastructure, CI/CD, and DevOps practices"),
        "skill_boost": ["DevOps & Tools", "Databases"],
        "layout": None,
        "hide_sections": ["interests"],
    },
    "data": {
        "aliases": ["analytics", "ml", "ai", "machine-learning"],
        "summary_replace": ("full-stack development", "AI/ML development and data-driven solutions"),
        "skill_boost": ["AI & LLM", "Databases"],
        "layout": None,
        "hide_sections": ["interests"],
    },
}


def generate_cuid2() -> str:
    """Generate a CUID2-like ID (24 characters, lowercase + digits)."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(24))


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

    # Boost relevant skill categories to level 5
    if config["skill_boost"]:
        for skill in resume["sections"]["skills"]["items"]:
            if skill["name"] in config["skill_boost"]:
                skill["level"] = 5

    # Update summary text
    if config["summary_replace"]:
        old, new = config["summary_replace"]
        resume["sections"]["summary"]["content"] = (
            resume["sections"]["summary"]["content"].replace(old, new)
        )

    # Override layout if specified
    if config["layout"]:
        resume["metadata"]["layout"] = config["layout"]

    # Hide irrelevant sections
    for section_name in config["hide_sections"]:
        if section_name in resume["sections"]:
            resume["sections"][section_name]["visible"] = False

    return resume


def add_keywords(resume: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
    """Add job-specific keywords to matching skill categories."""
    for skill in resume["sections"]["skills"]["items"]:
        existing = [k.lower() for k in skill.get("keywords", [])]
        for kw in keywords:
            # Match keyword to skill category by checking if it relates to existing keywords
            if kw.lower() not in existing:
                # Add to the first skill group that has a related keyword
                for existing_kw in skill.get("keywords", []):
                    if _keywords_related(kw, existing_kw):
                        skill["keywords"].append(kw)
                        existing.append(kw.lower())
                        break
    return resume


def _keywords_related(new_kw: str, existing_kw: str) -> bool:
    """Check if two keywords are in the same domain using exact token matching."""
    domains = [
        {"react", "vue", "angular", "svelte", "next.js", "nuxt", "typescript", "javascript", "css", "tailwind", "html"},
        {"python", "django", "flask", "fastapi", "node.js", "express", ".net", "c#", "java", "spring", "go", "rust"},
        {"docker", "kubernetes", "aws", "azure", "gcp", "terraform", "ci/cd", "github actions", "jenkins"},
        {"mongodb", "postgresql", "mysql", "sql server", "redis", "firebase", "dynamodb"},
        {"openai", "langchain", "llm", "ai agents", "ml", "prompt engineering", "claude", "gpt"},
        {"agile", "scrum", "kanban", "leadership", "management"},
    ]
    new_lower = new_kw.lower()
    existing_lower = existing_kw.lower()
    for domain in domains:
        if new_lower in domain and existing_lower in domain:
            return True
    return False


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
                resume["sections"][section]["visible"] = False

    if show:
        for section in show:
            if section in resume["sections"]:
                resume["sections"][section]["visible"] = True

    if keywords:
        resume = add_keywords(resume, keywords)

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
            vis = "visible" if section.get("visible", True) else "hidden"
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
