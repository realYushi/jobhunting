#!/usr/bin/env python3
"""Match-score gate + red-flag scan for a job description.

The agent extracts required/preferred skills from the JD (judgment call),
then this script does the deterministic counting against the candidate
profile (LinkedIn-CV-Profile.md + base-resume.json) and the red-flag scan
against the JD text.

Exits 0 always (informational). Use --strict to exit 1 when verdict is SKIP.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.paths import project_root  # noqa: E402
from tools.lib.keyword_match import (  # noqa: E402
    candidate_text,
    compute_match_score,
    scan_red_flags,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Match-score + red-flag gate")
    parser.add_argument("--jd", required=True, help="Path to job description")
    parser.add_argument(
        "--profile",
        default="LinkedIn-CV-Profile.md",
        help="Candidate profile (default: LinkedIn-CV-Profile.md)",
    )
    parser.add_argument(
        "--resume",
        default="templates/base-resume.json",
        help="Base resume JSON (default: templates/base-resume.json)",
    )
    parser.add_argument("--required", nargs="*", default=[], help="Required skills/terms")
    parser.add_argument("--preferred", nargs="*", default=[], help="Preferred skills/terms")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 when verdict is SKIP (<60%%)"
    )
    args = parser.parse_args()

    root = project_root()
    jd_path = Path(args.jd)
    if not jd_path.is_absolute():
        jd_path = root / jd_path
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = root / profile_path
    resume_path = Path(args.resume)
    if not resume_path.is_absolute():
        resume_path = root / resume_path

    if not jd_path.exists():
        parser.error(f"JD not found: {jd_path}")

    text = candidate_text(profile_path, resume_path)
    jd_text = jd_path.read_text()

    score = compute_match_score(text, list(args.required), list(args.preferred))
    red_flags = scan_red_flags(jd_text)

    report = {
        "jd": str(jd_path),
        "required": [{"keyword": k, "present": ok} for k, ok in score.required],
        "preferred": [{"keyword": k, "present": ok} for k, ok in score.preferred],
        "required_pct": score.required_pct,
        "preferred_pct": score.preferred_pct,
        "overall_pct": score.overall_pct,
        "verdict": score.verdict,
        "red_flags": {
            cat: [{"pattern": p, "count": c} for p, c in items]
            for cat, items in red_flags.items()
        },
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("MATCH SCORE REPORT")
        print("=" * 40)
        if args.required:
            req_hit = sum(1 for _, ok in score.required if ok)
            print(f"Required ({req_hit}/{len(args.required)}):")
            for kw, ok in score.required:
                mark = "OK  " if ok else "MISS"
                print(f"  [{mark}] {kw}")
        if args.preferred:
            pref_hit = sum(1 for _, ok in score.preferred if ok)
            print(f"Preferred ({pref_hit}/{len(args.preferred)}):")
            for kw, ok in score.preferred:
                mark = "OK  " if ok else "MISS"
                print(f"  [{mark}] {kw}")
        print("-" * 40)
        if args.required and args.preferred:
            print(
                f"Required: {score.required_pct}% (x0.7)  "
                f"Preferred: {score.preferred_pct}% (x0.3)"
            )
        print(f"Overall:  {score.overall_pct}%")
        print(f"Verdict:  {score.verdict}")
        all_results = list(score.required) + list(score.preferred)
        if score.overall_pct < 75 and any(not ok for _, ok in all_results):
            print()
            print("NOTE: matching is literal keyword search. Before trusting the verdict,")
            print("scan MISS items for adjacent tech in the candidate profile (e.g., NestJS")
            print("for FastAPI, Azure for AWS) — those are partial matches the score ignores.")
        print()
        if red_flags:
            print("RED FLAGS")
            print("-" * 40)
            for cat, items in red_flags.items():
                for pattern, count in items:
                    print(f"  [{cat}] {pattern}  ({count}x)")
        else:
            print("RED FLAGS: none detected")

    if args.strict and score.overall_pct < 60:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
