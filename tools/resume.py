#!/usr/bin/env python3
"""CLI: generate a role-optimized JSON resume from the base template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.paths import project_root  # noqa: E402
from lib.resume import (  # noqa: E402
    ResumeError,
    create_resume,
    list_role_names,
    load_base_resume,
    resolve_role,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate role-optimized JSON resumes")
    parser.add_argument("--company", help="Company name")
    parser.add_argument(
        "--role", help="Role focus (frontend, backend, fullstack, devops, data)"
    )
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--hide", nargs="*", help="Sections to hide")
    parser.add_argument("--show", nargs="*", help="Sections to show")
    parser.add_argument("--keywords", nargs="*", help="Job keywords to add to skills")
    parser.add_argument("--validate", help="Validate a JSON resume file")
    parser.add_argument(
        "--list-sections", action="store_true", help="List all sections"
    )

    args = parser.parse_args()
    root = project_root()

    if args.validate:
        try:
            with open(args.validate) as f:
                json.load(f)
            print("JSON validation: PASSED")
            return 0
        except json.JSONDecodeError as e:
            print(f"JSON validation: FAILED - {e}")
            return 1

    if args.list_sections:
        resume = load_base_resume(root)
        print("Available sections:")
        for name, section in resume["sections"].items():
            vis = "hidden" if section.get("hidden", False) else "visible"
            print(f"  {name} ({vis})")
        return 0

    if not args.company:
        parser.error("--company is required for resume generation")

    role = None
    if args.role:
        role = resolve_role(args.role)
        if not role:
            parser.error(
                f"Unknown role: {args.role}. Valid: {', '.join(list_role_names())}"
            )

    try:
        resume = create_resume(
            root, args.company, role, args.hide, args.show, args.keywords
        )
    except ResumeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = (
        args.output or f"applications/active/{args.company}/documents/resume.json"
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as f:
        json.dump(resume, f, indent=2)
    print(f"Resume saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
