#!/usr/bin/env python3
"""Create a local job application package, with dry-run support."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.paths import project_root  # noqa: E402
from lib.workflow import WorkflowOptions, create_application_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a job application package")
    parser.add_argument("--job", required=True, help="Path to the job description file")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--position", required=True, help="Position/title")
    parser.add_argument(
        "--role", help="Role focus: frontend, backend, fullstack, devops, data"
    )
    parser.add_argument("--keywords", nargs="*", default=[], help="Job keywords to add")
    parser.add_argument(
        "--priority", default="Medium", choices=["High", "Medium", "Low"]
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview actions without writing files"
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip local PDF render (default: render via typst)",
    )
    args = parser.parse_args()

    root = project_root()
    job_path = Path(args.job)
    if not job_path.is_absolute():
        job_path = root / job_path
    if not job_path.exists():
        parser.error(f"Job description not found: {job_path}")

    try:
        result = create_application_package(
            WorkflowOptions(
                project_root=root,
                job_path=job_path,
                company=args.company,
                position=args.position,
                role=args.role,
                keywords=tuple(args.keywords),
                priority=args.priority,
                dry_run=args.dry_run,
                render_pdf=not args.no_pdf,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI should show concise failures
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    mode = "DRY RUN" if args.dry_run else "CREATED"
    action_text = "\n".join(f"- {action}" for action in result.planned_actions)
    print(f"{mode}: {result.application_dir}")
    if action_text:
        print(action_text)
    if result.warnings:
        print("\nRemaining placeholders to fill in:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
