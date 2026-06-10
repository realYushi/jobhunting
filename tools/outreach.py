#!/usr/bin/env python3
"""Prepare one-off outreach targets for per-company subagents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lib.hunter import top_contacts  # noqa: E402
from lib.paths import company_dirname, project_root, tracker_path  # noqa: E402
from lib.templates import render_cold_email  # noqa: E402
from lib.tracker import load_tracker  # noqa: E402


_AGENT_TYPE = "outreach-company"


def _agent_prompt(target: dict) -> str:
    return (
        f"Read this outreach target's contacts_path ({target['contacts_path']}), "
        f"jd_path ({target['jd_path']}), analysis_path ({target['analysis_path']}), "
        f"resume_path ({target['resume_path']}), cold_email_path ({target['cold_email_path']}), "
        "and LinkedIn-CV-Profile.md. This is for one already-submitted application package. "
        "First evaluate whether the current contacts are usable. If they are weak or empty, "
        "try additional evidence-based contact discovery using available tools, but never invent a contact. "
        "Choose the best recipient, flag any wrong-entity / wrong-region / low-confidence risks, "
        "and only if the contact is good enough rewrite cold_email_path into a complete, role-aware email. "
        "Replace all placeholders and remove the auto-generated context HTML comment before finishing. "
        "Report status (ready|risky_contact|no_contact_found), chosen recipient, evidence, and whether the file was updated."
    )


def _submitted_rows(root: Path) -> list[dict]:
    tracker = load_tracker(tracker_path(root))
    rows = [
        app
        for app in tracker.get("applications", {}).get("active", [])
        if app.get("status") == "Submitted"
    ]
    rows.sort(
        key=lambda app: (
            app.get("submitted_at") or "",
            app.get("company") or "",
            app.get("position") or "",
        )
    )
    return rows


def _slug_from_pdf_path(pdf_path: str | None) -> str | None:
    if not pdf_path:
        return None
    match = re.search(
        r"applications/(?:active|archive/submitted)/([^/]+)/documents/", str(pdf_path)
    )
    return match.group(1) if match else None


def _resolve_archive_dir(root: Path, app: dict) -> Path:
    company = str(app.get("company") or "")
    job_id = app.get("job_id")
    candidates: list[str] = []
    # Probe BOTH slug forms: legacy directories predate job_id-suffixed slugs,
    # so an archived package may sit under either ``{Company}-{id8}`` or the
    # bare ``{Company}`` name depending on when it was created.
    for slug in (
        _slug_from_pdf_path(app.get("pdf_path")),
        company_dirname(company, job_id),
        company_dirname(company, None),
    ):
        if slug and slug not in candidates:
            candidates.append(slug)

    archive_base = root / "applications" / "archive" / "submitted"
    for slug in candidates:
        candidate = archive_base / slug
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Could not resolve archive dir for {company} — {app.get('position')}"
    )


def _prepare_target(root: Path, app: dict, scaffold: bool) -> dict:
    archive_dir = _resolve_archive_dir(root, app)
    research_dir = archive_dir / "research"
    documents_dir = archive_dir / "documents"
    contacts_path = research_dir / "contacts.json"
    cold_email_path = documents_dir / "cold-email.md"
    jd_path = research_dir / "job-description.md"
    analysis_path = research_dir / "analysis.md"
    resume_path = documents_dir / "resume.json"

    if scaffold and not cold_email_path.exists():
        contact = top_contacts(archive_dir, limit=1)
        job_text = jd_path.read_text(errors="replace") if jd_path.exists() else ""
        cold_email_path.write_text(
            render_cold_email(
                str(app.get("company") or ""),
                str(app.get("position") or ""),
                root=root,
                job_text=job_text,
                contact=contact[0] if contact else None,
            )
        )

    target = {
        "company": app.get("company"),
        "position": app.get("position"),
        "submitted_at": app.get("submitted_at"),
        "source": app.get("source"),
        "job_id": app.get("job_id"),
        "url": app.get("url"),
        "archive_path": str(archive_dir),
        "contacts_path": str(contacts_path),
        "jd_path": str(jd_path),
        "analysis_path": str(analysis_path),
        "resume_path": str(resume_path),
        "cold_email_path": str(cold_email_path),
        "subagent_type": _AGENT_TYPE,
        "agent_description": f"Outreach: {app.get('company')}"
    }
    target["agent_prompt"] = _agent_prompt(target)
    return target


def cmd_list(args: argparse.Namespace) -> int:
    root = project_root()
    rows = _submitted_rows(root)
    if not rows:
        print("No submitted applications found.")
        return 0
    for idx, app in enumerate(rows, start=1):
        print(
            f"{idx}. {app.get('submitted_at', '?')} — {app.get('position')} @ {app.get('company')}"
        )
    return 0


def _select_rows(rows: list[dict], picks: list[int]) -> list[dict]:
    selected: list[dict] = []
    for pick in picks:
        if pick < 1 or pick > len(rows):
            raise ValueError(f"Invalid selection: {pick}")
        selected.append(rows[pick - 1])
    return selected


def prepare_targets(picks: list[int], *, output: str, no_scaffold: bool) -> tuple[int, list[dict]]:
    root = project_root()
    rows = _submitted_rows(root)
    if not rows:
        raise ValueError("No submitted applications found.")
    selected = _select_rows(rows, picks)
    targets = [_prepare_target(root, app, scaffold=not no_scaffold) for app in selected]
    payload = {"targets": targets}

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return len(targets), targets


def cmd_prepare(args: argparse.Namespace) -> int:
    try:
        count, targets = prepare_targets(
            args.pick, output=args.output, no_scaffold=args.no_scaffold
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Prepared {count} outreach target(s) → {args.output}")
    for target in targets:
        print(f"- {target['company']} — {target['position']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List submitted applications and prepare per-company outreach targets."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list-submitted", help="List submitted applications")
    list_parser.set_defaults(func=cmd_list)

    prepare_parser = sub.add_parser(
        "prepare", help="Write a queue JSON for selected submitted applications"
    )
    prepare_parser.add_argument(
        "--pick",
        nargs="+",
        type=int,
        required=True,
        help="1-based numbers from list-submitted output",
    )
    prepare_parser.add_argument(
        "--output",
        default="/tmp/jobhunting-outreach-queue.json",
        help="Output JSON path",
    )
    prepare_parser.add_argument(
        "--no-scaffold",
        action="store_true",
        help="Do not create cold-email.md when it is missing",
    )
    prepare_parser.set_defaults(func=cmd_prepare)

    run_parser = sub.add_parser(
        "run", help="Prepare selected submitted applications for automatic subagent launch"
    )
    run_parser.add_argument(
        "--pick",
        nargs="+",
        type=int,
        required=True,
        help="1-based numbers from list-submitted output",
    )
    run_parser.add_argument(
        "--output",
        default="/tmp/jobhunting-outreach-queue.json",
        help="Output JSON path",
    )
    run_parser.add_argument(
        "--no-scaffold",
        action="store_true",
        help="Do not create cold-email.md when it is missing",
    )
    run_parser.set_defaults(func=cmd_prepare)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
