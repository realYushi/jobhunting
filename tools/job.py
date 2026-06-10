#!/usr/bin/env python3
"""Unified CLI dispatcher for job-hunting tools.

Delegates to the existing tool modules without duplicating logic:

  job pipeline <args>                    tools/pipeline.py
  job resume --company <c> --role <r>    tools/resume.py
  job resume reactive <subcmd> <args>    tools/reactive_resume.py
  job resume cover-letter <args>         tools/cover_letter_pdf.py
  job score match --jd <jd>              tools/match_score.py
  job score ats --resume <r> --jd <jd>   tools/ats_check.py
  job outreach <subcmd> <args>           tools/outreach.py
  job apply --job <j> --company <c>      tools/apply.py
  job status                             tools/status.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _tools_dir() -> Path:
    """Return the tools/ directory (where this file lives)."""
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Routing table: (command, [subcommand]) -> tools module name
# ---------------------------------------------------------------------------

_ROUTES: dict[tuple[str, str | None], str] = {
    ("pipeline", None): "pipeline",
    ("resume", None): "resume",
    ("resume", "reactive"): "reactive_resume",
    ("resume", "cover-letter"): "cover_letter_pdf",
    ("score", "match"): "match_score",
    ("score", "ats"): "ats_check",
    ("outreach", None): "outreach",
    ("apply", None): "apply",
    ("status", None): "status",
}


def _route(argv: list[str]) -> tuple[str, list[str]]:
    """Determine the target module and the argv to pass to its main().

    Returns (module_name, argv_for_module).
    """
    if not argv:
        return "", []

    command = argv[0]

    # Commands with no subcommands: consume just the command word
    if command in ("pipeline", "outreach", "apply", "status"):
        return command, argv[1:]

    if command == "resume":
        if len(argv) > 1 and argv[1] in ("reactive", "cover-letter"):
            sub = argv[1]
            return f"resume/{sub}", argv[2:]
        # Bare `job resume <args>` — delegates to resume.py
        return "resume", argv[1:]

    if command == "score":
        if len(argv) > 1 and argv[1] in ("match", "ats"):
            sub = argv[1]
            return f"score/{sub}", argv[2:]
        # `job score` alone — show score-level help
        return "score", argv[1:]

    # Unknown command — let the caller print help
    return "", argv


def _resolve_module(route: str) -> str | None:
    """Map a route key to a tools module name. Returns None for unknown routes."""
    return _ROUTES.get(
        _route_key(route),
    )


def _route_key(route: str) -> tuple[str, str | None]:
    """Parse 'resume/reactive' into ('resume', 'reactive')."""
    parts = route.split("/", 1)
    command = parts[0]
    sub = parts[1] if len(parts) > 1 else None
    return (command, sub)


def main() -> int:
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        _print_help()
        return 0

    route, module_argv = _route(argv)

    if not route:
        print(f"Unknown command: {argv[0]}", file=sys.stderr)
        _print_help()
        return 1

    module_name = _ROUTES.get(_route_key(route))
    if module_name is None:
        print(f"Unknown command: {' '.join(argv[:2])}", file=sys.stderr)
        _print_help()
        return 1

    # The tool modules import from lib.* which lives under tools/. Put tools/
    # on sys.path so those imports resolve, and add the tools/ parent so the
    # module itself is importable by name.
    old_argv = sys.argv
    sys.argv = [module_name] + module_argv
    tools_dir = str(_tools_dir())
    try:
        sys.path.insert(0, tools_dir)
        mod = importlib.import_module(module_name)
        result = mod.main()
        # main() may return None (status.py) or int
        return result if isinstance(result, int) else 0
    finally:
        sys.argv = old_argv
        if tools_dir in sys.path:
            sys.path.remove(tools_dir)


def _print_help() -> None:
    print(
        """\
usage: job <command> [subcommand] [options]

Unified CLI for job-hunting tools.

Commands:
  pipeline                  Run the job research pipeline (scrape, score, package)
  resume                    Generate a role-optimized JSON resume
  resume reactive           Reactive Resume API (list, get, create, push, update, pdf, lock, delete)
  resume cover-letter       Render cover-letter.md to PDF
  score match               Match-score gate + red-flag scan for a JD
  score ats                 ATS keyword coverage check
  outreach                  List submitted applications and prepare outreach targets
  apply                     Create a local job application package
  status                    Print application tracker status

Pass --help after any command for its options:
  job pipeline --help
  job resume --help
  job resume reactive --help
  job score match --help
"""
    )


if __name__ == "__main__":
    raise SystemExit(main())
